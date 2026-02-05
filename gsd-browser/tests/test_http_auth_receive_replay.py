from __future__ import annotations

import types

import anyio

from gsd_browser.optionb.http_auth import HttpAuthMiddleware


class _FakeVerifier:
    async def verify_token_with_audience_details(
        self, token: str
    ) -> tuple[object | None, object | None]:
        if token != "ok":
            return None, None
        return (
            types.SimpleNamespace(
                claims={
                    "tenant_id": "tenant",
                    "sub": "subject",
                    "scope": "gsd:browser:read gsd:browser:execute",
                }
            ),
            None,
        )


def _asgi_headers(headers: dict[str, str]) -> list[tuple[bytes, bytes]]:
    return [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers.items()]


def test_http_auth_receive_replay_preserves_disconnect_after_body() -> None:
    async def _run() -> None:
        request_body = b'{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

        messages: list[dict[str, object]] = [
            {"type": "http.request", "body": request_body, "more_body": False},
            {"type": "http.disconnect"},
        ]

        async def receive() -> dict[str, object]:
            return messages.pop(0) if messages else {"type": "http.disconnect"}

        seen: list[str] = []

        async def send(_: dict[str, object]) -> None:
            return

        async def inner_app(_: dict[str, object], receive_inner, __) -> None:
            first = await receive_inner()
            second = await receive_inner()
            seen.extend([str(first.get("type")), str(second.get("type"))])

        scope = {
            "type": "http",
            "path": "/mcp",
            "method": "POST",
            "headers": _asgi_headers(
                {
                    "Authorization": "Bearer ok",
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                    "Host": "localhost",
                }
            ),
        }

        middleware = HttpAuthMiddleware(inner_app, verifier=_FakeVerifier())
        await middleware(scope, receive, send)

        assert seen == ["http.request", "http.disconnect"]

    anyio.run(_run)


def test_http_auth_read_body_does_not_hang_on_disconnect_mid_body() -> None:
    async def _run() -> None:
        # Simulate a client disconnect after sending only part of the request body.
        messages: list[dict[str, object]] = [
            {"type": "http.request", "body": b'{"jsonrpc":"2.0"', "more_body": True},
            {"type": "http.disconnect"},
        ]

        async def receive() -> dict[str, object]:
            return messages.pop(0) if messages else {"type": "http.disconnect"}

        seen: list[str] = []

        async def send(_: dict[str, object]) -> None:
            return

        async def inner_app(_: dict[str, object], receive_inner, __) -> None:
            first = await receive_inner()
            second = await receive_inner()
            seen.extend([str(first.get("type")), str(second.get("type"))])

        scope = {
            "type": "http",
            "path": "/mcp",
            "method": "POST",
            "headers": _asgi_headers(
                {
                    "Authorization": "Bearer ok",
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                    "Host": "localhost",
                }
            ),
        }

        middleware = HttpAuthMiddleware(inner_app, verifier=_FakeVerifier())
        with anyio.fail_after(1):
            await middleware(scope, receive, send)

        assert seen == ["http.request", "http.disconnect"]

    anyio.run(_run)
