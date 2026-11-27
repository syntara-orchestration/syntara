"""Exercise AO's EP callback using real shared command envelopes."""

from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
from execution_plane_client.commands.control import Completion, CompletionStatus
from fastapi import FastAPI, Request, Response

from syntara.authz.exceptions import AuthorizationDeniedError, authorization_denied_handler
from syntara.core.config.base import get_settings
from syntara.core.database.session import get_db
from syntara.execution_plane import bridge
from syntara.execution_plane.commands import completion as command_completion
from syntara.execution_plane.commands.activity_resolution import ActivityResolution, ResolutionChain
from syntara.execution_plane.commands.completion import CompletionCommandHandler
from syntara.execution_plane.commands.context import AOCommandContext
from syntara.execution_plane.utils import execution_plane_work_item_id
from syntara.workflow_core.models import NodeType
from syntara.workflows.executions_router import get_temporal_execution_service
from syntara.workflows.models.activity_execution import ActivityExecution
from syntara.workflows.models.execution import Execution
from syntara.workflows.models.workflow_definition import WorkflowDefinition
from syntara.workflows.models.workflow_version import WorkflowVersion


@pytest.fixture
def callback(monkeypatch: pytest.MonkeyPatch) -> tuple[FastAPI, AsyncMock, MagicMock]:
    app = FastAPI()
    app.include_router(bridge.router)
    app.add_exception_handler(AuthorizationDeniedError, authorization_denied_handler)  # type: ignore[arg-type]
    app.state.authz_evaluator = MagicMock()
    authorize = AsyncMock()
    authorize.return_value.allowed = True
    monkeypatch.setattr(bridge, "authorize", authorize)
    session = AsyncMock()
    activity = _activity()
    activity_rows = MagicMock()
    activity_rows.one_or_none.return_value = activity
    plugin_rows = MagicMock()
    plugin_rows.first.return_value = SimpleNamespace(name="script-bash", manifest=_plugin_manifest())
    session.exec.side_effect = [activity_rows, plugin_rows]
    temporal = AsyncMock()
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_temporal_execution_service] = lambda: temporal

    @app.middleware("http")
    async def certificate(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request.state.is_cert_authenticated = True
        request.state.cert_cn = get_settings().ep_callback_service_cn
        return await call_next(request)

    return app, temporal, activity_rows


def completion():
    work_id = uuid4()
    return Completion(
        status=CompletionStatus.COMPLETED,
        result={"output": {"return_code": 0, "stdout": "ok", "stderr": ""}},
        work_item_id=work_id,
    ).to_message(
        source_id="execution-plane",
        destination_id="syntara-orchestration",
        client_id="syntara-orchestration",
    )


def _plugin_manifest() -> dict[str, object]:
    return {
        "spec": {
            "output": {
                "kind": "inline",
                "value": {
                    "type": "object",
                    "required": ["return_code", "stdout", "stderr"],
                    "additionalProperties": False,
                    "properties": {
                        "return_code": {"type": "integer"},
                        "stdout": {"type": "string"},
                        "stderr": {"type": "string"},
                    },
                },
            }
        }
    }


def _execution() -> Execution:
    execution = Execution(
        id=uuid4(),
        workflow_id=uuid4(),
        workflow_version_id=uuid4(),
        project_id=uuid4(),
        temporal_workflow_id="workflow-id",
    )
    execution.workflow_version = WorkflowVersion(
        id=execution.workflow_version_id,
        workflow_id=execution.workflow_id,
        version=1,
        schema_version="2.0.0",
        workflow_definition={
            "schema_version": "2.0.0",
            "name": "workflow",
            "triggers": [{"id": "trigger", "type": "manual"}],
            "nodes": [
                {
                    "id": "script",
                    "type": "script_bash",
                    "parameters": {"code": "true"},
                }
            ],
            "edges": [],
        },
    )
    return execution


def _activity() -> ActivityExecution:
    execution = _execution()
    activity = ActivityExecution(
        id=uuid4(),
        execution_id=execution.id,
        activity_name="script",
        node_type=NodeType.SCRIPT_BASH,
        temporal_activity_id="activity-id",
    )
    activity.execution = execution
    return activity


def test_router_only_exposes_the_command_ingress():
    assert {route.path for route in bridge.router.routes} == {"/api/execution_plane/v1/commands"}


def test_command_ingress_is_not_published_in_openapi():
    assert all(not route.include_in_schema for route in bridge.router.routes)


@pytest.mark.asyncio
async def test_completion_authorizes_ep_service_principal(callback, monkeypatch):
    app, temporal, _ = callback
    authorize = AsyncMock()
    authorize.return_value.allowed = True
    monkeypatch.setattr(bridge, "authorize", authorize)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=completion().model_dump(mode="json"))

    assert response.status_code == 200, response.text
    assert authorize.await_count == 1
    request_arg = authorize.await_args.args[2]
    assert request_arg.user_id == bridge.service_principal_id(get_settings().ep_callback_service_cn)
    assert request_arg.resource_type == "execution-plane-callback"
    assert request_arg.action == "complete"
    assert request_arg.groups == []
    temporal.complete_async_activity.assert_awaited_once()


