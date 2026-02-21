from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_TARGET_URL_ENV = "GSD_STRUCTURED_FLOW_TARGET_URL"
_STORAGE_STATE_ENV = "GSD_STRUCTURED_FLOW_STORAGE_STATE"
_HEADLESS_ENV = "GSD_STRUCTURED_FLOW_HEADLESS"
_RECORD_VIDEO_DIR_ENV = "GSD_STRUCTURED_FLOW_RECORD_VIDEO_DIR"
_RECORD_VIDEO_SIZE_ENV = "GSD_STRUCTURED_FLOW_RECORD_VIDEO_SIZE_JSON"
_RECORD_VIDEO_FPS_ENV = "GSD_STRUCTURED_FLOW_RECORD_VIDEO_FRAMERATE"
_EXTRACT_FIELDS_ENV = "GSD_STRUCTURED_FLOW_EXTRACT_FIELDS_JSON"
_ENABLE_DEFAULT_EXTENSIONS_ENV = "GSD_STRUCTURED_FLOW_ENABLE_DEFAULT_EXTENSIONS"
_CDP_WAIT_TIMEOUT_ENV = "GSD_STRUCTURED_FLOW_CDP_WAIT_TIMEOUT_S"


def build_replay_script_from_events(
    *,
    events: list[dict[str, Any]],
    default_extract_fields: list[dict[str, Any]] | None,
    extract_timing: str,
    extract_after_action_index: int | None,
    settle_ms: int,
    default_step_timeout_ms: int,
) -> tuple[str, dict[str, Any] | None]:
    """Generate an LLM-free replay script (Actor API) from captured browser-use events.

    This is used for the Agent-based record strategy when CodeAgent export isn't available.

    Args:
        events: Captured events (dicts) from BrowserSession.event_bus.
        default_extract_fields: Optional extract_fields specs to run during replay.
        extract_timing: "before_last_click" (default) or "after_all_actions".
        extract_after_action_index: Optional explicit insertion index (0-based) into actions.
        settle_ms: Small sleep after each action to allow UI to settle.
        default_step_timeout_ms: Default per-action wait timeout for selector lookup.

    Returns:
        (script_text, dsl_payload)
    """

    def _coerce_int(value: object | None) -> int | None:
        try:
            return int(value) if value is not None else None
        except Exception:
            return None

    settle_ms = max(0, int(_coerce_int(settle_ms) or 0))
    default_step_timeout_ms = max(1_000, int(_coerce_int(default_step_timeout_ms) or 30_000))

    actions: list[dict[str, Any]] = []
    for evt in events:
        t = str(evt.get("type") or "")
        if t == "NavigateToUrlEvent" and evt.get("url"):
            actions.append({"type": "navigate", "url": str(evt.get("url"))})
        elif t == "ClickElementEvent":
            actions.append(
                {
                    "type": "click",
                    "selector": evt.get("selector"),
                    "xpath": evt.get("xpath"),
                }
            )
        elif t == "TypeTextEvent":
            actions.append(
                {
                    "type": "fill",
                    "selector": evt.get("selector"),
                    "xpath": evt.get("xpath"),
                    "text": evt.get("text"),
                    "text_env": evt.get("text_env"),
                }
            )
        elif t == "SendKeysEvent" and evt.get("keys") is not None:
            actions.append({"type": "press", "key": str(evt.get("keys"))})

    def _find_last_click_index() -> int | None:
        for i in range(len(actions) - 1, -1, -1):
            if actions[i].get("type") == "click":
                return i
        return None

    extract_insert_index: int | None = None
    if default_extract_fields:
        if extract_after_action_index is not None:
            extract_insert_index = max(0, min(int(extract_after_action_index) + 1, len(actions)))
        elif str(extract_timing or "").strip().lower() == "after_all_actions":
            extract_insert_index = len(actions)
        else:
            last_click = _find_last_click_index()
            extract_insert_index = last_click if last_click is not None else len(actions)

    dsl_steps: list[dict[str, Any]] = []
    for action in actions:
        t = str(action.get("type") or "")
        if t == "navigate":
            dsl_steps.append(
                {
                    "id": f"nav_{len(dsl_steps)}",
                    "type": "eval_js",
                    "expression": "(_url) => { location.href = _url; }",
                    "args": [action.get("url")],
                }
            )
        elif t == "click" and action.get("selector"):
            dsl_steps.append(
                {
                    "id": f"click_{len(dsl_steps)}",
                    "type": "click",
                    "selector": action.get("selector"),
                }
            )
        elif t == "fill" and action.get("selector"):
            text_val = action.get("text")
            if action.get("text_env"):
                # DSL runner is LLM-free and doesn't support env indirection for secrets.
                # Keep an empty value and surface the env name for debugging.
                text_val = ""
            dsl_steps.append(
                {
                    "id": f"fill_{len(dsl_steps)}",
                    "type": "fill",
                    "selector": action.get("selector"),
                    "value": text_val,
                    "value_env": action.get("text_env"),
                }
            )
        elif t == "press" and action.get("key"):
            dsl_steps.append(
                {
                    "id": f"press_{len(dsl_steps)}",
                    "type": "press",
                    "key": action.get("key"),
                }
            )

    if default_extract_fields and extract_insert_index is not None:
        # Insert a DSL extraction step.
        extract_step = {
            "id": "extract_fields",
            "type": "extract_fields",
            "fields": default_extract_fields,
        }
        dsl_steps.insert(min(extract_insert_index, len(dsl_steps)), extract_step)

    dsl_payload: dict[str, Any] | None = None
    if dsl_steps:
        dsl_payload = {"version": "gsd.structured_flow.dsl.v1", "steps": dsl_steps}

    default_extract_json = (
        json.dumps(default_extract_fields, ensure_ascii=False)
        if default_extract_fields is not None
        else "null"
    )
    dsl_json = json.dumps(dsl_payload or {}, indent=2, sort_keys=True, ensure_ascii=False)

    lines: list[str] = []
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("import asyncio")
    lines.append("import json")
    lines.append("import os")
    lines.append("import sys")
    lines.append("import time")
    lines.append("from typing import Any")
    lines.append("")
    lines.append("from browser_use import BrowserSession")
    lines.append("")
    lines.append("# --- gsd structured flow replay script (generated) ---")
    lines.append(
        f"_GSD_TARGET_URL = os.environ.get({_TARGET_URL_ENV!r}) or "
        "(sys.argv[1] if len(sys.argv) > 1 else '')"
    )
    lines.append("if not _GSD_TARGET_URL:")
    lines.append(
        f"    raise RuntimeError(f\"Missing target url. Set {_TARGET_URL_ENV}=... "
        "or pass it as argv[1].\")"
    )
    lines.append("")
    lines.append(f"_DEFAULT_EXTRACT_FIELDS_JSON = {default_extract_json!r}")
    lines.append(
        f"_EXTRACT_FIELDS_JSON = os.environ.get({_EXTRACT_FIELDS_ENV!r}) or "
        "_DEFAULT_EXTRACT_FIELDS_JSON"
    )
    lines.append("try:")
    lines.append(
        "    EXTRACT_FIELDS = json.loads(_EXTRACT_FIELDS_JSON) "
        "if _EXTRACT_FIELDS_JSON else None"
    )
    lines.append("except Exception:")
    lines.append("    EXTRACT_FIELDS = None")
    lines.append("")
    lines.append(f"SETTLE_MS = int(os.environ.get('GSD_STRUCTURED_FLOW_SETTLE_MS') or {settle_ms})")
    lines.append(
        "DEFAULT_STEP_TIMEOUT_MS = int(os.environ.get('GSD_STRUCTURED_FLOW_STEP_TIMEOUT_MS') "
        f"or {default_step_timeout_ms})"
    )
    lines.append("")
    lines.append("def _gsd_bool_env(name: str, default: bool) -> bool:")
    lines.append("    raw = os.environ.get(name)")
    lines.append("    if raw is None:")
    lines.append("        return default")
    lines.append("    text = str(raw).strip().lower()")
    lines.append("    if text in {'1','true','yes','y','on'}:")
    lines.append("        return True")
    lines.append("    if text in {'0','false','no','n','off'}:")
    lines.append("        return False")
    lines.append("    return default")
    lines.append("")
    lines.append("def _gsd_browser_kwargs() -> dict[str, object]:")
    lines.append("    kwargs: dict[str, object] = {}")
    lines.append(f"    kwargs['headless'] = _gsd_bool_env({_HEADLESS_ENV!r}, True)")
    lines.append(
        "    kwargs['enable_default_extensions'] = _gsd_bool_env("
        f"{_ENABLE_DEFAULT_EXTENSIONS_ENV!r}, True)"
    )
    lines.append("    kwargs['args'] = ['--remote-allow-origins=*']")
    lines.append(f"    storage = os.environ.get({_STORAGE_STATE_ENV!r})")
    lines.append("    if storage:")
    lines.append("        kwargs['storage_state'] = storage")
    lines.append(f"    record_dir = os.environ.get({_RECORD_VIDEO_DIR_ENV!r})")
    lines.append("    if record_dir:")
    lines.append("        kwargs['record_video_dir'] = record_dir")
    lines.append(f"    record_size = os.environ.get({_RECORD_VIDEO_SIZE_ENV!r})")
    lines.append("    if record_size:")
    lines.append("        try:")
    lines.append("            kwargs['record_video_size'] = json.loads(record_size)")
    lines.append("        except Exception:")
    lines.append("            pass")
    lines.append(f"    record_fps = os.environ.get({_RECORD_VIDEO_FPS_ENV!r})")
    lines.append("    if record_fps:")
    lines.append("        try:")
    lines.append("            kwargs['record_video_framerate'] = int(str(record_fps).strip())")
    lines.append("        except Exception:")
    lines.append("            pass")
    lines.append("    return kwargs")
    lines.append("")
    lines.append("def _gsd_patch_browser_use_cdp_wait_timeout() -> None:")
    lines.append(f"    raw = os.environ.get({_CDP_WAIT_TIMEOUT_ENV!r})")
    lines.append("    if not raw:")
    lines.append("        return")
    lines.append("    try:")
    lines.append("        timeout_s = float(str(raw).strip())")
    lines.append("    except Exception:")
    lines.append("        return")
    lines.append("    if not (timeout_s and timeout_s > 0):")
    lines.append("        return")
    lines.append("    try:")
    lines.append("        from browser_use.browser.watchdogs import local_browser_watchdog")
    lines.append("    except Exception:")
    lines.append("        return")
    lines.append("    cls = getattr(local_browser_watchdog, 'LocalBrowserWatchdog', None)")
    lines.append("    if cls is None:")
    lines.append("        return")
    lines.append("    orig = getattr(cls, '_wait_for_cdp_url', None)")
    lines.append("    if not callable(orig) or getattr(orig, '_gsd_patched', False):")
    lines.append("        return")
    lines.append("")
    lines.append("    async def _wrapped(port: int, timeout: float = 30) -> str:")
    lines.append("        return await orig(port, timeout=float(timeout_s))")
    lines.append("")
    lines.append("    _wrapped._gsd_patched = True  # type: ignore[attr-defined]")
    lines.append("    try:")
    lines.append("        cls._wait_for_cdp_url = staticmethod(_wrapped)")
    lines.append("    except Exception:")
    lines.append("        return")
    lines.append("")
    lines.append("def _gsd_browser_session() -> BrowserSession:")
    lines.append("    _gsd_patch_browser_use_cdp_wait_timeout()")
    lines.append("    kwargs = _gsd_browser_kwargs()")
    lines.append("    try:")
    lines.append("        return BrowserSession(**kwargs)")
    lines.append("    except TypeError:")
    lines.append(
        "        for key in ('record_video_dir','record_video_size',"
        "'record_video_framerate','args'):"
    )
    lines.append("            kwargs.pop(key, None)")
    lines.append("        return BrowserSession(**kwargs)")
    lines.append("")
    lines.append("async def _maybe_sleep_ms(ms: int) -> None:")
    lines.append("    if ms and ms > 0:")
    lines.append("        await asyncio.sleep(float(ms) / 1000.0)")
    lines.append("")
    lines.append("async def _goto(page: Any, url: str) -> None:")
    lines.append("    fn = getattr(page, 'goto', None) or getattr(page, 'navigate_to', None)")
    lines.append("    if callable(fn):")
    lines.append("        await fn(str(url))")
    lines.append("        return")
    lines.append("    ev = getattr(page, 'evaluate', None)")
    lines.append("    if not callable(ev):")
    lines.append("        raise RuntimeError('Page has no goto/navigate_to/evaluate')")
    lines.append("    await ev('(_url) => { location.href = _url; }', str(url))")
    lines.append("")
    lines.append("async def _wait_for_selector(page, selector, timeout_ms):")
    lines.append("    started = time.monotonic()")
    lines.append("    while (time.monotonic() - started) * 1000.0 < float(timeout_ms):")
    lines.append("        els = await page.get_elements_by_css_selector(selector)")
    lines.append("        if els:")
    lines.append("            return list(els)")
    lines.append("        await asyncio.sleep(0.1)")
    lines.append("    raise RuntimeError(f'selector not found: {selector}')")
    lines.append("")
    lines.append("async def _click(page: Any, *, selector: str | None, xpath: str | None) -> None:")
    lines.append("    if selector:")
    lines.append("        els = await _wait_for_selector(page, selector, DEFAULT_STEP_TIMEOUT_MS)")
    lines.append("        await els[0].click()")
    lines.append("        return")
    lines.append("    if xpath:")
    lines.append("        ev = getattr(page, 'evaluate', None)")
    lines.append("        if not callable(ev):")
    lines.append("            raise RuntimeError('Page.evaluate required for xpath click')")
    lines.append(
        "        ok_raw = await ev("
        "'(xp) => { const n = document.evaluate(xp, document, null, "
        "XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue; "
        "if (!n) return false; n.click(); return true; }', "
        "xpath)"
    )
    lines.append("        ok_txt = str(ok_raw or '').strip().lower()")
    lines.append("        ok = ok_txt in {'true','1','yes','y','on'}")
    lines.append("        if not ok:")
    lines.append("            raise RuntimeError(f'xpath not found: {xpath}')")
    lines.append("        return")
    lines.append("    raise RuntimeError('click missing selector and xpath')")
    lines.append("")
    lines.append("async def _fill(page, *, selector, xpath, text):")
    lines.append("    if selector:")
    lines.append("        els = await _wait_for_selector(page, selector, DEFAULT_STEP_TIMEOUT_MS)")
    lines.append("        await els[0].fill(text)")
    lines.append("        return")
    lines.append("    if xpath:")
    lines.append("        ev = getattr(page, 'evaluate', None)")
    lines.append("        if not callable(ev):")
    lines.append("            raise RuntimeError('Page.evaluate required for xpath fill')")
    lines.append(
        "        ok_raw = await ev("
        "          '(xp, value) => {"
        "            const n = document.evaluate(xp, document, null, "
        "XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;"
        "            if (!n) return false;"
        "            try { n.focus(); } catch (e) {}"
        "            n.value = String(value ?? \"\");"
        "            n.dispatchEvent(new Event(\"input\", {bubbles:true}));"
        "            n.dispatchEvent(new Event(\"change\", {bubbles:true}));"
        "            return true;"
        "          }',"
        "          xpath,"
        "          text,"
        "        )"
    )
    lines.append("        ok_txt = str(ok_raw or '').strip().lower()")
    lines.append("        ok = ok_txt in {'true','1','yes','y','on'}")
    lines.append("        if not ok:")
    lines.append("            raise RuntimeError(f'xpath not found: {xpath}')")
    lines.append("        return")
    lines.append("    raise RuntimeError('fill missing selector and xpath')")
    lines.append("")
    lines.append("async def _extract_fields(page: Any) -> dict[str, Any]:")
    lines.append("    if not EXTRACT_FIELDS:")
    lines.append("        return {}")
    lines.append("    ev = getattr(page, 'evaluate', None)")
    lines.append("    if not callable(ev):")
    lines.append("        raise RuntimeError('Page.evaluate required for extraction')")
    lines.append("    expr = r'''")
    lines.append("    (specs) => {")
    lines.append("      const out = {};")
    lines.append("      const pickOne = (nodes, nth) => {")
    lines.append("        const idx = Math.max(0, Number(nth || 0));")
    lines.append("        return nodes && nodes.length > idx ? nodes[idx] : null;")
    lines.append("      };")
    lines.append("      const getValue = (node, kind, attr) => {")
    lines.append("        if (!node) return null;")
    lines.append("        if (kind === 'inner_text') return node.innerText ?? null;")
    lines.append("        if (kind === 'text_content') return node.textContent ?? null;")
    lines.append("        if (kind === 'html') return node.outerHTML ?? null;")
    lines.append("        if (kind === 'value') {")
    lines.append("          return node.value!==undefined?String(node.value):null;")
    lines.append("        }")
    lines.append("        if (kind === 'attr') return node.getAttribute(attr) ?? null;")
    lines.append("        return null;")
    lines.append("      };")
    lines.append("      for (const f of specs || []) {")
    lines.append("        const name = String(f.name || '');")
    lines.append("        if (!name) continue;")
    lines.append("        const sel = String(f.selector || '');")
    lines.append("        const kind = String(f.kind || 'inner_text');")
    lines.append("        const nth = Number(f.nth || 0);")
    lines.append("        const all = !!f.all;")
    lines.append("        const attr = f.attr == null ? null : String(f.attr);")
    lines.append("        let value = null;")
    lines.append("        if (!sel) {")
    lines.append("          value = null;")
    lines.append("        } else if (all) {")
    lines.append("          const nodes = Array.from(document.querySelectorAll(sel));")
    lines.append("          value = nodes.map(n => getValue(n, kind, attr));")
    lines.append("        } else {")
    lines.append("          const nodes = Array.from(document.querySelectorAll(sel));")
    lines.append("          value = getValue(pickOne(nodes, nth), kind, attr);")
    lines.append("        }")
    lines.append("        out[name] = value;")
    lines.append("      }")
    lines.append("      return out;")
    lines.append("    }")
    lines.append("    '''.strip()")
    lines.append("    raw = await ev(expr, EXTRACT_FIELDS)")
    lines.append("    if isinstance(raw, str):")
    lines.append("        try:")
    lines.append("            obj = json.loads(raw) if raw else {}")
    lines.append("        except Exception:")
    lines.append("            return {}")
    lines.append("        return obj if isinstance(obj, dict) else {}")
    lines.append("    return raw if isinstance(raw, dict) else {}")
    lines.append("")
    lines.append("async def _wait_for_url_change_or_new_page(browser, page, timeout_s):")
    lines.append("    try:")
    lines.append("        url_before = await page.get_url()")
    lines.append("    except Exception:")
    lines.append("        url_before = None")
    lines.append("    try:")
    lines.append("        pages_before = await browser.get_pages()")
    lines.append("        n_before = len(pages_before or [])")
    lines.append("    except Exception:")
    lines.append("        n_before = 0")
    lines.append("    started = time.monotonic()")
    lines.append("    last_url = url_before")
    lines.append("    while (time.monotonic() - started) < float(timeout_s):")
    lines.append("        try:")
    lines.append("            pages = await browser.get_pages()")
    lines.append("            if pages and len(pages) > n_before:")
    lines.append("                page = pages[-1]")
    lines.append("        except Exception:")
    lines.append("            pass")
    lines.append("        try:")
    lines.append("            url = await page.get_url()")
    lines.append("        except Exception:")
    lines.append("            url = None")
    lines.append("        if url and url != url_before:")
    lines.append("            return page, url")
    lines.append("        last_url = url or last_url")
    lines.append("        await asyncio.sleep(0.2)")
    lines.append("    return page, last_url")
    lines.append("")
    lines.append(f"GSD_FALLBACK_DSL_JSON = r'''{dsl_json}'''")
    lines.append("# --- end generated helpers ---")
    lines.append("")
    lines.append("async def main() -> None:")
    lines.append("    browser = _gsd_browser_session()")
    lines.append("    await browser.start()")
    lines.append("    try:")
    lines.append("        page = await browser.new_page()")
    lines.append("        await _goto(page, _GSD_TARGET_URL)")
    lines.append("        await _maybe_sleep_ms(SETTLE_MS)")
    lines.append("        extracted: dict[str, Any] = {}")
    lines.append("        # Replayed steps captured during record")

    for idx, action in enumerate(actions):
        if (
            default_extract_fields
            and extract_insert_index is not None
            and idx == extract_insert_index
        ):
            lines.append("        extracted = await _extract_fields(page)")
            lines.append("        await _maybe_sleep_ms(SETTLE_MS)")

        t = str(action.get("type") or "")
        if t == "navigate" and action.get("url"):
            url = json.dumps(str(action.get("url")))
            lines.append(f"        await _goto(page, {url})")
            lines.append("        await _maybe_sleep_ms(SETTLE_MS)")
        elif t == "click":
            sel = json.dumps(str(action.get("selector"))) if action.get("selector") else "None"
            xp = json.dumps(str(action.get("xpath"))) if action.get("xpath") else "None"
            lines.append(f"        await _click(page, selector={sel}, xpath={xp})")
            lines.append("        await _maybe_sleep_ms(SETTLE_MS)")
        elif t == "fill":
            sel = json.dumps(str(action.get("selector"))) if action.get("selector") else "None"
            xp = json.dumps(str(action.get("xpath"))) if action.get("xpath") else "None"
            if action.get("text_env"):
                env_name = json.dumps(str(action.get("text_env")))
                lines.append(f"        _val = os.environ.get({env_name})")
                lines.append(
                    "        if _val is None: raise RuntimeError("
                    "'missing required env var for recorded input')"
                )
                lines.append(
                    f"        await _fill(page, selector={sel}, xpath={xp}, text=str(_val))"
                )
            else:
                text_val = json.dumps(str(action.get("text") or ""))
                lines.append(
                    f"        await _fill(page, selector={sel}, xpath={xp}, text={text_val})"
                )
            lines.append("        await _maybe_sleep_ms(SETTLE_MS)")
        elif t == "press" and action.get("key"):
            key = json.dumps(str(action.get("key")))
            lines.append(f"        await page.press({key})")
            lines.append("        await _maybe_sleep_ms(SETTLE_MS)")

    if (
        default_extract_fields
        and extract_insert_index is not None
        and extract_insert_index == len(actions)
    ):
        lines.append("        extracted = await _extract_fields(page)")
        lines.append("        await _maybe_sleep_ms(SETTLE_MS)")

    # Final URL capture (handles JS nav and new tabs)
    lines.append(
        "        page, final_url = await _wait_for_url_change_or_new_page("
        "browser, page, timeout_s=10.0)"
    )
    lines.append("        if not final_url:")
    lines.append("            final_url = await page.get_url()")
    lines.append(
        "        print('GSD_STRUCTURED_FLOW_RESULT=' + json.dumps("
        "{'final_url': final_url, 'extracted': extracted}, ensure_ascii=False))"
    )
    lines.append("    finally:")
    lines.append("        await browser.stop()")
    lines.append("")
    lines.append("if __name__ == '__main__':")
    lines.append("    asyncio.run(main())")

    script = "\n".join(lines) + "\n"
    return script, dsl_payload


