from __future__ import annotations

import asyncio

import fastmcp
import pytest
from fastmcp import Client

from gsd_browser.optionb import task_ownership
from gsd_browser.optionb.identity import Identity
from gsd_browser.optionb.ops_tasks import (
    OpsTasksListQuery,
    OpsTasksService,
    OpsTasksServiceError,
)


def _configure_memory_docket(monkeypatch: pytest.MonkeyPatch, *, label: str) -> None:
    monkeypatch.setattr(fastmcp.settings.docket, "url", f"memory://{label}")
    monkeypatch.setattr(fastmcp.settings.docket, "name", f"gsd-{label}")


def test_ops_tasks_list_is_identity_scoped_and_sorted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_memory_docket(monkeypatch, label="ops-tasks-list-scope-order")

    from gsd_browser.optionb.fastmcp_server import GsdFastMCP

    server = GsdFastMCP("ops-test", tasks=True)

    identity_a = Identity(tenant_id="t1", subject_id="s1", transport="stdio")
    identity_b = Identity(tenant_id="t2", subject_id="s2", transport="http")
    base_ms = 2_000_000_000_000

    async def run() -> None:
        async with Client(server):
            docket = server.docket
            assert docket is not None
            store = task_ownership.TaskOwnershipStore(docket_getter=lambda: docket)
            ops = OpsTasksService(docket_getter=lambda: docket, now_ms=lambda: 0)

            await store.write(
                task_ownership.build_record(
                    task_id="task_c",
                    tool_name="web_eval_agent",
                    identity=identity_a,
                    session_id="sess-a",
                    ttl_ms=60_000,
                    created_at_ms=base_ms + 3000,
                )
            )
            await store.write(
                task_ownership.build_record(
                    task_id="task_b",
                    tool_name="web_task_agent",
                    identity=identity_a,
                    session_id="sess-a",
                    ttl_ms=60_000,
                    created_at_ms=base_ms + 2000,
                )
            )
            await store.write(
                task_ownership.build_record(
                    task_id="task_a",
                    tool_name="web_task_agent",
                    identity=identity_a,
                    session_id="sess-a",
                    ttl_ms=60_000,
                    created_at_ms=base_ms + 2000,
                )
            )
            await store.write(
                task_ownership.build_record(
                    task_id="task_z",
                    tool_name="web_task_agent",
                    identity=identity_b,
                    session_id="sess-b",
                    ttl_ms=60_000,
                    created_at_ms=base_ms + 4000,
                )
            )

            resp = await ops.list_tasks(identity=identity_a, query=OpsTasksListQuery(limit=100))
            assert [t.task_id for t in resp.tasks] == ["task_c", "task_b", "task_a"]
            assert resp.next_cursor is None

    asyncio.run(run())


def test_ops_tasks_list_cursor_is_bound_to_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_memory_docket(monkeypatch, label="ops-tasks-list-cursor-binding")

    from gsd_browser.optionb.fastmcp_server import GsdFastMCP

    server = GsdFastMCP("ops-test", tasks=True)

    identity = Identity(tenant_id="t1", subject_id="s1", transport="stdio")
    base_ms = 2_000_000_000_000

    async def run() -> None:
        async with Client(server):
            docket = server.docket
            assert docket is not None
            store = task_ownership.TaskOwnershipStore(docket_getter=lambda: docket)
            ops = OpsTasksService(docket_getter=lambda: docket, now_ms=lambda: 0)

            await store.write(
                task_ownership.build_record(
                    task_id="task_2",
                    tool_name="web_eval_agent",
                    identity=identity,
                    session_id="sess",
                    ttl_ms=60_000,
                    created_at_ms=base_ms + 2000,
                )
            )
            await store.write(
                task_ownership.build_record(
                    task_id="task_1",
                    tool_name="web_task_agent",
                    identity=identity,
                    session_id="sess",
                    ttl_ms=60_000,
                    created_at_ms=base_ms + 1000,
                )
            )

            first = await ops.list_tasks(identity=identity, query=OpsTasksListQuery(limit=1))
            assert len(first.tasks) == 1
            assert first.next_cursor

            with pytest.raises(OpsTasksServiceError) as exc:
                _ = await ops.list_tasks(
                    identity=identity,
                    query=OpsTasksListQuery(
                        limit=1,
                        cursor=first.next_cursor,
                        tool_name="web_eval_agent",
                    ),
                )
            assert exc.value.code == "invalid_cursor"

    asyncio.run(run())


def test_ops_tasks_list_limit_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_memory_docket(monkeypatch, label="ops-tasks-list-limit-validation")

    from gsd_browser.optionb.fastmcp_server import GsdFastMCP

    server = GsdFastMCP("ops-test", tasks=True)

    identity = Identity(tenant_id="t1", subject_id="s1", transport="stdio")

    async def run() -> None:
        async with Client(server):
            docket = server.docket
            assert docket is not None
            ops = OpsTasksService(docket_getter=lambda: docket, now_ms=lambda: 0)

            with pytest.raises(OpsTasksServiceError) as exc:
                _ = await ops.list_tasks(identity=identity, query=OpsTasksListQuery(limit=0))
            assert exc.value.code == "invalid_limit"

            with pytest.raises(OpsTasksServiceError) as exc2:
                _ = await ops.list_tasks(identity=identity, query=OpsTasksListQuery(limit=1001))
            assert exc2.value.code == "invalid_limit"

    asyncio.run(run())


def test_ops_tasks_list_paginates_in_pinned_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_memory_docket(monkeypatch, label="ops-tasks-list-pagination-order")

    from gsd_browser.optionb.fastmcp_server import GsdFastMCP

    server = GsdFastMCP("ops-test", tasks=True)

    identity = Identity(tenant_id="t1", subject_id="s1", transport="stdio")
    base_ms = 2_000_000_000_000

    async def run() -> None:
        async with Client(server):
            docket = server.docket
            assert docket is not None
            store = task_ownership.TaskOwnershipStore(docket_getter=lambda: docket)
            ops = OpsTasksService(docket_getter=lambda: docket, now_ms=lambda: 0)

            await store.write(
                task_ownership.build_record(
                    task_id="task_c",
                    tool_name="web_eval_agent",
                    identity=identity,
                    session_id="sess",
                    ttl_ms=60_000,
                    created_at_ms=base_ms + 3000,
                )
            )
            await store.write(
                task_ownership.build_record(
                    task_id="task_b",
                    tool_name="web_eval_agent",
                    identity=identity,
                    session_id="sess",
                    ttl_ms=60_000,
                    created_at_ms=base_ms + 2000,
                )
            )
            await store.write(
                task_ownership.build_record(
                    task_id="task_a",
                    tool_name="web_eval_agent",
                    identity=identity,
                    session_id="sess",
                    ttl_ms=60_000,
                    created_at_ms=base_ms + 2000,
                )
            )

            page1 = await ops.list_tasks(identity=identity, query=OpsTasksListQuery(limit=2))
            assert [t.task_id for t in page1.tasks] == ["task_c", "task_b"]
            assert page1.next_cursor

            page2 = await ops.list_tasks(
                identity=identity, query=OpsTasksListQuery(limit=2, cursor=page1.next_cursor)
            )
            assert [t.task_id for t in page2.tasks] == ["task_a"]
            assert page2.next_cursor is None

    asyncio.run(run())
