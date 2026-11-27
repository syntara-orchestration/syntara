"""Shared activity identity with real PostgreSQL and independently started paths.

The monitor alone creates AO rows. Temporal metadata, EP HTTP, and Temporal
completion are doubles; row creation and callback lookups use PostgreSQL.
"""

from collections.abc import Generator
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4, uuid5

import pytest
from execution_plane_client.commands.control import CompletionStatus
from execution_plane_client.commands.credentials import CredentialResolveWorkload
from execution_plane_client.commands.results import CredentialResolveWorkloadCommandResult
from execution_plane_client.commands.work import WorkExecute
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.execution_plane.commands import credentials as command_credentials
from syntara.execution_plane.commands.completion import CompletionCommandHandler
from syntara.execution_plane.commands.context import AOCommandContext
from syntara.execution_plane.commands.credentials import CredentialResolveWorkloadCommandHandler
from syntara.workflow_core.models import NodeType
from syntara.workflow_runtime.engines.temporal.activities.ep import ep_dispatch_activity as dispatch
from syntara.workflow_runtime.engines.temporal.services.activity_sync_service import ActivitySyncService
from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution
from syntara.workflows.models.workflow_version import WorkflowVersion

_NODE_ID = "test_activity"
_DEFINITIONS = {
    _NODE_ID: {"type": "script_python"},
    "other_activity": {"type": "http_request"},
}


_PLUGIN_MANIFEST = {
    "spec": {
        "input": {
            "kind": "inline",
            "value": {
                "type": "object",
                "properties": {"code": {"type": "string"}},
            },
        }
    }
}


@pytest.fixture
def ep_submission(
    test_execution: Execution, test_db_session_factory: async_sessionmaker[AsyncSession]
) -> Generator[AsyncMock, None, None]:
    """Accept EP work without creating its AO activity row."""
    info = Mock(
        workflow_id=test_execution.temporal_workflow_id,
        workflow_run_id="test-run",
        activity_id=_NODE_ID,
    )
    with (
        patch.object(activity, "info", return_value=info),
        patch.object(dispatch, "AsyncSessionLocal", test_db_session_factory),
        patch.object(
            dispatch,
            "get_execution_plane_plugin",
            AsyncMock(
                return_value=SimpleNamespace(
                    name="script-bash",
                    node_type=NodeType.SCRIPT_BASH,
                    image_reference="quay.io/example/script-bash:test",
                    step_identity="syntara.script-bash.script-bash",
                    manifest=_PLUGIN_MANIFEST,
                )
            ),
        ),
        patch.object(
            dispatch,
            "execution_plane_plugin_credential_recipe_ids",
            AsyncMock(return_value=("acme.echo.api-token", "acme.echo.workspace-token")),
        ),
        patch.object(dispatch, "ExecutionPlaneHttpClient"),
        patch.object(dispatch, "_submit_and_read_work", return_value={"status": "pending"}) as submission,
    ):
        yield submission