def patch_exported_script(script: str) -> str:
    """Patch browser-use CodeAgent exported scripts for stable replay.

    Current browser-use `session_to_python_script` exports a script that uses a default
    BrowserSession() constructor and often hardcodes the initial navigate(...) URL.

    This patch:
    - adds a TARGET_URL derived from env/argv
    - replaces the first navigate("https://...") call with navigate(TARGET_URL)
    - replaces BrowserSession() with BrowserSession(**_gsd_browser_kwargs())
      (and injects the helper)
    """

    text = str(script)
    if not text.strip():
        raise ValueError("script is empty")

    lines = text.splitlines()

    def _find_import_insertion_index() -> int:
        # Insert after initial imports / module docstring.
        i = 0
        if lines and (lines[0].startswith('"""') or lines[0].startswith("'''")):
            quote = '"""' if lines[0].startswith('"""') else "'''"
            i += 1
            while i < len(lines) and quote not in lines[i]:
                i += 1
            if i < len(lines):
                i += 1
        while i < len(lines) and (
            lines[i].startswith("import ")
            or lines[i].startswith("from ")
            or not lines[i].strip()
        ):
            i += 1
        return i

    insertion_index = _find_import_insertion_index()

    helper_block = [
        "",
        "# --- gsd structured flow patch ---",
        (
            f"_GSD_TARGET_URL = os.environ.get({_TARGET_URL_ENV!r}) or "
            "(sys.argv[1] if len(sys.argv) > 1 else '')"
        ),
        "if not _GSD_TARGET_URL:",
        (
            f"    raise RuntimeError(f\"Missing target url. Set {_TARGET_URL_ENV}=... "
            "or pass it as argv[1].\")"
        ),
        "",
        "def _gsd_bool_env(name: str, default: bool) -> bool:",
        "    raw = os.environ.get(name)",
        "    if raw is None:",
        "        return default",
        "    text = str(raw).strip().lower()",
        "    if text in {'1','true','yes','y','on'}:",
        "        return True",
        "    if text in {'0','false','no','n','off'}:",
        "        return False",
        "    return default",
        "",
        "def _gsd_browser_kwargs() -> dict[str, object]:",
        "    kwargs: dict[str, object] = {}",
        f"    kwargs['headless'] = _gsd_bool_env({_HEADLESS_ENV!r}, True)",
        (
            "    kwargs['enable_default_extensions'] = _gsd_bool_env("
            f"{_ENABLE_DEFAULT_EXTENSIONS_ENV!r}, True)"
        ),
        "    # Chrome 111+ may require this for CDP /json/version to return 200.",
        "    kwargs['args'] = ['--remote-allow-origins=*']",
        f"    storage = os.environ.get({_STORAGE_STATE_ENV!r})",
        "    if storage:",
        "        kwargs['storage_state'] = storage",
        f"    record_dir = os.environ.get({_RECORD_VIDEO_DIR_ENV!r})",
        "    if record_dir:",
        "        kwargs['record_video_dir'] = record_dir",
        f"    record_size = os.environ.get({_RECORD_VIDEO_SIZE_ENV!r})",
        "    if record_size:",
        "        try:",
        "            kwargs['record_video_size'] = json.loads(record_size)",
        "        except Exception:",
        "            pass",
        f"    record_fps = os.environ.get({_RECORD_VIDEO_FPS_ENV!r})",
        "    if record_fps:",
        "        try:",
        "            kwargs['record_video_framerate'] = int(str(record_fps).strip())",
        "        except Exception:",
        "            pass",
        "    return kwargs",
        "",
        "def _gsd_patch_browser_use_cdp_wait_timeout() -> None:",
        f"    raw = os.environ.get({_CDP_WAIT_TIMEOUT_ENV!r})",
        "    if not raw:",
        "        return",
        "    try:",
        "        timeout_s = float(str(raw).strip())",
        "    except Exception:",
        "        return",
        "    if not (timeout_s and timeout_s > 0):",
        "        return",
        "    try:",
        "        from browser_use.browser.watchdogs import local_browser_watchdog",
        "    except Exception:",
        "        return",
        "    cls = getattr(local_browser_watchdog, 'LocalBrowserWatchdog', None)",
        "    if cls is None:",
        "        return",
        "    orig = getattr(cls, '_wait_for_cdp_url', None)",
        "    if not callable(orig) or getattr(orig, '_gsd_patched', False):",
        "        return",
        "",
        "    async def _wrapped(port: int, timeout: float = 30) -> str:",
        "        return await orig(port, timeout=float(timeout_s))",
        "",
        "    _wrapped._gsd_patched = True  # type: ignore[attr-defined]",
        "    try:",
        "        cls._wait_for_cdp_url = staticmethod(_wrapped)",
        "    except Exception:",
        "        return",
        "",
        "def _gsd_browser_session() -> 'BrowserSession':",
        "    _gsd_patch_browser_use_cdp_wait_timeout()",
        "    kwargs = _gsd_browser_kwargs()",
        "    try:",
        "        return BrowserSession(**kwargs)",
        "    except TypeError:",
        "        # Back-compat: older/newer browser-use may not accept recording kwargs.",
        (
            "        for key in ('record_video_dir','record_video_size',"
            "'record_video_framerate','args'):"
        ),
        "            kwargs.pop(key, None)",
        "        return BrowserSession(**kwargs)",
        "# --- end gsd structured flow patch ---",
        "",
    ]

    # Ensure imports exist.
    needs_os = all(not re.match(r"\s*import\s+os\b", ln) for ln in lines)
    needs_sys = all(not re.match(r"\s*import\s+sys\b", ln) for ln in lines)
    needs_json = all(not re.match(r"\s*import\s+json\b", ln) for ln in lines)
    if needs_os:
        lines.insert(0, "import os")
    if needs_sys:
        lines.insert(0, "import sys")
    if needs_json:
        lines.insert(0, "import json")

    # Recompute insertion index if we inserted at top.
    insertion_index = _find_import_insertion_index()
    lines[insertion_index:insertion_index] = helper_block

    patched = "\n".join(lines) + ("\n" if not text.endswith("\n") else "")

    # Patch BrowserSession() constructor.
    patched = re.sub(
        r"\bBrowserSession\(\s*\)",
        "_gsd_browser_session()",
        patched,
        count=1,
    )

    # Patch the first navigate("https://...") or await navigate("https://...") call.
    patched = re.sub(
        r"(\bawait\s+)?navigate\(\s*(['\"])https?://[^'\"]+\2\s*\)",
        r"\1navigate(_GSD_TARGET_URL)",
        patched,
        count=1,
    )

    return patched


