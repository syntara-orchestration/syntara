"""Workload-scoped credential resolution command handling."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import httpx
import pytest
from execution_plane_client.commands.credentials import CredentialResolveCluster, CredentialResolveWorkload
from execution_plane_client.commands.results import CredentialResolveWorkloadCommandResult
from execution_plane_client.errors import ProtocolConflict
from fastapi import FastAPI, Request, Response

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.authz.exceptions import AuthorizationDeniedError, authorization_denied_handler
from syntara.core.config.base import get_settings
from syntara.core.database.session import get_db
from syntara.core.lib.encryption import EncryptionError
from syntara.core.models.principal import service_principal_id
from syntara.credentials.audit.credential import CredentialWorkloadResolvedEvent
from syntara.execution_plane import bridge
from syntara.execution_plane.commands import credentials as command_credentials
from syntara.execution_plane.commands.activity_resolution import (
    ActivityResolution,
    ResolutionChain,
    TemporalHistoryResolutionStrategy,
    resolution_for_activity,
)
from syntara.execution_plane.commands.context import AOCommandContext
from syntara.execution_plane.commands.errors import CommandResourceStateError
from syntara.execution_plane.utils import execution_plane_work_item_id
from syntara.integrations.exceptions import IntegrationCredentialNotFoundError
from syntara.workflow_core.models import ConditionNodeParameters, NodeType
from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution
from syntara.workflows.models.workflow_definition import ConditionNode, WorkflowDefinition
from syntara.workflows.models.workflow_version import WorkflowVersion

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from execution_plane_client.protocol import MessageEnvelope


@pytest.fixture
def callback(monkeypatch: pytest.MonkeyPatch) -> tuple[FastAPI, AsyncMock]:
    app = FastAPI()
    app.include_router(bridge.router)
    app.add_exception_handler(AuthorizationDeniedError, authorization_denied_handler)  # type: ignore[arg-type]
    app.state.authz_evaluator = MagicMock()
    authorize = AsyncMock()
    authorize.return_value.allowed = True
    monkeypatch.setattr(bridge, "authorize", authorize)
    session = AsyncMock()
    app.dependency_overrides[get_db] = lambda: session

    @app.middleware("http")
    async def certificate(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request.state.is_cert_authenticated = True
        request.state.cert_cn = get_settings().ep_callback_service_cn
        return await call_next(request)

    return app, session


def workload_command(
    *,
    work_item_id: UUID | None = None,
    credential_ref: UUID | None = None,
    credential_recipe_id: str = "acme.echo.api-token",
    runtime_context: Mapping[str, object] | None = None,
) -> tuple[MessageEnvelope, CredentialResolveWorkload]:
    message = CredentialResolveWorkload(
        work_item_id=work_item_id or uuid4(),
        attempt_id="attempt",
        credential_ref=credential_ref or uuid4(),
        credential_recipe_id=credential_recipe_id,
        step_revision_id="step-revision",
        runtime_context=dict(runtime_context or {}),
    ).to_message(
        source_id="execution-plane",
        destination_id="syntara-orchestration",
        client_id="syntara-orchestration",
    )
    return message, CredentialResolveWorkload.model_validate(message.command.payload)


def activity(
    *,
    status: ActivityStatus = ActivityStatus.RUNNING,
    credential_ref: UUID | None = None,
    credential_recipe_id: str = "acme.echo.api-token",
    workflow_definition: dict[str, object] | None = None,
) -> ActivityExecution:
    execution = Execution(
        id=uuid4(),
        workflow_id=uuid4(),
        workflow_version_id=uuid4(),
        project_id=uuid4(),
        temporal_workflow_id="workflow",
    )
    definition = workflow_definition or {
        "schema_version": "2.0.0",
        "name": "workflow",
        "triggers": [{"id": "trigger", "type": "manual"}],
        "nodes": [
            {
                "id": "approval",
                "type": "approval",
                "parameters": {
                    "credential_bindings": [
                        {
                            "credential_recipe_id": credential_recipe_id,
                            "credential_ref": str(credential_ref or uuid4()),
                        }
                    ]
                },
            }
        ],
        "edges": [],
    }
    version = WorkflowVersion(
        id=execution.workflow_version_id,
        workflow_id=execution.workflow_id,
        version=1,
        schema_version="2.0.0",
        workflow_definition=definition,
    )
    execution.workflow_version = version
    result = ActivityExecution(
        id=execution_plane_work_item_id(execution.id, "approval"),
        execution_id=execution.id,
        activity_name="approval",
        node_type="approval",
        temporal_activity_id="activity",
        status=status,
    )
    result.execution = execution
    return result


def _allow_plugin_recipe(monkeypatch: pytest.MonkeyPatch, recipe_id: str = "acme.echo.api-token") -> None:
    monkeypatch.setattr(
        command_credentials,
        "get_execution_plane_plugin_by_node_type",
        AsyncMock(return_value=SimpleNamespace(name="plugin")),
    )
    monkeypatch.setattr(
        command_credentials,
        "execution_plane_plugin_credential_recipe_ids",
        AsyncMock(return_value=(recipe_id,)),
    )


def _use_resolution_chain(
    monkeypatch: pytest.MonkeyPatch,
    activity: ActivityExecution | None,
    *,
    temporal_activity_id: str | None = None,
) -> None:
    """Replace the handler's resolution chain with a deterministic result."""
    resolution = (
        resolution_for_activity(activity, temporal_activity_id=temporal_activity_id) if activity is not None else None
    )

    async def resolve(
        _self: object,
        _context: object,
        _work_item_id: object,
        _runtime_context: object,
    ) -> ActivityResolution | None:
        return resolution

    monkeypatch.setattr(ResolutionChain, "resolve", resolve)


