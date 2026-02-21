from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any, Literal


class StructuredFlowError(RuntimeError):
    pass


def _now_ts() -> float:
    return time.time()


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _page_get_url(page: Any) -> str | None:
    get_url = getattr(page, "get_url", None)
    if callable(get_url):
        try:
            return str(await _maybe_await(get_url()))
        except Exception:
            return None
    evaluate = getattr(page, "evaluate", None)
    if callable(evaluate):
        try:
            return str(await _maybe_await(evaluate("() => location.href")))
        except Exception:
            return None
    return None


async def _page_goto(page: Any, url: str) -> None:
    goto = getattr(page, "goto", None)
    if callable(goto):
        await _maybe_await(goto(str(url)))
        return
    navigate_to = getattr(page, "navigate_to", None)
    if callable(navigate_to):
        await _maybe_await(navigate_to(str(url)))
        return
    raise StructuredFlowError("Page has no goto/navigate_to method")


async def _page_get_elements(page: Any, selector: str) -> list[Any]:
    fn = getattr(page, "get_elements_by_css_selector", None)
    if not callable(fn):
        raise StructuredFlowError("Page.get_elements_by_css_selector is unavailable")
    value = await _maybe_await(fn(str(selector)))
    return list(value or [])


async def _wait_until(
    predicate: Any,
    *,
    timeout_ms: int,
    poll_interval_ms: int = 250,
) -> None:
    timeout_s = max(0.0, float(timeout_ms) / 1000.0)
    poll_s = max(0.05, float(poll_interval_ms) / 1000.0)
    started = time.monotonic()
    while True:
        if (time.monotonic() - started) >= timeout_s:
            raise TimeoutError("timed out")
        ok = await _maybe_await(predicate())
        if ok:
            return
        await asyncio.sleep(poll_s)


async def wait_selector(
    *,
    page: Any,
    selector: str,
    state: Literal["attached", "detached", "visible", "hidden"],
    timeout_ms: int,
) -> None:
    selector = str(selector)
    state = str(state)

    async def _check_attached() -> bool:
        elems = await _page_get_elements(page, selector)
        return bool(elems)

    async def _check_detached() -> bool:
        elems = await _page_get_elements(page, selector)
        return not elems

    async def _check_visibility(expected_visible: bool) -> bool:
        evaluate = getattr(page, "evaluate", None)
        if not callable(evaluate):
            # Fallback: treat presence as visibility.
            elems = await _page_get_elements(page, selector)
            return bool(elems) if expected_visible else not bool(elems)
        expr = """
        (sel, expectedVisible) => {
          const el = document.querySelector(sel);
          const isVisible = (node) => {
            if (!node) return false;
            const style = window.getComputedStyle(node);
            if (!style) return false;
            if (
              style.display === 'none' ||
              style.visibility === 'hidden' ||
              style.opacity === '0'
            ) return false;
            const rect = node.getBoundingClientRect();
            return !!(rect && rect.width > 0 && rect.height > 0);
          };
          const visible = isVisible(el);
          return expectedVisible ? visible : !visible;
        }
        """.strip()
        try:
            return bool(await _maybe_await(evaluate(expr, selector, expected_visible)))
        except Exception:
            elems = await _page_get_elements(page, selector)
            return bool(elems) if expected_visible else not bool(elems)

    if state == "attached":
        await _wait_until(_check_attached, timeout_ms=timeout_ms)
        return
    if state == "detached":
        await _wait_until(_check_detached, timeout_ms=timeout_ms)
        return
    if state == "visible":
        await _wait_until(lambda: _check_visibility(True), timeout_ms=timeout_ms)
        return
    if state == "hidden":
        await _wait_until(lambda: _check_visibility(False), timeout_ms=timeout_ms)
        return
    raise ValueError(f"Invalid wait_selector.state: {state!r}")


async def wait_text(
    *,
    page: Any,
    text: str,
    selector: str | None,
    case_sensitive: bool,
    timeout_ms: int,
) -> None:
    raw = str(text)
    target = raw if case_sensitive else raw.lower()

    evaluate = getattr(page, "evaluate", None)
    if not callable(evaluate):
        raise StructuredFlowError("Page.evaluate is required for wait_text")

    expr = """
    (needle, sel, caseSensitive) => {
      const node = sel ? document.querySelector(sel) : document.body;
      const hay = (node && (node.innerText || node.textContent || "")) || "";
      if (caseSensitive) return hay.includes(needle);
      return hay.toLowerCase().includes(String(needle).toLowerCase());
    }
    """.strip()

    async def _check() -> bool:
        return bool(await _maybe_await(evaluate(expr, target, selector, case_sensitive)))

    await _wait_until(_check, timeout_ms=timeout_ms)