def script_uses_llm_at_replay(script: str) -> tuple[bool, list[str]]:
    """Heuristic scan for replay-time LLM dependencies.

    Note: exported scripts often *bind* extract = namespace['extract'] even if unused.
    We only flag on actual calls or explicit LLM imports/instantiation.
    """

    reasons: list[str] = []
    text = str(script)
    lowered = text.lower()

    if "must_get_element_by_prompt" in lowered or "get_element_by_prompt" in lowered:
        reasons.append("uses *_by_prompt element finding")
    if re.search(r"\bawait\s+extract\(", text) or re.search(r"\bextract\(", text):
        # Avoid false-positive for assignments like `extract = namespace[...]`.
        call_sites = [
            ln
            for ln in text.splitlines()
            if "extract(" in ln and "extract =" not in ln and not ln.lstrip().startswith("#")
        ]
        if call_sites:
            reasons.append("calls extract(...) which is LLM-backed")
    if (
        "chatopenai" in lowered
        or "chatanthropic" in lowered
        or "chatbrowseruse" in lowered
    ):
        reasons.append("imports/mentions Chat* LLM classes")
    if (
        "openai_api_key" in lowered
        or "anthropic_api_key" in lowered
        or "browser_use_api_key" in lowered
    ):
        reasons.append("mentions provider API key variables")

    return bool(reasons), reasons