def loop_activity(
    *,
    execution_id: UUID,
    temporal_activity_id: str,
    status: ActivityStatus = ActivityStatus.RUNNING,
    credential_ref: UUID | None = None,
    credential_recipe_id: str = "acme.echo.api-token",
    node_type: str = "approval",
) -> ActivityExecution:
    execution = Execution(
        id=execution_id,
        workflow_id=uuid4(),
        workflow_version_id=uuid4(),
        project_id=uuid4(),
        temporal_workflow_id="workflow",
    )
    definition = {
        "schema_version": "2.0.0",
        "name": "workflow",
        "triggers": [{"id": "trigger", "type": "manual"}],
        "nodes": [
            {
                "id": "approval",
                "type": node_type,
                "parameters": {
                    "code": "true",
                    "credential_bindings": [
                        {
                            "credential_recipe_id": credential_recipe_id,
                            "credential_ref": str(credential_ref or uuid4()),
                        }
                    ],
                },
            }
        ],
        "edges": [],
    }
    version = WorkflowVersion(
        id=execution.workflow_version_id,
        workflow_id=execution.workflow_id,
        version=1,
        schema_version="2.0.0",
        workflow_definition=definition,
    )
    execution.workflow_version = version
    result = ActivityExecution(
        id=execution_plane_work_item_id(execution.id, "approval"),
        execution_id=execution.id,
        activity_name="approval",
        node_type="approval",
        temporal_activity_id=temporal_activity_id,
        status=status,
    )
    result.execution = execution
    return result


@pytest.fixture
def command_context() -> AOCommandContext:
    return AOCommandContext(session=AsyncMock(), temporal_service=None)