async def extract_fields(
    *,
    page: Any,
    fields: list[dict[str, Any]],
    timeout_ms: int,
) -> dict[str, Any]:
    _ = timeout_ms
    evaluate = getattr(page, "evaluate", None)
    if not callable(evaluate):
        raise StructuredFlowError("Page.evaluate is required for extract_fields")

    expr = """
    (specs) => {
      const out = {};
      const pickOne = (nodes, nth) => {
        const idx = Math.max(0, Number(nth || 0));
        return nodes && nodes.length > idx ? nodes[idx] : null;
      };
      const getValue = (node, kind, attr) => {
        if (!node) return null;
        if (kind === "inner_text") return node.innerText ?? null;
        if (kind === "text_content") return node.textContent ?? null;
        if (kind === "html") return node.outerHTML ?? null;
        if (kind === "value") return (node.value !== undefined ? String(node.value) : null);
        if (kind === "attr") return node.getAttribute(attr) ?? null;
        return null;
      };
      for (const f of specs || []) {
        const name = String(f.name || "");
        if (!name) continue;
        const sel = String(f.selector || "");
        const kind = String(f.kind || "inner_text");
        const nth = Number(f.nth || 0);
        const all = !!f.all;
        const attr = f.attr == null ? null : String(f.attr);
        let value = null;
        if (!sel) {
          value = null;
        } else if (all) {
          const nodes = Array.from(document.querySelectorAll(sel));
          value = nodes.map(n => getValue(n, kind, attr));
        } else {
          const nodes = Array.from(document.querySelectorAll(sel));
          value = getValue(pickOne(nodes, nth), kind, attr);
        }
        out[name] = value;
      }
      return out;
    }
    """.strip()
    value = await _maybe_await(evaluate(expr, fields))
    if not isinstance(value, dict):
        raise StructuredFlowError("extract_fields returned non-object")
    return value