@dataclass(frozen=True)
class ScriptRunResult:
    ok: bool
    exit_code: int
    stdout: str
    stderr: str
    logs: list[str]
    result: dict[str, Any] | None
    error: str | None


def _bounded_lines(text: str, *, max_lines: int = 200) -> list[str]:
    lines = [ln.rstrip("\n") for ln in text.splitlines()]
    if len(lines) <= max_lines:
        return lines
    return lines[:max_lines] + [f"… ({len(lines) - max_lines} more lines truncated)"]


def _extract_result_from_output(stdout: str) -> dict[str, Any] | None:
    # Preferred marker.
    for line in reversed(stdout.splitlines()):
        if "GSD_STRUCTURED_FLOW_RESULT=" in line:
            _, tail = line.split("GSD_STRUCTURED_FLOW_RESULT=", 1)
            tail = tail.strip()
            try:
                obj = json.loads(tail)
            except Exception:
                continue
            if isinstance(obj, dict):
                return obj

    # Fallback: last JSON object line with expected keys.
    for line in reversed(stdout.splitlines()):
        candidate = line.strip()
        if not candidate.startswith("{") or not candidate.endswith("}"):
            continue
        try:
            obj = json.loads(candidate)
        except Exception:
            continue
        if isinstance(obj, dict) and ("final_url" in obj or "extracted" in obj):
            return obj
    return None