@pytest.mark.asyncio
async def test_completion_rejects_service_principal_without_callback_role(callback, monkeypatch):
    app, temporal, _ = callback
    authorize = AsyncMock()
    authorize.return_value.allowed = False
    monkeypatch.setattr(bridge, "authorize", authorize)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=completion().model_dump(mode="json"))

    assert response.status_code == 403
    authorize.assert_awaited_once()
    temporal.complete_async_activity.assert_not_awaited()


@pytest.mark.asyncio
async def test_completion_rejects_wrong_certificate_identity(callback, monkeypatch):
    app, temporal, _ = callback
    monkeypatch.setattr(
        bridge,
        "get_settings",
        lambda: SimpleNamespace(ep_callback_service_cn="other-allowlisted-service"),
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=completion().model_dump(mode="json"))

    assert response.status_code == 403
    temporal.complete_async_activity.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome",
    [
        CompletionStatus.COMPLETED,
        CompletionStatus.FAILED,
        CompletionStatus.CANCELLED,
        CompletionStatus.RECONCILIATION_REQUIRED,
    ],
)
async def test_completion_command_resolves_temporal_activity_and_acknowledges(callback, outcome, monkeypatch):
    app, temporal, _ = callback
    message = completion()
    body = message.model_dump(mode="json")
    body["command"]["payload"]["status"] = outcome
    validate = MagicMock(wraps=Completion.model_validate)
    monkeypatch.setattr(Completion, "model_validate", validate)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["message_id"] == str(message.message_id)
    assert response.json()["received"] is True
    assert response.json()["resource"]["kind"] == "work_item"
    assert response.json()["resource"]["resource_id"] == message.command.payload["work_item_id"]
    validate.assert_called_once()
    if outcome is CompletionStatus.COMPLETED:
        temporal.complete_async_activity.assert_awaited_once_with(
            temporal_workflow_id="workflow-id",
            activity_id="activity-id",
            result={"output": {"return_code": 0, "stdout": "ok", "stderr": ""}},
        )
    elif outcome is CompletionStatus.CANCELLED:
        temporal.report_cancellation_async_activity.assert_awaited_once_with(
            temporal_workflow_id="workflow-id", activity_id="activity-id"
        )
        temporal.fail_async_activity.assert_not_awaited()
    else:
        assert temporal.fail_async_activity.await_args.kwargs["error"].non_retryable
        if outcome is CompletionStatus.RECONCILIATION_REQUIRED:
            assert (
                temporal.fail_async_activity.await_args.kwargs["error"].type == "ExecutionPlaneReconciliationRequired"
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["source_id", "destination_id", "client_id"])
async def test_completion_rejects_wrong_participant(callback, field):
    app, temporal, _ = callback
    body = completion().model_dump(mode="json")
    target = body["scope"] if field == "client_id" else body
    target[field] = "other-service"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=body)
    assert response.status_code == 403
    temporal.complete_async_activity.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid",
    [
        "missing_work",
        "invalid_work",
        "legacy_parent",
        "resource",
        "revision",
        "type",
        "unknown_type",
        "status",
        "result",
    ],
)
async def test_completion_rejects_invalid_correlation_or_command(callback, invalid):
    app, temporal, _ = callback
    body = completion().model_dump(mode="json")
    command = body["command"]
    if invalid == "missing_work":
        del command["payload"]["work_item_id"]
    elif invalid == "invalid_work":
        command["payload"]["work_item_id"] = None
    elif invalid == "legacy_parent":
        command["parent_command_id"] = str(uuid4())
    elif invalid == "resource":
        command["payload"]["resource"] = {"kind": "work_item", "resource_id": str(uuid4())}
    elif invalid == "status":
        command["payload"]["status"] = "running"
    elif invalid == "result":
        command["payload"]["result"] = []
    elif invalid == "unknown_type":
        command["command_type"] = "unknown.command"
    elif invalid == "revision":
        command["command_revision"] = 2
    else:
        command["command_type"] = "work.cancel_bulk"
        command["payload"] = {"selector": {"work_item_ids": [str(uuid4())]}}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=body)
    assert response.status_code == 422
    temporal.complete_async_activity.assert_not_awaited()
    temporal.fail_async_activity.assert_not_awaited()


