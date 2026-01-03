"""CDP input dispatch helpers for take-control (/ctrl) events."""

from __future__ import annotations

import inspect
import logging
from typing import Any

logger = logging.getLogger("gsd_browser.streaming")


_MODIFIER_BITS: dict[str, int] = {"alt": 1, "ctrl": 2, "meta": 4, "shift": 8}


def _payload_bool(payload: dict[str, Any], *keys: str) -> bool:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            return value
    return False


def _modifiers_from_payload(payload: dict[str, Any]) -> int:
    explicit = payload.get("modifiers")
    if isinstance(explicit, int):
        return explicit
    modifiers = 0
    if _payload_bool(payload, "alt", "altKey"):
        modifiers |= _MODIFIER_BITS["alt"]
    if _payload_bool(payload, "ctrl", "ctrlKey", "control"):
        modifiers |= _MODIFIER_BITS["ctrl"]
    if _payload_bool(payload, "meta", "metaKey"):
        modifiers |= _MODIFIER_BITS["meta"]
    if _payload_bool(payload, "shift", "shiftKey"):
        modifiers |= _MODIFIER_BITS["shift"]
    return modifiers


_SPECIAL_VKEYS: dict[str, int] = {
    "Backspace": 8,
    "Tab": 9,
    "Enter": 13,
    "Shift": 16,
    "Control": 17,
    "Alt": 18,
    "Pause": 19,
    "CapsLock": 20,
    "Escape": 27,
    "Space": 32,
    "PageUp": 33,
    "PageDown": 34,
    "End": 35,
    "Home": 36,
    "ArrowLeft": 37,
    "ArrowUp": 38,
    "ArrowRight": 39,
    "ArrowDown": 40,
    "Insert": 45,
    "Delete": 46,
    "Meta": 91,
}


def _virtual_key_code(key: str) -> int:
    if key in _SPECIAL_VKEYS:
        return _SPECIAL_VKEYS[key]

    if len(key) == 1:
        char = key
        if "a" <= char <= "z" or "A" <= char <= "Z":
            return ord(char.upper())
        if "0" <= char <= "9":
            return ord(char)
        if ord(char) < 128:
            return ord(char)
    return 0


def _default_code_for_key(key: str) -> str | None:
    if key == " ":
        return "Space"
    if key == "Space":
        return "Space"
    if key in _SPECIAL_VKEYS:
        return key
    if len(key) == 1:
        char = key
        if "a" <= char <= "z" or "A" <= char <= "Z":
            return f"Key{char.upper()}"
        if "0" <= char <= "9":
            return f"Digit{char}"
    return None


async def _cdp_send(cdp_client: Any, method: str, params: dict[str, Any]) -> None:
    send = getattr(cdp_client, "send", None)
    if send is None:
        raise RuntimeError("cdp_client_missing_send")

    result = send(method, params)
    if inspect.isawaitable(result):
        await result


def _mouse_button(button: str) -> str:
    if button == "right":
        return "right"
    if button == "middle":
        return "middle"
    return "left"


def _modifier_bit_for_key(*, key: str, code: str | None = None) -> int:
    normalized_key = key.strip()
    normalized_code = (code or "").strip()
    if normalized_key in {"Shift"} or normalized_code.startswith("Shift"):
        return _MODIFIER_BITS["shift"]
    if normalized_key in {"Control", "Ctrl"} or normalized_code.startswith("Control"):
        return _MODIFIER_BITS["ctrl"]
    if normalized_key in {"Alt"} or normalized_code.startswith("Alt"):
        return _MODIFIER_BITS["alt"]
    if normalized_key in {"Meta"} or normalized_code.startswith(("Meta", "OS")):
        return _MODIFIER_BITS["meta"]
    return 0


