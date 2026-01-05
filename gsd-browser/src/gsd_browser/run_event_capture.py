"""Event capture helpers for populating the RunEventStore during web_eval_agent runs."""

from __future__ import annotations

import inspect
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .run_event_store import RunEventStore


def _now_ts() -> float:
    return datetime.now(UTC).timestamp()


def _format_console_args(args: list[dict[str, Any]] | None) -> str:
    if not args:
        return ""
    parts: list[str] = []
    for arg in args:
        if not isinstance(arg, dict):
            parts.append(str(arg))
            continue
        if "value" in arg and arg["value"] is not None:
            parts.append(str(arg["value"]))
            continue
        description = arg.get("description")
        if description:
            parts.append(str(description))
            continue
        arg_type = arg.get("type")
        if arg_type:
            parts.append(f"<{arg_type}>")
            continue
        parts.append("<arg>")
    return " ".join(parts).strip()


def _safe_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
    except Exception:  # noqa: BLE001
        return url
    if not parsed.scheme or not parsed.netloc:
        return url
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "", "", ""))


def _extract_stack_location(stack: dict[str, Any] | None) -> dict[str, Any] | None:
    if not stack:
        return None
    frames = stack.get("callFrames")
    if not isinstance(frames, list) or not frames:
        return None
    frame = frames[0]
    if not isinstance(frame, dict):
        return None

    location: dict[str, Any] = {}
    if frame.get("url"):
        location["url"] = _safe_url(str(frame["url"]))
    if frame.get("functionName"):
        location["function"] = str(frame["functionName"])
    if frame.get("lineNumber") is not None:
        try:
            location["line"] = int(frame["lineNumber"]) + 1
        except Exception:  # noqa: BLE001
            pass
    if frame.get("columnNumber") is not None:
        try:
            location["column"] = int(frame["columnNumber"]) + 1
        except Exception:  # noqa: BLE001
            pass
    return location or None


Handler = Callable[[Any, str | None], Any]


@dataclass
class _RegisteredHandler:
    method: str
    previous: Handler | None


