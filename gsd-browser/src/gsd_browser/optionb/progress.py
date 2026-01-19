from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Literal, Protocol

Phase = Literal["init", "navigate", "agent_step", "finalize", "done", "cancelled", "failed"]


class TaskProgress(Protocol):
    async def set_total(self, total: int) -> None: ...

    async def increment(self, amount: int = 1) -> None: ...

    async def set_message(self, message: str | None) -> None: ...


@dataclass
class _ProgressState:
    progress: TaskProgress
    max_steps: int | None
    last_step: int = 0
    last_agent_note: str = ""
    total_set: bool = False
    terminal: bool = False
    pending_tasks: set[asyncio.Task[None]] = field(default_factory=set)


_state: ContextVar[_ProgressState | None] = ContextVar("gsd_task_progress", default=None)


def _truncate_note(note: str) -> str:
    normalized = str(note or "")
    if len(normalized) <= 200:
        return normalized
    return normalized[:199] + "…"


def _format_message(*, phase: Phase, step: int | None, note: str) -> str:
    step_value = "null" if step is None else str(int(step))
    return f"phase={phase} step={step_value} note={_truncate_note(note)}"


@contextmanager
def task_progress_scope(*, progress: TaskProgress, max_steps: int | None) -> Iterator[None]:
    token = _state.set(_ProgressState(progress=progress, max_steps=max_steps))
    try:
        yield
    finally:
        _state.reset(token)


async def emit(
    *,
    phase: Phase,
    step: int | None,
    note: str,
) -> None:
    state = _state.get()
    if state is None:
        return

    if state.max_steps is not None and not state.total_set:
        try:
            await state.progress.set_total(int(state.max_steps))
            state.total_set = True
        except Exception:  # noqa: BLE001
            state.total_set = True

    message = _format_message(phase=phase, step=step, note=note)
    await state.progress.set_message(message)
    if phase in {"done", "cancelled", "failed"}:
        state.terminal = True


async def emit_agent_step(*, step: int, note: str) -> None:
    state = _state.get()
    if state is None:
        return
    if state.terminal:
        return

    step_value = int(step)
    state.last_agent_note = str(note or "")
    if state.max_steps is not None:
        delta = step_value - state.last_step
        if delta > 0:
            try:
                await state.progress.increment(delta)
            except Exception:  # noqa: BLE001
                pass
        state.last_step = max(state.last_step, step_value)

    await emit(phase="agent_step", step=step_value, note=note)


async def emit_last_agent_step_snapshot() -> None:
    state = _state.get()
    if state is None or state.terminal:
        return
    if state.last_step <= 0:
        return

    note = state.last_agent_note.strip() or f"step {state.last_step}"
    await emit(phase="agent_step", step=state.last_step, note=note)


def schedule_agent_step(*, step: int | None, note: str | None) -> None:
    state = _state.get()
    if state is None or step is None:
        return
    if state.terminal:
        return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    task = loop.create_task(emit_agent_step(step=int(step), note=str(note or "")))
    state.pending_tasks.add(task)

    def _cleanup(done: asyncio.Task[None]) -> None:
        state.pending_tasks.discard(done)

    task.add_done_callback(_cleanup)


async def drain_pending_agent_steps(*, timeout_s: float = 0.2) -> None:
    state = _state.get()
    if state is None:
        return

    pending = [task for task in tuple(state.pending_tasks) if not task.done()]
    if not pending:
        return

    try:
        await asyncio.wait(pending, timeout=float(timeout_s))
    except Exception:  # noqa: BLE001
        return
