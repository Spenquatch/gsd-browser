#!/usr/bin/env python3
"""End-to-end smoke test for the web_structured_flow MCP tool.

This runs:
  1) record (LLM Agent) against a local JS-driven page
  2) replay via the generated LLM-free script

It expects an LLM provider to be available for recording. By default it uses:
  GSD_LLM_PROVIDER=openai
  GSD_MODEL=gpt-4o-mini
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


def _write_site(root: Path) -> None:
    (root / "index.html").write_text(
        """<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Structured Flow Smoke</title>
    <style>
      body { font-family: sans-serif; }
      .tab { padding: 6px 10px; margin-right: 6px; }
      #details { display: none; margin-top: 8px; padding: 6px; border: 1px solid #ccc; }
    </style>
  </head>
  <body>
    <h1 id="title">Structured Flow Smoke</h1>
    <div>
      <button id="tab-html" class="tab">HTML</button>
      <button id="tab-js" class="tab">JavaScript</button>
    </div>
    <div id="content" style="margin-top: 10px;">
      <div id="html-panel">
        <p id="html-text">This is the HTML panel.</p>
      </div>
      <div id="js-panel" style="display:none;">
        <p>JS panel loaded. Greeting: <span id="greeting">Hello</span></p>
        <button id="show-details">Show details</button>
        <div id="details">
          <div>Detail A: <span id="detail-a">Alpha</span></div>
          <div>Detail B: <span id="detail-b">Bravo</span></div>
        </div>
        <div style="margin-top: 8px;">
          <label for="name">Name</label>
          <input id="name" aria-label="Name" />
          <button id="continue">Continue</button>
        </div>
      </div>
    </div>
    <script>
      const htmlBtn = document.getElementById('tab-html');
      const jsBtn = document.getElementById('tab-js');
      const htmlPanel = document.getElementById('html-panel');
      const jsPanel = document.getElementById('js-panel');
      const showDetails = document.getElementById('show-details');
      const details = document.getElementById('details');
      const cont = document.getElementById('continue');
      htmlBtn.addEventListener('click', () => {
        htmlPanel.style.display = '';
        jsPanel.style.display = 'none';
      });
      jsBtn.addEventListener('click', () => {
        htmlPanel.style.display = 'none';
        jsPanel.style.display = '';
      });
      showDetails.addEventListener('click', () => {
        details.style.display = '';
      });
      cont.addEventListener('click', () => {
        const name = document.getElementById('name').value || '';
        // JS-driven navigation (no <a href>)
        window.location.href = '/done.html?name=' + encodeURIComponent(name);
      });
    </script>
  </body>
</html>
""",
        encoding="utf-8",
    )
    (root / "done.html").write_text(
        """<!doctype html>
<html>
  <head><meta charset="utf-8" /><title>Done</title></head>
  <body>
    <h1 id="done-title">Done</h1>
    <p id="done-url"></p>
    <script>
      document.getElementById('done-url').textContent = location.href;
    </script>
  </body>
</html>
""",
        encoding="utf-8",
    )


def _start_server(root: Path) -> tuple[ThreadingHTTPServer, str]:
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, _format: str, *_args: Any) -> None:  # noqa: D401
            return

    class QuietServer(ThreadingHTTPServer):
        def handle_error(self, _request: object, _client_address: object) -> None:
            exc = sys.exc_info()[1]
            if isinstance(exc, ConnectionResetError):
                return
            return super().handle_error(_request, _client_address)

    server = QuietServer(("127.0.0.1", 0), Handler)
    host, port = server.server_address[:2]
    base_url = f"http://{host}:{port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, base_url


async def _run() -> int:
    in_docker = str(os.environ.get("IN_DOCKER", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }
    headless = True if in_docker else False

    # Default provider for record if the user hasn't set one.
    os.environ.setdefault("GSD_LLM_PROVIDER", "openai")
    os.environ.setdefault("GSD_MODEL", "gpt-4o-mini")
    # First-time browser bootstrap (extensions/downloads) can exceed browser-use defaults.
    os.environ.setdefault("TIMEOUT_BrowserStartEvent", "180")
    os.environ.setdefault("TIMEOUT_BrowserLaunchEvent", "180")
    os.environ.setdefault("GSD_STRUCTURED_FLOW_CDP_WAIT_TIMEOUT_S", "180")
    # Avoid first-run Playwright browser installation by pointing browser-use at a local browser.
    for candidate in (
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ):
        if os.path.exists(candidate):
            os.environ.setdefault("GSD_BROWSER_EXECUTABLE_PATH", candidate)
            break

    # Allow running from a repo checkout without an editable install.
    repo_gsd_browser_src = Path(__file__).resolve().parents[1] / "src"
    sys.path.insert(0, str(repo_gsd_browser_src))

    from gsd_browser import mcp_server

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # Keep template storage inside the temp directory.
        os.environ["HOME"] = str(tmp)
        os.environ["USERPROFILE"] = str(tmp)

        site_dir = tmp / "site"
        site_dir.mkdir(parents=True, exist_ok=True)
        _write_site(site_dir)
        server, base_url = _start_server(site_dir)
        try:
            start_url = f"{base_url}/index.html"
            record = {
                "url": start_url,
                "task": (
                    "Click the 'JavaScript' tab (id='tab-js'), then click 'Show details' "
                    "(id='show-details'), then type 'Bob' into the Name input (id='name'), "
                    "then click 'Continue' (id='continue')."
                ),
                "template_id": "smoke_structured_flow",
                "template_name": "Smoke Structured Flow",
                "strategy": "agent",
                "headless_browser": headless,
                "enable_default_extensions": False,
                "use_vision": False,
                "budget_s": 180,
                "max_steps": 12,
                "min_actions": 3,
                "settle_ms": 50,
                "extract": {
                    "timing": "before_last_click",
                    "fields": [
                        {"name": "greeting", "selector": "#greeting", "kind": "text_content"},
                        {"name": "detail_a", "selector": "#detail-a", "kind": "text_content"},
                        {"name": "typed_name", "selector": "#name", "kind": "value"},
                    ],
                },
            }
            rec_out = await mcp_server.web_structured_flow(record=record)
            payload = json.loads(rec_out[0].text)
            if payload.get("status") != "success":
                raise RuntimeError(f"record failed: {payload}")

            replay = {
                "template_id": "smoke_structured_flow",
                "url": start_url,
                "runner": "script",
                "headless_browser": headless,
                "enable_default_extensions": False,
                "budget_s": 180,
                "settle_ms": 50,
            }
            rep_out = await mcp_server.web_structured_flow(replay=replay)
            rep_payload = json.loads(rep_out[0].text)
            if rep_payload.get("status") not in {"success", "partial"}:
                raise RuntimeError(f"replay failed: {rep_payload}")

            final_url = str(rep_payload.get("final_url") or "")
            extracted = rep_payload.get("extracted")
            print("final_url:", final_url)
            print("extracted:", json.dumps(extracted, ensure_ascii=False))
            if "/done.html" not in final_url:
                raise RuntimeError("expected navigation to /done.html")
            if not isinstance(extracted, dict) or extracted.get("detail_a") != "Alpha":
                raise RuntimeError("extraction mismatch")
            return 0
        finally:
            server.shutdown()


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