def allow_plugin_recipe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate callback correlation from the built-in script plugin registry."""
    monkeypatch.setattr(
        command_credentials,
        "get_execution_plane_plugin_by_node_type",
        AsyncMock(return_value=SimpleNamespace(name="script-bash")),
    )
    monkeypatch.setattr(
        command_credentials,
        "execution_plane_plugin_credential_recipe_ids",
        AsyncMock(return_value=("acme.echo.api-token",)),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("monitor_first", [False, True])
async def test_monitor_and_dispatch_share_identity_in_either_order(
    test_execution: Execution,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    ep_submission: AsyncMock,
    *,
    monitor_first: bool,
) -> None:
    """An early callback can retry after the monitor creates the matching row."""
    monitor = ActivitySyncService(Mock(), test_db_session_factory, AsyncMock())
    if monitor_first:
        await monitor._create_all_activities_upfront(test_execution.id, _DEFINITIONS)

    assert await dispatch._dispatch_to_ep({"code": "echo ok"}, None, test_execution.id, None, "script-bash") is None
    work_id = UUID(ep_submission.call_args.args[1].command.payload["work_item_id"])
    assert work_id == uuid5(test_execution.id, _NODE_ID)

    temporal = AsyncMock()
    result = {"output": {"return_code": 0, "stdout": "ok", "stderr": ""}}
    async with test_db_session_factory() as reader:
        if not monitor_first:
            assert (
                await reader.exec(select(ActivityExecution).where(ActivityExecution.execution_id == test_execution.id))
            ).all() == []
            delivered = await CompletionCommandHandler()._complete_activity(
                context=AOCommandContext(reader, temporal),
                work_id=work_id,
                status=CompletionStatus.COMPLETED,
                result=result,
                runtime_context=None,
            )
            assert delivered is monitor_first
    if not monitor_first:
        temporal.complete_async_activity.assert_not_awaited()

    await monitor._create_all_activities_upfront(test_execution.id, _DEFINITIONS)
    async with test_db_session_factory() as reader:
        await CompletionCommandHandler()._complete_activity(
            context=AOCommandContext(reader, temporal),
            work_id=work_id,
            status=CompletionStatus.COMPLETED,
            result=result,
            runtime_context=None,
        )
        rows = (
            await reader.exec(select(ActivityExecution).where(ActivityExecution.execution_id == test_execution.id))
        ).all()
        assert {row.activity_name for row in rows} == set(_DEFINITIONS)
        assert all(row.id == uuid5(test_execution.id, row.temporal_activity_id) for row in rows)
        assert next(row.id for row in rows if row.activity_name == _NODE_ID) == work_id
    temporal.complete_async_activity.assert_awaited_with(
        temporal_workflow_id=test_execution.temporal_workflow_id, activity_id=_NODE_ID, result=result
    )


@pytest.mark.asyncio
async def test_monitor_updates_row_created_after_dispatch(
    test_execution: Execution,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    ep_submission: AsyncMock,
) -> None:
    await dispatch._dispatch_to_ep({"code": "echo ok"}, None, test_execution.id, None, "script-bash")
    work_id = UUID(ep_submission.call_args.args[1].command.payload["work_item_id"])
    monitor = ActivitySyncService(Mock(), test_db_session_factory, AsyncMock())
    metadata = await monitor._initialize_monitoring(test_execution.id)
    now = datetime.now(UTC)
    metadata.pending_activity_updates[1] = {
        "activity_id": _NODE_ID,
        "status": ActivityStatus.COMPLETED,
        "started_at": now,
        "completed_at": now,
        "retry_count": 0,
        "error_details": None,
    }
    metadata.pending_sync_event_ids.add(1)
    handle = Mock()
    handle.query = AsyncMock(side_effect=[{"code": "echo ok"}, {"output": {"stdout": "ok"}}])

    await monitor._sync_activities_to_db(metadata, handle)

    async with test_db_session_factory() as reader:
        row = await reader.get(ActivityExecution, work_id)
        assert row is not None
        assert row.status == ActivityStatus.COMPLETED
        assert row.output_data == {"output": {"stdout": "ok"}}


@pytest.mark.asyncio
async def test_dispatch_moves_credential_bindings_out_of_inputs(
    test_execution: Execution,
    ep_submission: AsyncMock,
) -> None:
    first = uuid4()
    second = uuid4()
    input_config = {
        "code": "echo ok",
        "credential_bindings": [
            {"credential_recipe_id": "acme.echo.api-token", "credential_ref": first},
            {"credential_recipe_id": "acme.echo.workspace-token", "credential_ref": second},
        ],
    }

    await dispatch._dispatch_to_ep(input_config, None, test_execution.id, None, "script-bash")

    first_message = ep_submission.call_args.args[1]
    payload = WorkExecute.model_validate(first_message.command.payload)
    assert payload.invocation.inputs == {"code": "echo ok"}
    assert "runtime_context" not in payload.invocation.model_dump()
    assert [
        (binding.credential_recipe_id, binding.credential_ref) for binding in payload.invocation.credential_bindings
    ] == [
        ("acme.echo.api-token", first),
        ("acme.echo.workspace-token", second),
    ]

    await dispatch._dispatch_to_ep(input_config, None, test_execution.id, None, "script-bash")
    second_message = ep_submission.call_args.args[1]
    assert second_message.message_id != first_message.message_id
    assert payload.runtime_context == {
        "execution_id": str(test_execution.id),
        "project_id": str(test_execution.project_id),
        "workflow_id": str(test_execution.workflow_id),
        "temporal_activity_id": _NODE_ID,
    }
    assert second_message.command.payload == first_message.command.payload


@pytest.mark.asyncio
async def test_dispatch_rejects_unresolved_credential_binding_templates(
    test_execution: Execution,
    ep_submission: AsyncMock,
) -> None:
    input_config = {
        "code": "echo ok",
        "credential_bindings": [
            {
                "credential_recipe_id": "acme.echo.api-token",
                "credential_ref": "${trigger.credential}",
            }
        ],
    }

    with pytest.raises(ApplicationError, match="invalid for the Execution Plane command protocol"):
        await dispatch._dispatch_to_ep(input_config, None, test_execution.id, None, "script-bash")

    ep_submission.assert_not_called()


@pytest.mark.asyncio
async def test_loop_body_completion_correlates_canvas_activity(
    test_execution: Execution,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Loop-body work can complete the canvas activity despite its unique Temporal ID."""
    monitor = ActivitySyncService(Mock(), test_db_session_factory, AsyncMock())
    await monitor._create_all_activities_upfront(test_execution.id, _DEFINITIONS)
    loop_activity_id = f"{_NODE_ID}_iter_0"
    info = Mock(
        workflow_id=test_execution.temporal_workflow_id,
        workflow_run_id="test-run",
        activity_id=loop_activity_id,
    )
    with (
        patch.object(activity, "info", return_value=info),
        patch.object(dispatch, "AsyncSessionLocal", test_db_session_factory),
        patch.object(
            dispatch,
            "get_execution_plane_plugin",
            AsyncMock(
                return_value=SimpleNamespace(
                    name="script-bash",
                    node_type=NodeType.SCRIPT_BASH,
                    image_reference="quay.io/example/script-bash:test",
                    step_identity="syntara.script-bash.script-bash",
                    manifest=_PLUGIN_MANIFEST,
                )
            ),
        ),
        patch.object(dispatch, "ExecutionPlaneHttpClient"),
        patch.object(dispatch, "_submit_and_read_work", return_value={"status": "pending"}),
    ):
        assert await dispatch._dispatch_to_ep({"code": "echo ok"}, None, test_execution.id, None, "script-bash") is None

    work_id = uuid5(test_execution.id, loop_activity_id)
    runtime_context: dict[str, object] = {
        "execution_id": str(test_execution.id),
        "temporal_activity_id": loop_activity_id,
    }
    temporal = AsyncMock()
    result = {"output": {"return_code": 0, "stdout": "ok", "stderr": ""}}
    async with test_db_session_factory() as reader:
        delivered = await CompletionCommandHandler()._complete_activity(
            context=AOCommandContext(reader, temporal),
            work_id=work_id,
            status=CompletionStatus.COMPLETED,
            result=result,
            runtime_context=runtime_context,
        )
    assert delivered
    temporal.complete_async_activity.assert_awaited_once_with(
        temporal_workflow_id=test_execution.temporal_workflow_id,
        activity_id=loop_activity_id,
        result=result,
    )

    runtime_context["temporal_activity_id"] = f"{_NODE_ID}_iter_1"
    async with test_db_session_factory() as reader:
        assert not await CompletionCommandHandler()._complete_activity(
            context=AOCommandContext(reader, temporal),
            work_id=work_id,
            status=CompletionStatus.COMPLETED,
            result=result,
            runtime_context=runtime_context,
        )