class CDPRunEventCapture:
    """Tap CDP Runtime/Network events and record bounded run events.

    Notes:
    - cdp_use's EventRegistry supports a single handler per method; this class wraps any
      existing handler so we don't clobber upstream logic.
    - We intentionally avoid capturing response bodies.
    """

    def __init__(
        self, *, store: RunEventStore, session_id: str, max_pending_requests: int = 2000
    ) -> None:
        self._store = store
        self._session_id = session_id
        self._register_router: _CDPClientRouter | None = None
        self._register_mode = False
        self._registered: list[_RegisteredHandler] = []
        self._pending_requests: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._max_pending_requests = max(0, max_pending_requests)

    def attach(self, cdp_client: Any) -> None:
        if self._try_attach_via_register(cdp_client):
            return

        registry = getattr(cdp_client, "_event_registry", None)
        handlers = getattr(registry, "_handlers", None) if registry else None
        if not isinstance(handlers, dict):
            return

        self._wrap_handler(handlers, "Runtime.consoleAPICalled", self._on_console_api_called)
        self._wrap_handler(handlers, "Runtime.exceptionThrown", self._on_exception_thrown)
        self._wrap_handler(handlers, "Network.requestWillBeSent", self._on_request_will_be_sent)
        self._wrap_handler(handlers, "Network.responseReceived", self._on_response_received)
        self._wrap_handler(handlers, "Network.loadingFinished", self._on_loading_finished)
        self._wrap_handler(handlers, "Network.loadingFailed", self._on_loading_failed)

    def detach(self, cdp_client: Any) -> None:
        if self._register_mode and self._register_router is not None:
            if self._register_router.active_capture is self:
                self._register_router.active_capture = None
            self._register_router = None
            self._register_mode = False
            self._pending_requests.clear()
            return

        registry = getattr(cdp_client, "_event_registry", None)
        handlers = getattr(registry, "_handlers", None) if registry else None
        if not isinstance(handlers, dict):
            return
        for entry in reversed(self._registered):
            if entry.previous is None:
                handlers.pop(entry.method, None)
            else:
                handlers[entry.method] = entry.previous
        self._registered.clear()
        self._pending_requests.clear()

    def _wrap_handler(self, handlers: dict[str, Handler], method: str, ours: Handler) -> None:
        previous = handlers.get(method)

        async def wrapper(params: Any, cdp_session_id: str | None) -> None:
            if previous is not None:
                if inspect.iscoroutinefunction(previous):
                    await previous(params, cdp_session_id)
                else:
                    previous(params, cdp_session_id)

            if inspect.iscoroutinefunction(ours):
                await ours(params, cdp_session_id)
            else:
                ours(params, cdp_session_id)

        handlers[method] = wrapper
        self._registered.append(_RegisteredHandler(method=method, previous=previous))

    def _try_attach_via_register(self, cdp_client: Any) -> bool:
        register = getattr(cdp_client, "register", None)
        runtime = getattr(register, "Runtime", None) if register is not None else None
        network = getattr(register, "Network", None) if register is not None else None

        register_console = (
            getattr(runtime, "consoleAPICalled", None) if runtime is not None else None
        )
        register_exception = (
            getattr(runtime, "exceptionThrown", None) if runtime is not None else None
        )
        register_request = (
            getattr(network, "requestWillBeSent", None) if network is not None else None
        )
        register_response = (
            getattr(network, "responseReceived", None) if network is not None else None
        )
        register_finished = (
            getattr(network, "loadingFinished", None) if network is not None else None
        )
        register_failed = getattr(network, "loadingFailed", None) if network is not None else None

        if not all(
            callable(fn)
            for fn in (
                register_console,
                register_exception,
                register_request,
                register_response,
                register_finished,
                register_failed,
            )
        ):
            return False

        client_id = id(cdp_client)
        router = _REGISTER_ROUTERS_BY_ID.get(client_id)
        if router is None:
            router = _CDPClientRouter()
            _REGISTER_ROUTERS_BY_ID[client_id] = router

        router.active_capture = self
        self._register_router = router
        self._register_mode = True

        if router.registered:
            return True

        def _handle_console(event: Any, cdp_session_id: str | None = None) -> None:
            capture = router.active_capture
            if capture is None:
                return
            capture._on_console_api_called(event if isinstance(event, dict) else {}, cdp_session_id)

        def _handle_exception(event: Any, cdp_session_id: str | None = None) -> None:
            capture = router.active_capture
            if capture is None:
                return
            capture._on_exception_thrown(event if isinstance(event, dict) else {}, cdp_session_id)

        def _handle_request(event: Any, cdp_session_id: str | None = None) -> None:
            capture = router.active_capture
            if capture is None:
                return
            capture._on_request_will_be_sent(
                event if isinstance(event, dict) else {}, cdp_session_id
            )

        def _handle_response(event: Any, cdp_session_id: str | None = None) -> None:
            capture = router.active_capture
            if capture is None:
                return
            capture._on_response_received(event if isinstance(event, dict) else {}, cdp_session_id)

        def _handle_finished(event: Any, cdp_session_id: str | None = None) -> None:
            capture = router.active_capture
            if capture is None:
                return
            capture._on_loading_finished(event if isinstance(event, dict) else {}, cdp_session_id)

        def _handle_failed(event: Any, cdp_session_id: str | None = None) -> None:
            capture = router.active_capture
            if capture is None:
                return
            capture._on_loading_failed(event if isinstance(event, dict) else {}, cdp_session_id)

        register_console(_handle_console)
        register_exception(_handle_exception)
        register_request(_handle_request)
        register_response(_handle_response)
        register_finished(_handle_finished)
        register_failed(_handle_failed)

        router.registered = True
        return True

    def _on_console_api_called(self, event: dict[str, Any], _: str | None) -> None:
        level = str(event.get("type") or "log")
        message = _format_console_args(
            event.get("args") if isinstance(event.get("args"), list) else None
        )
        location = _extract_stack_location(
            event.get("stackTrace") if isinstance(event.get("stackTrace"), dict) else None
        )
        self._store.record_console_event(
            self._session_id,
            captured_at=_now_ts(),
            level=level,
            message=message,
            location=location,
        )

    def _on_exception_thrown(self, event: dict[str, Any], _: str | None) -> None:
        details = (
            event.get("exceptionDetails") if isinstance(event.get("exceptionDetails"), dict) else {}
        )
        message = str(details.get("text") or "Unhandled exception")
        exception = details.get("exception") if isinstance(details.get("exception"), dict) else None
        if exception:
            description = exception.get("description") or exception.get("value")
            if description:
                message = f"{message}: {description}"
        location: dict[str, Any] = {}
        if details.get("url"):
            location["url"] = _safe_url(str(details["url"]))
        if details.get("lineNumber") is not None:
            try:
                location["line"] = int(details["lineNumber"]) + 1
            except Exception:  # noqa: BLE001
                pass
        if details.get("columnNumber") is not None:
            try:
                location["column"] = int(details["columnNumber"]) + 1
            except Exception:  # noqa: BLE001
                pass
        stack_location = _extract_stack_location(
            details.get("stackTrace") if isinstance(details.get("stackTrace"), dict) else None
        )
        if stack_location:
            location.update(stack_location)

        self._store.record_console_event(
            self._session_id,
            captured_at=_now_ts(),
            level="exception",
            message=message,
            location=location or None,
        )

    def _on_request_will_be_sent(self, event: dict[str, Any], _: str | None) -> None:
        request_id = event.get("requestId")
        request = event.get("request") if isinstance(event.get("request"), dict) else None
        if not request_id or not request:
            return
        url = str(request.get("url") or "")
        method = str(request.get("method") or "")
        start_ts = event.get("timestamp")
        entry = {"method": method, "url": _safe_url(url), "start_ts": start_ts}

        if request_id in self._pending_requests:
            self._pending_requests.move_to_end(request_id)
        self._pending_requests[request_id] = entry
        if self._max_pending_requests and len(self._pending_requests) > self._max_pending_requests:
            self._pending_requests.popitem(last=False)

    def _on_response_received(self, event: dict[str, Any], _: str | None) -> None:
        request_id = event.get("requestId")
        response = event.get("response") if isinstance(event.get("response"), dict) else None
        if not request_id or request_id not in self._pending_requests or not response:
            return
        entry = self._pending_requests[request_id]
        entry["status"] = response.get("status")
        entry["response_ts"] = event.get("timestamp")
        self._pending_requests.move_to_end(request_id)

    def _on_loading_finished(self, event: dict[str, Any], _: str | None) -> None:
        request_id = event.get("requestId")
        if not request_id or request_id not in self._pending_requests:
            return
        entry = self._pending_requests.pop(request_id)
        end_ts = event.get("timestamp")
        duration_ms = None
        if isinstance(entry.get("start_ts"), (int, float)) and isinstance(end_ts, (int, float)):
            duration_ms = max(0.0, (float(end_ts) - float(entry["start_ts"])) * 1000.0)
        self._store.record_network_event(
            self._session_id,
            captured_at=_now_ts(),
            method=str(entry.get("method") or ""),
            url=str(entry.get("url") or ""),
            status=int(entry["status"]) if isinstance(entry.get("status"), (int, float)) else None,
            duration_ms=duration_ms,
        )

    def _on_loading_failed(self, event: dict[str, Any], _: str | None) -> None:
        request_id = event.get("requestId")
        if not request_id or request_id not in self._pending_requests:
            return
        entry = self._pending_requests.pop(request_id)
        end_ts = event.get("timestamp")
        duration_ms = None
        if isinstance(entry.get("start_ts"), (int, float)) and isinstance(end_ts, (int, float)):
            duration_ms = max(0.0, (float(end_ts) - float(entry["start_ts"])) * 1000.0)
        error_text = event.get("errorText") or event.get("blockedReason") or "failed"
        self._store.record_network_event(
            self._session_id,
            captured_at=_now_ts(),
            method=str(entry.get("method") or ""),
            url=str(entry.get("url") or ""),
            status=int(entry["status"]) if isinstance(entry.get("status"), (int, float)) else None,
            duration_ms=duration_ms,
            error=str(error_text),
        )


class _CDPClientRouter:
    def __init__(self) -> None:
        self.registered = False
        self.active_capture: CDPRunEventCapture | None = None


_REGISTER_ROUTERS_BY_ID: dict[int, _CDPClientRouter] = {}