async def run_dsl_flow(
    *,
    browser: Any,
    page: Any,
    steps: list[dict[str, Any]],
    step_timeout_s: float | None,
    settle_ms: int,
) -> tuple[str | None, dict[str, Any], list[dict[str, Any]]]:
    """Run a deterministic flow against an already-opened page.

    Returns: (final_url, extracted, step_results)
    """
    extracted: dict[str, Any] = {}
    results: list[dict[str, Any]] = []

    default_timeout_ms = int(float(step_timeout_s) * 1000.0) if step_timeout_s else 30_000

    for step in steps:
        started_at = _now_ts()
        step_id = str(step.get("id") or "")
        step_type = str(step.get("type") or "")
        timeout_ms = int(step.get("timeout_ms") or default_timeout_ms)

        url_before = await _page_get_url(page)
        record: dict[str, Any] = {
            "id": step_id or step_type or "step",
            "type": step_type,
            "status": "failed",
            "started_at": started_at,
            "finished_at": None,
            "url_before": url_before,
            "url_after": None,
            "value": None,
            "fields": None,
            "error": None,
        }

        try:
            if step_type == "goto":
                await _page_goto(page, str(step["url"]))
            elif step_type == "click":
                selector = str(step["selector"])
                nth = int(step.get("nth") or 0)
                elems = await _page_get_elements(page, selector)
                if nth >= len(elems):
                    raise StructuredFlowError(
                        f"click: selector matched {len(elems)} elements; nth={nth} out of range"
                    )
                click = getattr(elems[nth], "click", None)
                if not callable(click):
                    raise StructuredFlowError("Element.click is unavailable")
                await _maybe_await(click())
                post_wait = step.get("post_wait")
                if isinstance(post_wait, dict):
                    if post_wait.get("type") == "selector":
                        await wait_selector(
                            page=page,
                            selector=str(post_wait["selector"]),
                            state=str(post_wait.get("state") or "attached"),
                            timeout_ms=timeout_ms,
                        )
                    elif post_wait.get("type") == "text":
                        await wait_text(
                            page=page,
                            text=str(post_wait["text"]),
                            selector=(
                                str(post_wait["selector"])
                                if post_wait.get("selector") is not None
                                else None
                            ),
                            case_sensitive=bool(post_wait.get("case_sensitive", False)),
                            timeout_ms=timeout_ms,
                        )
                else:
                    await asyncio.sleep(max(0.0, float(settle_ms) / 1000.0))
            elif step_type == "fill":
                selector = str(step["selector"])
                value = str(step["value"])
                nth = int(step.get("nth") or 0)
                elems = await _page_get_elements(page, selector)
                if nth >= len(elems):
                    raise StructuredFlowError(
                        f"fill: selector matched {len(elems)} elements; nth={nth} out of range"
                    )
                fill = getattr(elems[nth], "fill", None)
                if not callable(fill):
                    raise StructuredFlowError("Element.fill is unavailable")
                await _maybe_await(fill(value))
                post_wait = step.get("post_wait")
                if isinstance(post_wait, dict):
                    if post_wait.get("type") == "selector":
                        await wait_selector(
                            page=page,
                            selector=str(post_wait["selector"]),
                            state=str(post_wait.get("state") or "attached"),
                            timeout_ms=timeout_ms,
                        )
                    elif post_wait.get("type") == "text":
                        await wait_text(
                            page=page,
                            text=str(post_wait["text"]),
                            selector=(
                                str(post_wait["selector"])
                                if post_wait.get("selector") is not None
                                else None
                            ),
                            case_sensitive=bool(post_wait.get("case_sensitive", False)),
                            timeout_ms=timeout_ms,
                        )
                else:
                    await asyncio.sleep(max(0.0, float(settle_ms) / 1000.0))
            elif step_type == "press":
                press = getattr(page, "press", None)
                if not callable(press):
                    raise StructuredFlowError("Page.press is unavailable")
                await _maybe_await(press(str(step["key"])))
            elif step_type == "wait_selector":
                await wait_selector(
                    page=page,
                    selector=str(step["selector"]),
                    state=str(step.get("state") or "attached"),
                    timeout_ms=timeout_ms,
                )
            elif step_type == "wait_text":
                await wait_text(
                    page=page,
                    text=str(step["text"]),
                    selector=str(step["selector"]) if step.get("selector") is not None else None,
                    case_sensitive=bool(step.get("case_sensitive", False)),
                    timeout_ms=timeout_ms,
                )
            elif step_type == "eval_js":
                evaluate = getattr(page, "evaluate", None)
                if not callable(evaluate):
                    raise StructuredFlowError("Page.evaluate is unavailable")
                expr = str(step["expression"])
                args = step.get("args") or []
                if not isinstance(args, list):
                    raise StructuredFlowError("eval_js.args must be a list")
                record["value"] = await _maybe_await(evaluate(expr, *args))
            elif step_type == "extract_fields":
                fields_spec = step.get("fields") or []
                if not isinstance(fields_spec, list):
                    raise StructuredFlowError("extract_fields.fields must be a list")
                field_values = await extract_fields(
                    page=page, fields=fields_spec, timeout_ms=timeout_ms
                )
                # Enforce required fields.
                for spec in fields_spec:
                    if not isinstance(spec, dict):
                        continue
                    if not spec.get("required"):
                        continue
                    name = str(spec.get("name") or "")
                    if name and field_values.get(name) in (None, "", []):
                        raise StructuredFlowError(f"required field missing: {name}")
                record["fields"] = field_values
                extracted.update(field_values)
            else:
                raise StructuredFlowError(f"Unknown step type: {step_type!r}")

            record["status"] = "success"
        except Exception as exc:  # noqa: BLE001
            record["status"] = "failed"
            record["error"] = f"{type(exc).__name__}: {exc}"

        finished_at = _now_ts()
        record["finished_at"] = finished_at
        record["url_after"] = await _page_get_url(page)
        results.append(record)

        if record["status"] != "success":
            break

    # Best-effort final url: check current page first, then other pages for a non-blank url.
    final_url = await _page_get_url(page)
    try:
        get_pages = getattr(browser, "get_pages", None)
        if callable(get_pages):
            pages = await _maybe_await(get_pages())
            for p in pages or []:
                candidate = await _page_get_url(p)
                if candidate and candidate != "about:blank":
                    final_url = candidate
    except Exception:
        pass

    return final_url, extracted, results