def run_python_script(
    *,
    script_path: Path,
    target_url: str,
    storage_state_path: str | None,
    headless: bool,
    enable_default_extensions: bool,
    record_video_dir: str | None,
    record_video_size: dict[str, int] | None,
    record_video_framerate: int | None,
    timeout_s: float | None,
) -> ScriptRunResult:
    env = dict(os.environ)
    env[_TARGET_URL_ENV] = str(target_url)
    env[_HEADLESS_ENV] = "1" if headless else "0"
    env[_ENABLE_DEFAULT_EXTENSIONS_ENV] = "1" if enable_default_extensions else "0"
    if storage_state_path:
        env[_STORAGE_STATE_ENV] = str(storage_state_path)
    if record_video_dir:
        env[_RECORD_VIDEO_DIR_ENV] = str(record_video_dir)
    if record_video_size:
        env[_RECORD_VIDEO_SIZE_ENV] = json.dumps(record_video_size)
    if record_video_framerate:
        env[_RECORD_VIDEO_FPS_ENV] = str(int(record_video_framerate))

    cmd = [sys.executable, str(script_path)]

    try:
        proc = subprocess.run(  # noqa: S603
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=float(timeout_s) if timeout_s is not None else None,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        logs = _bounded_lines(stdout, max_lines=120) + _bounded_lines(stderr, max_lines=80)
        return ScriptRunResult(
            ok=False,
            exit_code=124,
            stdout=stdout,
            stderr=stderr,
            logs=logs,
            result=_extract_result_from_output(stdout),
            error="timeout",
        )
    except Exception as exc:  # noqa: BLE001
        return ScriptRunResult(
            ok=False,
            exit_code=1,
            stdout="",
            stderr=str(exc),
            logs=[str(exc)],
            result=None,
            error=f"{type(exc).__name__}: {exc}",
        )

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    logs = _bounded_lines(stdout, max_lines=120) + _bounded_lines(stderr, max_lines=80)
    result = _extract_result_from_output(stdout)
    ok = proc.returncode == 0
    return ScriptRunResult(
        ok=ok,
        exit_code=int(proc.returncode),
        stdout=stdout,
        stderr=stderr,
        logs=logs,
        result=result,
        error=None if ok else f"exit_code={proc.returncode}",
    )
