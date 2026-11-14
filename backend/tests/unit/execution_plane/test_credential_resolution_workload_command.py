"""Workload-scoped credential resolution command handling."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import httpx
import pytest
from execution_plane_client.commands.credentials import CredentialResolve, CredentialResolveWorkload
from execution_plane_client.errors import ProtocolConflict
from fastapi import FastAPI, Request, Response

from syntara.core.config.base import get_settings
from syntara.core.database.session import get_db
from syntara.core.lib.encryption import EncryptionError
from syntara.execution_plane import bridge
from syntara.execution_plane.commands import credentials as command_credentials
from syntara.execution_plane.commands.context import AOCommandContext
from syntara.execution_plane.commands.errors import CommandResourceStateError
from syntara.execution_plane.utils import execution_plane_work_item_id
from syntara.integrations.exceptions import IntegrationCredentialNotFoundError
from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution
from syntara.workflows.models.workflow_definition import ConditionNode
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.workflow_engine.models.workflow_definition import ConditionNodeParameters

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from execution_plane_client.protocol import MessageEnvelope


@pytest.fixture
def callback() -> tuple[FastAPI, AsyncMock]:
    app = FastAPI()
    app.include_router(bridge.router)
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
    credential_ref: UUID | None = None,
    credential_recipe_id: str = "acme.echo.api-token",
) -> tuple[MessageEnvelope, CredentialResolveWorkload]:
    message = CredentialResolveWorkload(
        work_item_id=uuid4(),
        attempt_id="attempt",
        credential_ref=credential_ref or uuid4(),
        credential_recipe_id=credential_recipe_id,
        step_revision_id="step-revision",
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
    resolved: dict[str, object] = {}

    async def load_activity(_handler: object, _session: AsyncMock, work_item_id: object) -> ActivityExecution:
        assert work_item_id == UUID(str(message.command.payload["work_item_id"]))
        return row

    async def resolve_document(
        _handler: object,
        _session: AsyncMock,
        credential_ref: object,
        _project_id: object,
    ) -> dict[str, str]:
        resolved["credential_ref"] = credential_ref
        return {"token": "resolved-token"}

    monkeypatch.setattr(command_credentials.CredentialResolveWorkloadCommandHandler, "_load_activity", load_activity)
    monkeypatch.setattr(
        command_credentials.CredentialResolveWorkloadCommandHandler, "_resolve_credential_document", resolve_document
    )

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
            "command_revision": 2,
            "credential": {"token": "resolved-token"},
        },
    }
    assert resolved["credential_ref"] == payload.credential_ref


@pytest.mark.asyncio
async def test_workload_credential_command_rejects_missing_activity(
    callback: tuple[FastAPI, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _ = callback
    message, _ = workload_command()

    async def load_activity(_handler: object, _session: AsyncMock, _work_item_id: object) -> ActivityExecution | None:
        return None

    monkeypatch.setattr(command_credentials.CredentialResolveWorkloadCommandHandler, "_load_activity", load_activity)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=message.model_dump(mode="json"))

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_workload_credential_command_rejects_terminal_activity(
    callback: tuple[FastAPI, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _ = callback
    message, payload = workload_command(credential_ref=uuid4())

    async def load_activity(_handler: object, _session: AsyncMock, _work_item_id: object) -> ActivityExecution:
        return activity(status=ActivityStatus.COMPLETED, credential_ref=payload.credential_ref)

    monkeypatch.setattr(command_credentials.CredentialResolveWorkloadCommandHandler, "_load_activity", load_activity)

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

    async def load_activity(_handler: object, _session: AsyncMock, _work_item_id: object) -> ActivityExecution:
        return row

    monkeypatch.setattr(command_credentials.CredentialResolveWorkloadCommandHandler, "_load_activity", load_activity)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=message.model_dump(mode="json"))

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_load_activity_returns_the_matching_row() -> None:
    handler = command_credentials.CredentialResolveWorkloadCommandHandler()
    session = AsyncMock()
    result = MagicMock()
    expected = object()
    result.one_or_none.return_value = expected
    session.exec.return_value = result

    loaded = await handler._load_activity(session, uuid4())

    assert loaded is expected
    session.exec.assert_awaited_once()
    result.one_or_none.assert_called_once_with()


def test_node_lookup_rejects_invalid_workflow_definitions() -> None:
    handler = command_credentials.CredentialResolveWorkloadCommandHandler()
    row = activity(workflow_definition={"schema_version": "invalid"})

    with pytest.raises(CommandResourceStateError):
        handler._node_for_activity(row)


def test_node_lookup_rejects_activities_without_matching_nodes() -> None:
    handler = command_credentials.CredentialResolveWorkloadCommandHandler()
    definition: dict[str, object] = {
        "schema_version": "2.0.0",
        "name": "workflow",
        "triggers": [{"id": "trigger", "type": "manual"}],
        "nodes": [
            {
                "id": "other-node",
                "type": "approval",
                "parameters": {"credential_bindings": []},
            }
        ],
        "edges": [],
    }
    row = activity(workflow_definition=definition)

    with pytest.raises(CommandResourceStateError):
        handler._node_for_activity(row)


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
    payload = CredentialResolve(credential_ref=uuid4())

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
