from __future__ import annotations

import asyncio
import socket
import time
from typing import Any

import pytest
import socketio
import uvicorn
from authlib.jose import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from socketio.exceptions import ConnectionError as SocketIOConnectionError

from gsd_browser.config import Settings
from gsd_browser.streaming.server import create_streaming_app


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


async def _wait_port(port: int, *, timeout_s: float = 5.0) -> None:
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        await asyncio.sleep(0.02)
    raise AssertionError("Timed out waiting for streaming server to listen")


def _jwt_keypair() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem


def _issue_token(
    *,
    private_pem: str,
    issuer: str,
    audience: str,
    tenant_id: str,
    subject_id: str,
) -> str:
    claims = {
        "iss": issuer,
        "aud": audience,
        "exp": int(time.time()) + 60,
        "tenant_id": tenant_id,
        "sub": subject_id,
    }
    token = jwt.encode({"alg": "RS256", "typ": "JWT"}, claims, private_pem.encode("utf-8"))
    if isinstance(token, bytes):
        return token.decode("utf-8")
    return str(token)


def _run(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        return asyncio.run(value)
    return value


def test_streaming_jwt_connect_and_tenant_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    private_pem, public_pem = _jwt_keypair()

    issuer = "https://issuer.example"
    audience = "gsd"

    monkeypatch.setenv("GSD_STREAMING_AUTH_MODE", "jwt")
    monkeypatch.setenv("GSD_JWT_PUBLIC_KEY", public_pem)
    monkeypatch.setenv("GSD_JWT_ISSUER", issuer)
    monkeypatch.setenv("GSD_JWT_AUDIENCE", audience)
    monkeypatch.setenv("GSD_JWT_TENANT_ID_CLAIM", "tenant_id")
    monkeypatch.setenv("GSD_JWT_SUBJECT_ID_CLAIM", "sub")

    port = _free_port()
    runtime = create_streaming_app(settings=Settings())

    # Create a session owned by tenant-a so join_session can enforce authorization.
    session_id = "sess-test-1"
    runtime.registry.create_session(
        session_id=session_id,
        owner_tenant_id="tenant-a",
        owner_subject_id="sub-a",
        worker_id="w1",
        stream_url="http://127.0.0.1",
    )
    runtime.control_state.set_active_session(session_id=session_id)

    async def _exercise() -> None:
        config = uvicorn.Config(
            runtime.asgi_app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
        )
        server = uvicorn.Server(config)
        task = asyncio.create_task(server.serve())
        try:
            await _wait_port(port)

            # Missing token should fail the Socket.IO connect.
            bad = socketio.AsyncClient()
            with pytest.raises(SocketIOConnectionError):
                await bad.connect(
                    f"http://127.0.0.1:{port}",
                    namespaces=["/stream"],
                    transports=["websocket"],
                )
            try:
                await bad.disconnect()
            except Exception:
                pass

            # Valid token can connect and join its tenant session.
            token_ok = _issue_token(
                private_pem=private_pem,
                issuer=issuer,
                audience=audience,
                tenant_id="tenant-a",
                subject_id="sub-a",
            )
            client = socketio.AsyncClient()
            await client.connect(
                f"http://127.0.0.1:{port}",
                namespaces=["/stream"],
                transports=["websocket"],
                auth={"token": token_ok},
            )
            join = await client.call(
                "join_session",
                {"session_id": session_id},
                namespace="/stream",
                timeout=2.0,
            )
            assert join == {"ok": True, "session_id": session_id}
            await client.disconnect()

            # Wrong-tenant token can connect, but join_session is denied.
            token_wrong = _issue_token(
                private_pem=private_pem,
                issuer=issuer,
                audience=audience,
                tenant_id="tenant-b",
                subject_id="sub-b",
            )
            other = socketio.AsyncClient()
            await other.connect(
                f"http://127.0.0.1:{port}",
                namespaces=["/stream", "/ctrl"],
                transports=["websocket"],
                auth={"token": token_wrong},
            )
            denied = await other.call(
                "join_session",
                {"session_id": session_id},
                namespace="/stream",
                timeout=2.0,
            )
            assert denied.get("ok") is False
            assert denied.get("error") == "forbidden"

            ctrl = await other.call(
                "take_control",
                {"session_id": session_id},
                namespace="/ctrl",
                timeout=2.0,
            )
            assert ctrl.get("ok") is False
            assert ctrl.get("error") == "forbidden"
            await other.disconnect()
        finally:
            server.should_exit = True
            await task

    _run(_exercise())
