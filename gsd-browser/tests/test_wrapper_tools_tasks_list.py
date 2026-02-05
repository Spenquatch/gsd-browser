from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import fastmcp
import pytest
from fastmcp import Client
from fastmcp.server.auth import AccessToken

from gsd_browser.contracts.v1 import TasksAdminListPayloadV1, TasksListPayloadV1
from gsd_browser.optionb import task_ownership
from gsd_browser.optionb.fastmcp_server import GsdFastMCP
from gsd_browser.optionb.identity import Identity


def _configure_memory_docket(monkeypatch: pytest.MonkeyPatch, *, label: str) -> None:
    monkeypatch.setattr(fastmcp.settings.docket, "url", f"memory://{label}")
    monkeypatch.setattr(fastmcp.settings.docket, "name", f"gsd-{label}")


def _register_wrapper_tools(server: GsdFastMCP) -> None:
    from gsd_browser.fastmcp_v2_stdio import tasks_admin_list, tasks_list

    server.tool(name="tasks_list")(tasks_list.fn)
    server.tool(name="tasks_admin_list")(tasks_admin_list.fn)


def test_tasks_list_wrapper_is_identity_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_memory_docket(monkeypatch, label="wrapper-tasks-list-identity-scope")

    from fastmcp.server import dependencies

    server = GsdFastMCP("wrapper-test", tasks=True)
    _register_wrapper_tools(server)

    identity_a = Identity(tenant_id="t1", subject_id="s1", transport="http")
    identity_b = Identity(tenant_id="t2", subject_id="s2", transport="http")

    token_a = AccessToken(
        token="t",
        client_id="c",
        scopes=[],
        claims={"tenant_id": "t1", "sub": "s1", "scope": "gsd:browser:read"},
    )
    monkeypatch.setattr(dependencies, "get_access_token", lambda: token_a)

    task_a1 = str(uuid4())
    task_a2 = str(uuid4())
    task_b1 = str(uuid4())
    session_a = str(uuid4())
    session_b = str(uuid4())
    base_ms = 2_000_000_000_000

    async def run() -> None:
        async with Client(server) as client:
            docket = server.docket
            assert docket is not None
            store = task_ownership.TaskOwnershipStore(docket_getter=lambda: docket)

            await store.write(
                task_ownership.build_record(
                    task_id=task_a1,
                    tool_name="web_eval_agent",
                    identity=identity_a,
                    session_id=session_a,
                    ttl_ms=60_000,
                    created_at_ms=base_ms + 2000,
                )
            )
            await store.write(
                task_ownership.build_record(
                    task_id=task_a2,
                    tool_name="web_task_agent",
                    identity=identity_a,
                    session_id=session_a,
                    ttl_ms=60_000,
                    created_at_ms=base_ms + 1000,
                )
            )
            await store.write(
                task_ownership.build_record(
                    task_id=task_b1,
                    tool_name="web_task_agent",
                    identity=identity_b,
                    session_id=session_b,
                    ttl_ms=60_000,
                    created_at_ms=base_ms + 3000,
                )
            )

            result = await client.call_tool_mcp(name="tasks_list", arguments={"limit": 100})
            payload = json.loads(result.content[0].text)
            validated = TasksListPayloadV1.model_validate(payload)
            assert {str(item.task_id) for item in validated.tasks} == {task_a1, task_a2}
            assert validated.error is None

    asyncio.run(run())


def test_tasks_admin_list_wrapper_is_gated_by_admin_mode_and_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_memory_docket(monkeypatch, label="wrapper-tasks-admin-list-gating")

    from fastmcp.server import dependencies

    server = GsdFastMCP("wrapper-test", tasks=True)
    _register_wrapper_tools(server)

    task_id = str(uuid4())
    session_id = str(uuid4())
    identity = Identity(tenant_id="t1", subject_id="s1", transport="http")

    token_read_only = AccessToken(
        token="t",
        client_id="c",
        scopes=[],
        claims={"tenant_id": "t1", "sub": "s1", "scope": "gsd:browser:read"},
    )
    token_admin = AccessToken(
        token="t",
        client_id="c",
        scopes=[],
        claims={"tenant_id": "t1", "sub": "s1", "scope": "gsd:admin"},
    )

    current_token = token_read_only
    monkeypatch.setattr(dependencies, "get_access_token", lambda: current_token)

    async def run() -> None:
        nonlocal current_token
        async with Client(server) as client:
            docket = server.docket
            assert docket is not None
            store = task_ownership.TaskOwnershipStore(docket_getter=lambda: docket)
            await store.write(
                task_ownership.build_record(
                    task_id=task_id,
                    tool_name="web_eval_agent",
                    identity=identity,
                    session_id=session_id,
                    ttl_ms=60_000,
                    created_at_ms=2_000_000_000_000,
                )
            )

            monkeypatch.delenv("GSD_ADMIN_MODE", raising=False)
            result_disabled = await client.call_tool_mcp(
                name="tasks_admin_list", arguments={"limit": 100}
            )
            payload_disabled = json.loads(result_disabled.content[0].text)
            validated_disabled = TasksAdminListPayloadV1.model_validate(payload_disabled)
            assert validated_disabled.tasks == []
            assert validated_disabled.error is not None
            assert validated_disabled.error.code == "admin_disabled"

            monkeypatch.setenv("GSD_ADMIN_MODE", "1")
            result_forbidden = await client.call_tool_mcp(
                name="tasks_admin_list", arguments={"limit": 100}
            )
            payload_forbidden = json.loads(result_forbidden.content[0].text)
            validated_forbidden = TasksAdminListPayloadV1.model_validate(payload_forbidden)
            assert validated_forbidden.tasks == []
            assert validated_forbidden.error is not None
            assert validated_forbidden.error.code == "forbidden"

            current_token = token_admin
            result_ok = await client.call_tool_mcp(
                name="tasks_admin_list", arguments={"limit": 100}
            )
            payload_ok = json.loads(result_ok.content[0].text)
            validated_ok = TasksAdminListPayloadV1.model_validate(payload_ok)
            assert validated_ok.error is None
            assert {str(item.task_id) for item in validated_ok.tasks} == {task_id}

    asyncio.run(run())