class CDPInputDispatcher:
    """Stateful CDP input dispatcher to preserve modifier semantics across events."""

    def __init__(self, *, cdp_client: Any) -> None:
        self._cdp_client = cdp_client
        self._held_modifiers = 0

    async def dispatch(self, event: str, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            payload = {}

        key = str(payload.get("key") or "")
        code = payload.get("code")
        code_str = str(code) if isinstance(code, str) else ""
        modifier_bit = _modifier_bit_for_key(key=key, code=code_str)

        if event == "input_keydown" and modifier_bit:
            self._held_modifiers |= modifier_bit
        elif event == "input_keyup" and modifier_bit:
            self._held_modifiers &= ~modifier_bit

        combined_modifiers = self._held_modifiers | _modifiers_from_payload(payload)
        if event == "input_keyup" and modifier_bit:
            combined_modifiers &= ~modifier_bit
        elif event == "input_keydown" and modifier_bit:
            combined_modifiers |= modifier_bit

        merged_payload = dict(payload)
        merged_payload["modifiers"] = combined_modifiers
        await dispatch_ctrl_input_event(
            cdp_client=self._cdp_client, event=event, payload=merged_payload
        )

    async def dispatch_input(self, event: str, payload: dict[str, Any]) -> None:
        await self.dispatch(event, payload)


async def dispatch_ctrl_input_event(
    *, cdp_client: Any, event: str, payload: dict[str, Any]
) -> None:
    """Dispatch a validated /ctrl input event to the active CDP target."""

    modifiers = _modifiers_from_payload(payload)

    if event in {"input_move", "input_click", "input_wheel"}:
        x = float(payload.get("x", 0.0))
        y = float(payload.get("y", 0.0))

        if event == "input_move":
            await _cdp_send(
                cdp_client,
                "Input.dispatchMouseEvent",
                {"type": "mouseMoved", "x": x, "y": y, "modifiers": modifiers},
            )
            return

        if event == "input_wheel":
            await _cdp_send(
                cdp_client,
                "Input.dispatchMouseEvent",
                {
                    "type": "mouseWheel",
                    "x": x,
                    "y": y,
                    "deltaX": float(payload.get("delta_x", 0.0)),
                    "deltaY": float(payload.get("delta_y", 0.0)),
                    "modifiers": modifiers,
                },
            )
            return

        button = _mouse_button(str(payload.get("button") or "left"))
        click_count = int(payload.get("click_count") or 1)
        await _cdp_send(
            cdp_client,
            "Input.dispatchMouseEvent",
            {
                "type": "mousePressed",
                "x": x,
                "y": y,
                "button": button,
                "clickCount": click_count,
                "modifiers": modifiers,
            },
        )
        await _cdp_send(
            cdp_client,
            "Input.dispatchMouseEvent",
            {
                "type": "mouseReleased",
                "x": x,
                "y": y,
                "button": button,
                "clickCount": click_count,
                "modifiers": modifiers,
            },
        )
        return

    if event in {"input_keydown", "input_keyup"}:
        key = str(payload.get("key") or "")
        if not key:
            return

        code = payload.get("code")
        if not isinstance(code, str) or not code:
            code = _default_code_for_key(key)

        repeat = payload.get("repeat")
        auto_repeat = bool(repeat) if isinstance(repeat, bool) else None

        vkey = _virtual_key_code(key)
        base: dict[str, Any] = {
            "key": key,
            "code": code,
            "modifiers": modifiers,
            "windowsVirtualKeyCode": vkey,
            "nativeVirtualKeyCode": vkey,
        }
        if auto_repeat is not None:
            base["autoRepeat"] = auto_repeat

        if event == "input_keyup":
            await _cdp_send(cdp_client, "Input.dispatchKeyEvent", {"type": "keyUp", **base})
            return

        if key == "Enter":
            await _cdp_send(
                cdp_client,
                "Input.dispatchKeyEvent",
                {
                    "type": "rawKeyDown",
                    **base,
                },
            )
            await _cdp_send(
                cdp_client,
                "Input.dispatchKeyEvent",
                {
                    "type": "char",
                    "text": "\r",
                    "unmodifiedText": "\r",
                    "modifiers": modifiers,
                    "windowsVirtualKeyCode": base["windowsVirtualKeyCode"],
                    "nativeVirtualKeyCode": base["nativeVirtualKeyCode"],
                    "key": key,
                    "code": code,
                },
            )
            return

        key_type = "rawKeyDown" if key in _SPECIAL_VKEYS else "keyDown"
        await _cdp_send(cdp_client, "Input.dispatchKeyEvent", {"type": key_type, **base})
        return

    if event == "input_type":
        text = payload.get("text")
        if not isinstance(text, str) or not text:
            return

        for char in text:
            if char in {"\n", "\r"}:
                await dispatch_ctrl_input_event(
                    cdp_client=cdp_client,
                    event="input_keydown",
                    payload={"key": "Enter", "modifiers": modifiers},
                )
                await dispatch_ctrl_input_event(
                    cdp_client=cdp_client,
                    event="input_keyup",
                    payload={"key": "Enter", "modifiers": modifiers},
                )
                continue

            vkey = _virtual_key_code(char)
            params: dict[str, Any] = {
                "type": "char",
                "text": char,
                "unmodifiedText": char,
                "modifiers": modifiers,
            }
            if vkey:
                params["windowsVirtualKeyCode"] = vkey
                params["nativeVirtualKeyCode"] = vkey
                params["key"] = char
                params["code"] = _default_code_for_key(char)

            await _cdp_send(cdp_client, "Input.dispatchKeyEvent", params)
        return

    logger.debug("Unhandled ctrl input event", extra={"event": event})
