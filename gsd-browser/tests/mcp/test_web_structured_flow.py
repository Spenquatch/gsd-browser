from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from gsd_browser.structured_flow import wait_selector
from gsd_browser.structured_flow_script import (
    patch_exported_script,
    run_python_script,
    script_uses_llm_at_replay,
)
from gsd_browser.structured_flow_store import (
    base_origin_for_url,
    load_manifest,
    save_template_files,
)


def _set_fake_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Ensure expanduser("~") resolves inside tmp for template storage.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


def test_patch_exported_script_parameterizes_url_and_browser_session() -> None:
    raw = """\
import asyncio
from browser_use import BrowserSession

async def main():
    browser = BrowserSession()
    await browser.start()
    namespace = {}
    navigate = lambda url: None
    await navigate("https://example.com/start")
    await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
"""
    patched = patch_exported_script(raw)
    assert "GSD_STRUCTURED_FLOW_TARGET_URL" in patched
    assert "_gsd_browser_session()" in patched
    assert 'await navigate(_GSD_TARGET_URL)' in patched or "navigate(_GSD_TARGET_URL)" in patched


def test_script_uses_llm_at_replay_ignores_extract_binding_but_flags_calls() -> None:
    script = """\
extract = namespace["extract"]
await extract("extract the price")
"""
    uses, reasons = script_uses_llm_at_replay(script)
    assert uses
    assert any("extract" in r for r in reasons)

    script2 = """\
extract = namespace["extract"]
# no calls
"""
    uses2, _reasons2 = script_uses_llm_at_replay(script2)
    assert not uses2


def test_run_python_script_parses_marker(tmp_path: Path) -> None:
    script_path = tmp_path / "script.py"
    payload = {"final_url": "https://example.com/final", "extracted": {"a": 1}}
    script_path.write_text(
        "import json\n"
        f"payload = {payload!r}\n"
        "print('hello')\n"
        "print('GSD_STRUCTURED_FLOW_RESULT=' + json.dumps(payload))\n",
        encoding="utf-8",
    )
    res = run_python_script(
        script_path=script_path,
        target_url="https://example.com/start",
        storage_state_path=None,
        headless=True,
        enable_default_extensions=True,
        record_video_dir=None,
        record_video_size=None,
        record_video_framerate=None,
        timeout_s=5.0,
    )
    assert res.ok
    assert isinstance(res.result, dict)
    assert res.result.get("final_url") == "https://example.com/final"


def test_template_store_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_fake_home(monkeypatch, tmp_path)
    script = "print('hi')\n"
    url = "https://example.com/a"
    manifest = save_template_files(
        template_id="t1",
        template_name="Test",
        base_origin=base_origin_for_url(url),
        recorded_example_url=url,
        script_content=script,
        uses_llm_at_replay=False,
        dsl_payload={"steps": []},
    )
    loaded = load_manifest("t1")
    assert loaded.template_id == manifest.template_id
    assert Path(loaded.script_path).exists()
    assert Path(loaded.manifest_path).exists()


def test_wait_selector_polls_until_attached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakePage:
        def __init__(self) -> None:
            self.calls = 0

        async def get_elements_by_css_selector(self, selector: str) -> list[object]:
            assert selector == "#x"
            self.calls += 1
            return [] if self.calls < 3 else [object()]

    async def _no_sleep(_s: float) -> None:
        return None

    monkeypatch.setattr("gsd_browser.structured_flow.asyncio.sleep", _no_sleep)
    page = FakePage()
    asyncio.run(wait_selector(page=page, selector="#x", state="attached", timeout_ms=1000))
    assert page.calls == 3


def test_mcp_tool_replay_script_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_fake_home(monkeypatch, tmp_path)
    from gsd_browser import mcp_server

    result_payload = {"final_url": "https://example.com/final", "extracted": {"ok": True}}
    script = (
        "import json\n"
        f"payload = {result_payload!r}\n"
        "print('GSD_STRUCTURED_FLOW_RESULT=' + json.dumps(payload))\n"
    )
    save_template_files(
        template_id="tmpl",
        template_name=None,
        base_origin="https://example.com",
        recorded_example_url="https://example.com/a",
        script_content=script,
        uses_llm_at_replay=False,
        dsl_payload=None,
    )

    out = asyncio.run(
        mcp_server.web_structured_flow(
            replay={
                "template_id": "tmpl",
                "url": "https://example.com/other",
                "runner": "script",
                "headless_browser": True,
            }
        )
    )
    assert out and out[0].type == "text"
    payload = json.loads(out[0].text)
    assert payload["status"] == "success"
    assert payload["final_url"] == "https://example.com/final"
    assert payload["extracted"] == {"ok": True}