@pytest.mark.asyncio
async def test_workload_credential_command_resolves_bound_generic_node(
    callback: tuple[FastAPI, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _ = callback
    message, payload = workload_command(credential_ref=uuid4())
    row = activity(credential_ref=payload.credential_ref)
    _allow_plugin_recipe(monkeypatch)
    resolved: dict[str, object] = {}

    async def resolve_document(
        _handler: object,
        _session: AsyncMock,
        credential_ref: object,
        _project_id: object,
    ) -> dict[str, str]:
        resolved["credential_ref"] = credential_ref
        return {"token": "resolved-token"}

    _use_resolution_chain(monkeypatch, row)
    monkeypatch.setattr(
        command_credentials.CredentialResolveWorkloadCommandHandler, "_resolve_credential_document", resolve_document
    )
    dispatch = MagicMock()
    monkeypatch.setattr(AuditEventDispatcher, "dispatch", dispatch)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=message.model_dump(mode="json"))

    assert response.status_code == 200, response.text
    assert response.json() == {
        "received": True,
        "message_id": str(message.message_id),
        "resource": {
            "kind": "work_item",
            "resource_id": str(UUID(str(message.command.payload["work_item_id"]))),
            "resource_key": None,
            "revision": None,
        },
        "result": {
            "command_type": "credential.resolve.workload",
            "command_revision": 1,
            "credential": {"token": "resolved-token"},
        },
    }
    assert resolved["credential_ref"] == payload.credential_ref
    dispatch.assert_called_once()
    event = dispatch.call_args.args[0]
    assert isinstance(event, CredentialWorkloadResolvedEvent)
    assert event.credential_id == payload.credential_ref
    assert event.work_item_id == payload.work_item_id
    assert event.message_id == message.message_id
    assert event.service_identity == message.source_id


@pytest.mark.asyncio
async def test_workload_credential_command_uses_workload_specific_permission(
    callback: tuple[FastAPI, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _ = callback
    authorize = AsyncMock()
    authorize.return_value.allowed = True
    monkeypatch.setattr(bridge, "authorize", authorize)
    _allow_plugin_recipe(monkeypatch)
    monkeypatch.setattr(AuditEventDispatcher, "dispatch", MagicMock())
    message, payload = workload_command()
    _use_resolution_chain(monkeypatch, activity(credential_ref=payload.credential_ref))
    monkeypatch.setattr(
        command_credentials.CredentialResolveWorkloadCommandHandler,
        "_resolve_credential_document",
        AsyncMock(return_value={"token": "resolved-token"}),
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=message.model_dump(mode="json"))

    assert response.status_code == 200, response.text
    assert authorize.await_count == 1
    await_args = authorize.await_args
    assert await_args is not None
    request_arg = await_args.args[2]
    assert request_arg.user_id == service_principal_id(get_settings().ep_callback_service_cn)
    assert request_arg.resource_type == "execution-plane-callback"
    assert request_arg.action == "resolve-credential-workload"


@pytest.mark.asyncio
async def test_workload_credential_command_rejects_service_principal_without_callback_role(
    callback: tuple[FastAPI, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _ = callback
    authorize = AsyncMock()
    authorize.return_value.allowed = False
    monkeypatch.setattr(bridge, "authorize", authorize)
    message, _ = workload_command()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=message.model_dump(mode="json"))

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_workload_credential_command_rejects_missing_activity(
    callback: tuple[FastAPI, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _ = callback
    message, _ = workload_command()
    _use_resolution_chain(monkeypatch, None)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=message.model_dump(mode="json"))

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_workload_credential_command_rejects_terminal_activity(
    callback: tuple[FastAPI, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _ = callback
    message, payload = workload_command(credential_ref=uuid4())

    _use_resolution_chain(
        monkeypatch,
        activity(status=ActivityStatus.COMPLETED, credential_ref=payload.credential_ref),
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=message.model_dump(mode="json"))

    assert response.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["credential_ref", "credential_recipe_id"])
async def test_workload_credential_command_rejects_unbound_recipe_or_reference(
    callback: tuple[FastAPI, AsyncMock], monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    app, _ = callback
    message, payload = workload_command(credential_ref=uuid4())
    row_credential_ref = payload.credential_ref if field == "credential_recipe_id" else uuid4()
    row_recipe_id = "other.recipe" if field == "credential_recipe_id" else payload.credential_recipe_id
    row = activity(credential_ref=row_credential_ref, credential_recipe_id=row_recipe_id)

    _use_resolution_chain(monkeypatch, row)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=message.model_dump(mode="json"))

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_workload_credential_command_rejects_recipe_unreachable_from_plugin(
    command_context: AOCommandContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = command_credentials.CredentialResolveWorkloadCommandHandler()
    message, payload = workload_command(credential_ref=uuid4())
    row = activity(credential_ref=payload.credential_ref, credential_recipe_id=payload.credential_recipe_id)
    row.node_type = NodeType.SCRIPT_PYTHON
    resolve_document = AsyncMock()

    _use_resolution_chain(monkeypatch, row)
    monkeypatch.setattr(handler, "_resolve_credential_document", resolve_document)
    monkeypatch.setattr(
        command_credentials,
        "get_execution_plane_plugin_by_node_type",
        AsyncMock(return_value=SimpleNamespace(name="script-python")),
    )
    monkeypatch.setattr(
        command_credentials,
        "execution_plane_plugin_credential_recipe_ids",
        AsyncMock(return_value=()),
    )

    with pytest.raises(CommandResourceStateError):
        await handler.handle(message, payload, command_context)

    resolve_document.assert_not_called()


async def test_workload_credential_command_resolves_loop_body_work(
    callback: tuple[FastAPI, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _ = callback
    execution_id = uuid4()
    temporal_activity_id = "approval_iter_0"
    work_item_id = execution_plane_work_item_id(execution_id, temporal_activity_id)
    message, payload = workload_command(
        work_item_id=work_item_id,
        credential_ref=uuid4(),
        runtime_context={
            "execution_id": str(execution_id),
            "temporal_activity_id": temporal_activity_id,
        },
    )
    row = loop_activity(
        execution_id=execution_id,
        temporal_activity_id=temporal_activity_id,
        credential_ref=payload.credential_ref,
    )

    _use_resolution_chain(monkeypatch, row, temporal_activity_id=temporal_activity_id)
    _allow_plugin_recipe(monkeypatch)
    monkeypatch.setattr(
        command_credentials.CredentialResolveWorkloadCommandHandler,
        "_resolve_credential_document",
        AsyncMock(return_value={"token": "resolved-token"}),
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=message.model_dump(mode="json"))

    assert response.status_code == 200, response.text
    assert response.json()["result"]["credential"] == {"token": "resolved-token"}


@pytest.mark.asyncio
async def test_workload_credential_command_resolves_later_loop_iteration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A later callback resolves its active per-iteration row, not iteration zero."""
    execution_id = uuid4()
    temporal_activity_id = "approval_iter_1"
    work_item_id = execution_plane_work_item_id(execution_id, temporal_activity_id)
    message, payload = workload_command(
        work_item_id=work_item_id,
        credential_ref=uuid4(),
        runtime_context={
            "execution_id": str(execution_id),
            "temporal_activity_id": temporal_activity_id,
        },
    )
    row = loop_activity(
        execution_id=execution_id,
        temporal_activity_id=temporal_activity_id,
        credential_ref=payload.credential_ref,
    )
    _use_resolution_chain(monkeypatch, row, temporal_activity_id=temporal_activity_id)
    monkeypatch.setattr(
        command_credentials.CredentialResolveWorkloadCommandHandler,
        "_resolve_credential_document",
        AsyncMock(return_value={"token": "resolved-token"}),
    )
    _allow_plugin_recipe(monkeypatch)

    handling = await command_credentials.CredentialResolveWorkloadCommandHandler().handle(
        message,
        payload,
        AOCommandContext(AsyncMock(), AsyncMock()),
    )

    assert isinstance(handling.result, CredentialResolveWorkloadCommandResult)
    assert handling.result.credential == {"token": "resolved-token"}


@pytest.mark.asyncio
async def test_workload_credential_command_rejects_loop_context_that_does_not_correlate(
    callback: tuple[FastAPI, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _ = callback
    execution_id = uuid4()
    temporal_activity_id = "approval_iter_0"
    message, _payload = workload_command(
        runtime_context={
            "execution_id": str(execution_id),
            "temporal_activity_id": temporal_activity_id,
        },
    )

    _use_resolution_chain(monkeypatch, None)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=message.model_dump(mode="json"))

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_temporal_history_strategy_resolves_loop_work_before_row_persistence() -> None:
    """Resolve an activity before the synchronizer has persisted its row."""
    execution_id = uuid4()
    temporal_activity_id = "approval_iter_1_iter_0"
    work_item_id = execution_plane_work_item_id(execution_id, temporal_activity_id)
    expected = loop_activity(
        execution_id=execution_id,
        temporal_activity_id=temporal_activity_id,
        node_type="script_bash",
    )
    execution_result = MagicMock()
    execution_result.one_or_none.return_value = expected.execution
    session = AsyncMock()
    session.exec.return_value = execution_result

    scheduled_event = MagicMock()
    scheduled_event.event_id = 42
    scheduled_attrs = scheduled_event.activity_task_scheduled_event_attributes
    scheduled_attrs.activity_id = temporal_activity_id
    scheduled_attrs.activity_type.name = "execute_bash_script_activity"
    history = MagicMock()
    history.events = [scheduled_event]
    handle = AsyncMock()
    handle.fetch_history.return_value = history
    temporal_client = MagicMock()
    temporal_client.get_workflow_handle.return_value = handle
    temporal_service = MagicMock(temporal_client=temporal_client)

    resolution = await TemporalHistoryResolutionStrategy().resolve(
        AOCommandContext(session, temporal_service),
        work_item_id,
        {
            "execution_id": str(execution_id),
            "temporal_activity_id": temporal_activity_id,
        },
    )

    assert resolution is not None
    assert resolution.node is not None
    assert resolution.execution is expected.execution
    assert resolution.node.id == "approval"
    assert resolution.temporal_activity_id == temporal_activity_id
    assert resolution.activity is None
    temporal_client.get_workflow_handle.assert_called_once_with(expected.execution.temporal_workflow_id)
    handle.fetch_history.assert_awaited_once()


@pytest.mark.asyncio
async def test_workload_credential_command_uses_history_when_later_iteration_row_is_not_synced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution_id = uuid4()
    temporal_activity_id = "approval_iter_1"
    work_item_id = execution_plane_work_item_id(execution_id, temporal_activity_id)
    message, payload = workload_command(
        work_item_id=work_item_id,
        credential_ref=uuid4(),
        runtime_context={
            "execution_id": str(execution_id),
            "temporal_activity_id": temporal_activity_id,
        },
    )

    iteration_zero = loop_activity(
        execution_id=execution_id,
        temporal_activity_id="approval",
        status=ActivityStatus.COMPLETED,
        credential_ref=payload.credential_ref,
        node_type="script_bash",
    )

    def query_result(value: object | None) -> MagicMock:
        result = MagicMock()
        result.one_or_none.return_value = value
        return result

    session = AsyncMock()
    session.exec.side_effect = [
        query_result(None),
        query_result(iteration_zero.execution),
        query_result(None),
        query_result(iteration_zero),
        query_result(iteration_zero.execution),
    ]

    scheduled_event = MagicMock()
    attrs = scheduled_event.activity_task_scheduled_event_attributes
    attrs.activity_id = temporal_activity_id
    attrs.activity_type.name = "execute_bash_script_activity"
    history = MagicMock()
    history.events = [scheduled_event]
    workflow_handle = AsyncMock()
    workflow_handle.fetch_history.return_value = history
    temporal_client = MagicMock()
    temporal_client.get_workflow_handle.return_value = workflow_handle
    temporal_service = MagicMock(temporal_client=temporal_client)

    handler = command_credentials.CredentialResolveWorkloadCommandHandler()
    monkeypatch.setattr(
        handler,
        "_resolve_credential_document",
        AsyncMock(return_value={"token": "resolved-token"}),
    )
    _allow_plugin_recipe(monkeypatch)

    handling = await handler.handle(
        message,
        payload,
        AOCommandContext(session, temporal_service),
    )

    assert isinstance(handling.result, CredentialResolveWorkloadCommandResult)
    assert handling.result.credential == {"token": "resolved-token"}
    workflow_handle.fetch_history.assert_awaited_once()


@pytest.mark.asyncio
async def test_workload_credential_command_uses_injected_resolution_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    message, payload = workload_command(credential_ref=uuid4())
    row = activity(credential_ref=payload.credential_ref)
    definition = WorkflowDefinition.model_validate(row.execution.workflow_version.workflow_definition)
    node = next(candidate for candidate in definition.nodes if candidate.id == "approval")
    expected = ActivityResolution(
        execution=row.execution,
        node=node,
        node_type=row.node_type,
        temporal_activity_id=row.temporal_activity_id,
        activity=row,
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

    monkeypatch.setattr(
        command_credentials.CredentialResolveWorkloadCommandHandler,
        "_resolve_credential_document",
        AsyncMock(return_value={"token": "resolved-token"}),
    )
    _allow_plugin_recipe(monkeypatch)
    context = AOCommandContext(AsyncMock(), AsyncMock())
    handler = command_credentials.CredentialResolveWorkloadCommandHandler()
    handler._resolution_chain = ResolutionChain([RecordingStrategy()])

    handling = await handler.handle(message, payload, context)

    assert isinstance(handling.result, CredentialResolveWorkloadCommandResult)
    assert handling.result.credential == {"token": "resolved-token"}
    assert calls == [(context, payload.work_item_id, payload.runtime_context)]


@pytest.mark.asyncio
async def test_workload_credential_command_rejects_terminal_loop_body_work(
    callback: tuple[FastAPI, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _ = callback
    execution_id = uuid4()
    temporal_activity_id = "approval_iter_0"
    work_item_id = execution_plane_work_item_id(execution_id, temporal_activity_id)
    message, payload = workload_command(
        work_item_id=work_item_id,
        credential_ref=uuid4(),
        runtime_context={
            "execution_id": str(execution_id),
            "temporal_activity_id": temporal_activity_id,
        },
    )
    row = loop_activity(
        execution_id=execution_id,
        temporal_activity_id=temporal_activity_id,
        status=ActivityStatus.COMPLETED,
        credential_ref=payload.credential_ref,
    )

    _use_resolution_chain(monkeypatch, row, temporal_activity_id=temporal_activity_id)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=message.model_dump(mode="json"))

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_workload_credential_command_rejects_unbound_loop_body_work(
    callback: tuple[FastAPI, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _ = callback
    execution_id = uuid4()
    temporal_activity_id = "approval_iter_0"
    work_item_id = execution_plane_work_item_id(execution_id, temporal_activity_id)
    message, _payload = workload_command(
        work_item_id=work_item_id,
        credential_ref=uuid4(),
        runtime_context={
            "execution_id": str(execution_id),
            "temporal_activity_id": temporal_activity_id,
        },
    )
    row = loop_activity(
        execution_id=execution_id,
        temporal_activity_id=temporal_activity_id,
        credential_ref=uuid4(),
    )

    _use_resolution_chain(monkeypatch, row, temporal_activity_id=temporal_activity_id)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=message.model_dump(mode="json"))

    assert response.status_code == 409


def test_binding_match_rejects_nodes_without_credential_bindings() -> None:
    handler = command_credentials.CredentialResolveWorkloadCommandHandler()
    node = ConditionNode(
        id="condition",
        type="condition",
        parameters=ConditionNodeParameters(condition="true"),
    )
    _message, payload = workload_command()

    assert handler._binding_matches(node, payload) is False


@pytest.mark.asyncio
async def test_credential_document_resolver_returns_the_full_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = command_credentials.CredentialResolveWorkloadCommandHandler()
    session = AsyncMock()
    credential_ref = uuid4()
    project_id = uuid4()
    credential = SimpleNamespace(project_id=project_id, enabled=True, secret_id=uuid4())
    credential_type = SimpleNamespace(injectors={"extra_vars": {"token": "{{token}}", "username": "service-account"}})
    secret_service = SimpleNamespace(retrieve_secret=AsyncMock(return_value={"token": "resolved-token"}))

    async def fetch_credential_with_type(
        _session: AsyncMock,
        _credential_ref: object,
    ) -> tuple[SimpleNamespace, SimpleNamespace]:
        return credential, credential_type

    monkeypatch.setattr(command_credentials, "fetch_credential_with_type", fetch_credential_with_type)
    monkeypatch.setattr(command_credentials, "create_secret_service", lambda _session: secret_service)

    document = await handler._resolve_credential_document(session, credential_ref, project_id)

    assert document == {"token": "resolved-token", "username": "service-account"}


@pytest.mark.asyncio
async def test_credential_document_resolver_rejects_missing_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = command_credentials.CredentialResolveWorkloadCommandHandler()
    session = AsyncMock()
    credential_ref = uuid4()
    project_id = uuid4()

    async def fetch_credential_with_type(
        _session: AsyncMock,
        _credential_ref: object,
    ) -> tuple[SimpleNamespace, SimpleNamespace]:
        raise IntegrationCredentialNotFoundError(credential_ref)

    monkeypatch.setattr(command_credentials, "fetch_credential_with_type", fetch_credential_with_type)

    with pytest.raises(CommandResourceStateError):
        await handler._resolve_credential_document(session, credential_ref, project_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["project-mismatch", "disabled"])
async def test_credential_document_resolver_rejects_out_of_scope_or_disabled_credentials(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    handler = command_credentials.CredentialResolveWorkloadCommandHandler()
    session = AsyncMock()
    credential_ref = uuid4()
    project_id = uuid4()
    credential_project_id = project_id if case == "disabled" else uuid4()
    credential = SimpleNamespace(
        project_id=credential_project_id,
        enabled=case != "disabled",
        secret_id=uuid4(),
    )
    credential_type = SimpleNamespace(injectors={})

    async def fetch_credential_with_type(
        _session: AsyncMock,
        _credential_ref: object,
    ) -> tuple[SimpleNamespace, SimpleNamespace]:
        return credential, credential_type

    monkeypatch.setattr(command_credentials, "fetch_credential_with_type", fetch_credential_with_type)

    with pytest.raises(CommandResourceStateError):
        await handler._resolve_credential_document(session, credential_ref, project_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [EncryptionError("decryption failed"), KeyError("secret")])
async def test_credential_document_resolver_rejects_unavailable_secrets(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    handler = command_credentials.CredentialResolveWorkloadCommandHandler()
    session = AsyncMock()
    credential_ref = uuid4()
    project_id = uuid4()
    credential = SimpleNamespace(project_id=project_id, enabled=True, secret_id=uuid4())
    credential_type = SimpleNamespace(injectors={})
    secret_service = SimpleNamespace(retrieve_secret=AsyncMock(side_effect=error))

    async def fetch_credential_with_type(
        _session: AsyncMock,
        _credential_ref: object,
    ) -> tuple[SimpleNamespace, SimpleNamespace]:
        return credential, credential_type

    monkeypatch.setattr(command_credentials, "fetch_credential_with_type", fetch_credential_with_type)
    monkeypatch.setattr(command_credentials, "create_secret_service", lambda _session: secret_service)

    with pytest.raises(CommandResourceStateError):
        await handler._resolve_credential_document(session, credential_ref, project_id)


@pytest.mark.asyncio
async def test_credential_document_resolver_rejects_empty_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = command_credentials.CredentialResolveWorkloadCommandHandler()
    session = AsyncMock()
    credential_ref = uuid4()
    project_id = uuid4()
    credential = SimpleNamespace(project_id=project_id, enabled=True, secret_id=uuid4())
    credential_type = SimpleNamespace(injectors={"extra_vars": {}})
    secret_service = SimpleNamespace(retrieve_secret=AsyncMock(return_value={}))

    async def fetch_credential_with_type(
        _session: AsyncMock,
        _credential_ref: object,
    ) -> tuple[SimpleNamespace, SimpleNamespace]:
        return credential, credential_type

    monkeypatch.setattr(command_credentials, "fetch_credential_with_type", fetch_credential_with_type)
    monkeypatch.setattr(command_credentials, "create_secret_service", lambda _session: secret_service)

    with pytest.raises(CommandResourceStateError):
        await handler._resolve_credential_document(session, credential_ref, project_id)


@pytest.mark.asyncio
async def test_workload_credential_command_handler_rejects_unexpected_payload(
    command_context: AOCommandContext,
) -> None:
    handler = command_credentials.CredentialResolveWorkloadCommandHandler()
    message, _payload = workload_command()
    payload = CredentialResolveCluster(resource_id=uuid4(), credential_ref=uuid4())

    with pytest.raises(ProtocolConflict):
        await handler.handle(message, payload, command_context)


@pytest.mark.asyncio
async def test_workload_credential_command_requires_explicit_work_item(callback) -> None:
    app, _session = callback
    message, _payload = workload_command()
    body = message.model_dump(mode="json")
    del body["command"]["payload"]["work_item_id"]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=body)
    assert response.status_code == 422
