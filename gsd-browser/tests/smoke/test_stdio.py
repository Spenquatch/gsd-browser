from __future__ import annotations

from io import StringIO

from gsd_browser.main import serve_stdio


def test_serve_stdio_echo_once() -> None:
    stdin = StringIO("ping\n")
    stdout = StringIO()

    serve_stdio(echo=True, once=True, input_stream=stdin, output_stream=stdout)

    stdout.seek(0)
    assert stdout.read() == "ping\n"