@pytest.mark.asyncio
async def test_completion_missing_activity_remains_retryable(callback):
    app, _, rows = callback
    rows.one_or_none.return_value = None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=completion().model_dump(mode="json"))
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_completion_resolves_loop_work_from_temporal_history(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deliver a completion before the activity synchronizer has persisted the row."""
    execution = _execution()
    temporal_activity_id = "script_iter_1_iter_0"
    work_id = execution_plane_work_item_id(execution.id, temporal_activity_id)
    scheduled_event = MagicMock()
    scheduled_event.event_id = 42
    scheduled_attrs = scheduled_event.activity_task_scheduled_event_attributes
    scheduled_attrs.activity_id = temporal_activity_id
    scheduled_attrs.activity_type.name = "execute_bash_script_activity"
    history = MagicMock()
    history.events = [scheduled_event]
    workflow_handle = AsyncMock()
    workflow_handle.fetch_history.return_value = history
    temporal_client = MagicMock()
    temporal_client.get_workflow_handle.return_value = workflow_handle
    temporal_service = AsyncMock(temporal_client=temporal_client)
    missing_row = MagicMock()
    missing_row.one_or_none.return_value = None
    execution_result = MagicMock()
    execution_result.one_or_none.return_value = execution
    plugin_rows = MagicMock()
    plugin_rows.first.return_value = SimpleNamespace(name="script-bash", manifest=_plugin_manifest())
    session = AsyncMock()
    session.exec.side_effect = [
        missing_row,
        execution_result,
        missing_row,
        missing_row,
        execution_result,
        plugin_rows,
    ]

    delivered = await CompletionCommandHandler()._complete_activity(
        context=AOCommandContext(session, temporal_service),
        work_id=work_id,
        status=CompletionStatus.COMPLETED,
        result={"output": {"return_code": 0, "stdout": "ok", "stderr": ""}},
        runtime_context={
            "execution_id": str(execution.id),
            "temporal_activity_id": temporal_activity_id,
        },
    )

    assert delivered is True
    temporal_client.get_workflow_handle.assert_called_once_with("workflow-id")
    workflow_handle.fetch_history.assert_awaited_once()
    temporal_service.complete_async_activity.assert_awaited_once_with(
        temporal_workflow_id="workflow-id",
        activity_id=temporal_activity_id,
        result={"output": {"return_code": 0, "stdout": "ok", "stderr": ""}},
    )


@pytest.mark.asyncio
async def test_completion_uses_injected_resolution_chain() -> None:
    execution = _execution()
    definition = execution.workflow_version.workflow_definition
    node = WorkflowDefinition.model_validate(definition).nodes[0]
    expected = ActivityResolution(
        execution=execution,
        node=node,
        node_type=NodeType.SCRIPT_BASH,
        temporal_activity_id="activity-id",
    )
    calls: list[tuple[object, object, object]] = []

    class RecordingStrategy:
        async def resolve(
            self,
            context: object,
            work_item_id: object,
            runtime_context: object,
        ) -> ActivityResolution | None:
            calls.append((context, work_item_id, runtime_context))
            return expected

    temporal = AsyncMock()
    context = AOCommandContext(AsyncMock(), temporal)
    handler = command_completion.CompletionCommandHandler()
    handler._resolution_chain = ResolutionChain([RecordingStrategy()])

    delivered = await handler._complete_activity(
        context=context,
        work_id=uuid4(),
        status=CompletionStatus.FAILED,
        result={"error": "failed"},
        runtime_context={"execution_id": str(execution.id)},
    )

    assert delivered is True
    assert len(calls) == 1
    assert calls[0][0] is context
    assert calls[0][2] == {"execution_id": str(execution.id)}
    temporal.fail_async_activity.assert_awaited_once_with(
        temporal_workflow_id="workflow-id",
        activity_id="activity-id",
        error=temporal.fail_async_activity.await_args.kwargs["error"],
    )


@pytest.mark.asyncio
async def test_completion_uses_persisted_node_type_without_canvas_node(monkeypatch: pytest.MonkeyPatch) -> None:
    execution = _execution()
    expected = ActivityResolution(
        execution=execution,
        node=None,
        node_type=NodeType.SCRIPT_BASH,
        temporal_activity_id="activity-id",
    )
    temporal = AsyncMock()
    context = AOCommandContext(AsyncMock(), temporal)
    handler = command_completion.CompletionCommandHandler()
    handler._resolution_chain = ResolutionChain([SimpleNamespace(resolve=AsyncMock(return_value=expected))])
    validation_error = AsyncMock(return_value=None)
    monkeypatch.setattr(handler, "_output_validation_error", validation_error)

    delivered = await handler._complete_activity(
        context=context,
        work_id=uuid4(),
        status=CompletionStatus.COMPLETED,
        result={"output": {"return_code": 0, "stdout": "ok", "stderr": ""}},
        runtime_context={"execution_id": str(execution.id)},
    )

    assert delivered is True
    validation_error.assert_awaited_once_with(
        context, NodeType.SCRIPT_BASH, {"output": {"return_code": 0, "stdout": "ok", "stderr": ""}}
    )
    temporal.complete_async_activity.assert_awaited_once_with(
        temporal_workflow_id="workflow-id",
        activity_id="activity-id",
        result={"output": {"return_code": 0, "stdout": "ok", "stderr": ""}},
    )


@pytest.mark.asyncio
async def test_completion_runtime_context_cannot_redirect_activity_or_result(callback):
    app, temporal, _ = callback
    message = completion()
    body = message.model_dump(mode="json")
    body["command"]["payload"]["runtime_context"] = {"activity_execution_id": str(uuid4()), "project_id": str(uuid4())}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["resource"]["kind"] == "work_item"
    assert response.json()["resource"]["resource_id"] == message.command.payload["work_item_id"]
    temporal.complete_async_activity.assert_awaited_once()


@pytest.mark.asyncio
async def test_completion_rejects_completed_result_that_violates_output_schema(callback):
    app, temporal, _ = callback
    message = completion()
    body = message.model_dump(mode="json")
    body["command"]["payload"]["result"] = {"output": {"return_code": 0}}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=body)

    assert response.status_code == 200, response.text
    temporal.complete_async_activity.assert_not_awaited()
    temporal.fail_async_activity.assert_awaited_once()
    error = temporal.fail_async_activity.await_args.kwargs["error"]
    assert error.type == "ExecutionPlaneProtocolError"
    assert error.non_retryable is True