@pytest.mark.asyncio
async def test_loop_body_credential_resolution_correlates_canvas_activity(
    test_execution: Execution,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Credential commands can resolve loop-body work through runtime context."""
    credential_ref = uuid4()
    async with test_db_session_factory() as session:
        version = await session.get(WorkflowVersion, test_execution.workflow_version_id)
        assert version is not None
        definition = dict(version.workflow_definition)
        nodes = [dict(node) for node in definition["nodes"]]
        target = next(node for node in nodes if node["id"] == _NODE_ID)
        parameters = dict(target.get("parameters", {}))
        parameters["credential_bindings"] = [
            {"credential_recipe_id": "acme.echo.api-token", "credential_ref": str(credential_ref)}
        ]
        target["parameters"] = parameters
        definition["nodes"] = nodes
        version.workflow_definition = definition
        await session.commit()

    monitor = ActivitySyncService(Mock(), test_db_session_factory, AsyncMock())
    await monitor._create_all_activities_upfront(test_execution.id, _DEFINITIONS)

    loop_activity_id = f"{_NODE_ID}_iter_0"
    work_id = uuid5(test_execution.id, loop_activity_id)
    message = CredentialResolveWorkload(
        work_item_id=work_id,
        attempt_id="attempt",
        credential_ref=credential_ref,
        credential_recipe_id="acme.echo.api-token",
        step_revision_id="step-revision",
        runtime_context={
            "execution_id": str(test_execution.id),
            "temporal_activity_id": loop_activity_id,
        },
    ).to_message(
        source_id="execution-plane",
        destination_id="syntara-orchestration",
        client_id="syntara-orchestration",
    )
    payload = CredentialResolveWorkload.model_validate(message.command.payload)
    resolve_document = AsyncMock(return_value={"token": "resolved-token"})
    monkeypatch.setattr(CredentialResolveWorkloadCommandHandler, "_resolve_credential_document", resolve_document)
    allow_plugin_recipe(monkeypatch)

    async with test_db_session_factory() as reader:
        handling = await CredentialResolveWorkloadCommandHandler().handle(
            message,
            payload,
            AOCommandContext(reader, AsyncMock()),
        )

    assert handling.result is not None
    assert isinstance(handling.result, CredentialResolveWorkloadCommandResult)
    assert handling.result.credential == {"token": "resolved-token"}
    assert handling.resource is not None
    assert handling.resource.resource_id == work_id
    resolve_document.assert_awaited_once_with(reader, credential_ref, test_execution.project_id)


@pytest.mark.asyncio
async def test_later_loop_iteration_credential_resolution_selects_active_row(
    test_execution: Execution,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A later callback must not validate against terminal iteration zero."""
    credential_ref = uuid4()
    async with test_db_session_factory() as session:
        version = await session.get(WorkflowVersion, test_execution.workflow_version_id)
        assert version is not None
        definition = dict(version.workflow_definition)
        nodes = [dict(node) for node in definition["nodes"]]
        target = next(node for node in nodes if node["id"] == _NODE_ID)
        parameters = dict(target.get("parameters", {}))
        parameters["credential_bindings"] = [
            {"credential_recipe_id": "acme.echo.api-token", "credential_ref": str(credential_ref)}
        ]
        target["parameters"] = parameters
        definition["nodes"] = nodes
        version.workflow_definition = definition
        await session.commit()

    monitor = ActivitySyncService(Mock(), test_db_session_factory, AsyncMock())
    await monitor._create_all_activities_upfront(test_execution.id, _DEFINITIONS)
    temporal_activity_id = f"{_NODE_ID}_iter_1"
    async with test_db_session_factory() as session:
        base_row = (
            await session.exec(
                select(ActivityExecution).where(
                    ActivityExecution.execution_id == test_execution.id,
                    ActivityExecution.activity_name == _NODE_ID,
                )
            )
        ).one()
        base_row.status = ActivityStatus.COMPLETED
        base_row.iteration = 0
        session.add(
            ActivityExecution(
                execution_id=test_execution.id,
                activity_name=f"{_NODE_ID}#iter-1",
                node_type=NodeType.SCRIPT_PYTHON,
                temporal_activity_id=temporal_activity_id,
                status=ActivityStatus.RUNNING,
                iteration=1,
            )
        )
        await session.commit()

    work_id = uuid5(test_execution.id, temporal_activity_id)
    message = CredentialResolveWorkload(
        work_item_id=work_id,
        attempt_id="attempt",
        credential_ref=credential_ref,
        credential_recipe_id="acme.echo.api-token",
        step_revision_id="step-revision",
        runtime_context={
            "execution_id": str(test_execution.id),
            "temporal_activity_id": temporal_activity_id,
        },
    ).to_message(
        source_id="execution-plane",
        destination_id="syntara-orchestration",
        client_id="syntara-orchestration",
    )
    payload = CredentialResolveWorkload.model_validate(message.command.payload)
    resolve_document = AsyncMock(return_value={"token": "resolved-token"})
    monkeypatch.setattr(CredentialResolveWorkloadCommandHandler, "_resolve_credential_document", resolve_document)
    allow_plugin_recipe(monkeypatch)

    async with test_db_session_factory() as reader:
        handling = await CredentialResolveWorkloadCommandHandler().handle(
            message,
            payload,
            AOCommandContext(reader, AsyncMock()),
        )

    assert handling.result is not None
    assert isinstance(handling.result, CredentialResolveWorkloadCommandResult)
    assert handling.result.credential == {"token": "resolved-token"}
    resolve_document.assert_awaited_once_with(reader, credential_ref, test_execution.project_id)
