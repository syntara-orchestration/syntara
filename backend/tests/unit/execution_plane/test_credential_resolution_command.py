"""AO's credential-resolution callback contract."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import httpx
import pytest
from execution_plane_client.commands.credentials import CredentialResolveCluster, CredentialResolveWorkload
from execution_plane_client.errors import ProtocolConflict
from fastapi import FastAPI, Request, Response

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.authz.exceptions import AuthorizationDeniedError, authorization_denied_handler
from syntara.core.config.base import get_settings
from syntara.core.database.session import get_db
from syntara.core.models.principal import service_principal_id
from syntara.credentials.audit.credential import CredentialClusterResolvedEvent
from syntara.execution_plane import bridge
from syntara.execution_plane.commands import credentials as command_credentials
from syntara.execution_plane.commands.context import AOCommandContext
from syntara.execution_plane.commands.errors import CommandResourceStateError
from syntara.integrations.models.integration import IntegrationType

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

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


def credential_command(*, resource_id: UUID | None = None, credential_ref: UUID | None = None) -> MessageEnvelope:
    return CredentialResolveCluster(
        resource_id=resource_id or uuid4(),
        credential_ref=credential_ref or uuid4(),
    ).to_message(
        source_id="execution-plane",
        destination_id="syntara-orchestration",
        client_id="syntara-orchestration",
    )


@pytest.fixture
def command_context() -> AOCommandContext:
    return AOCommandContext(session=AsyncMock(), temporal_service=None)


@pytest.mark.asyncio
async def test_credential_command_returns_typed_correlated_transport_receipt(
    callback: tuple[FastAPI, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _ = callback
    message = credential_command()
    resolved: dict[str, Any] = {}
    payload = CredentialResolveCluster.model_validate(message.command.payload)
    integration = SimpleNamespace(
        integration_type=IntegrationType.OPENSHIFT,
        management_credential_id=payload.credential_ref,
        enabled=True,
    )
    dispatch = MagicMock()

    async def resolve_credential(
        _handler: object,
        _session: AsyncMock,
        credential_ref: object,
    ) -> dict[str, str]:
        resolved["credential_ref"] = credential_ref
        return {"bearer_token": "resolved-token"}

    monkeypatch.setattr(
        command_credentials.CredentialResolveClusterCommandHandler,
        "_load_integration",
        AsyncMock(return_value=integration),
    )
    monkeypatch.setattr(AuditEventDispatcher, "dispatch", dispatch)
    monkeypatch.setattr(
        command_credentials.CredentialResolveClusterCommandHandler,
        "_resolve_credential_document",
        resolve_credential,
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=message.model_dump(mode="json"))

    assert response.status_code == 200, response.text
    assert response.json() == {
        "received": True,
        "message_id": str(message.message_id),
        "resource": {
            "kind": "cluster",
            "resource_id": str(payload.resource_id),
            "resource_key": None,
            "revision": None,
        },
        "result": {
            "command_type": "credential.resolve.cluster",
            "command_revision": 1,
            "credential": {"bearer_token": "resolved-token"},
        },
    }
    assert resolved["credential_ref"] == payload.credential_ref
    dispatch.assert_called_once()
    event = dispatch.call_args.args[0]
    assert isinstance(event, CredentialClusterResolvedEvent)
    assert event.credential_id == payload.credential_ref
    assert event.integration_id == payload.resource_id
    assert event.message_id == message.message_id
    assert event.service_identity == message.source_id


@pytest.mark.asyncio
async def test_credential_command_uses_credential_specific_permission(
    callback: tuple[FastAPI, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _ = callback
    authorize = AsyncMock()
    authorize.return_value.allowed = True
    message = credential_command()
    payload = CredentialResolveCluster.model_validate(message.command.payload)
    monkeypatch.setattr(bridge, "authorize", authorize)
    monkeypatch.setattr(AuditEventDispatcher, "dispatch", MagicMock())
    monkeypatch.setattr(
        command_credentials.CredentialResolveClusterCommandHandler,
        "_load_integration",
        AsyncMock(
            return_value=SimpleNamespace(
                integration_type=IntegrationType.OPENSHIFT,
                management_credential_id=payload.credential_ref,
                enabled=True,
            )
        ),
    )
    monkeypatch.setattr(
        command_credentials.CredentialResolveClusterCommandHandler,
        "_resolve_credential_document",
        AsyncMock(return_value={"bearer_token": "resolved-token"}),
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
    assert request_arg.action == "resolve-credential-cluster"


@pytest.mark.asyncio
async def test_credential_command_rejects_service_principal_without_callback_role(
    callback: tuple[FastAPI, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _ = callback
    authorize = AsyncMock()
    authorize.return_value.allowed = False
    monkeypatch.setattr(bridge, "authorize", authorize)
    resolve_credential = AsyncMock(return_value={"bearer_token": "resolved-token"})
    monkeypatch.setattr(
        command_credentials.CredentialResolveClusterCommandHandler,
        "_resolve_credential_document",
        resolve_credential,
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post(
            "/api/execution_plane/v1/commands", json=credential_command().model_dump(mode="json")
        )

    assert response.status_code == 403
    authorize.assert_awaited_once()
    resolve_credential.assert_not_awaited()


@pytest.mark.asyncio
async def test_credential_command_rejects_wrong_certificate_identity(
    callback: tuple[FastAPI, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _ = callback
    monkeypatch.setattr(
        bridge,
        "get_settings",
        lambda: SimpleNamespace(ep_callback_service_cn="other-allowlisted-service"),
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post(
            "/api/execution_plane/v1/commands", json=credential_command().model_dump(mode="json")
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_credential_command_rejects_wrong_participant(callback: tuple[FastAPI, AsyncMock]) -> None:
    app, _ = callback
    body = credential_command().model_dump(mode="json")
    body["destination_id"] = "other-service"

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=body)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_credential_command_rejects_invalid_command(callback: tuple[FastAPI, AsyncMock]) -> None:
    app, _ = callback
    body = credential_command().model_dump(mode="json")
    body["command"]["command_revision"] = 2

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=body)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_credential_command_requires_cluster_identity(callback: tuple[FastAPI, AsyncMock]) -> None:
    app, _ = callback
    body = credential_command().model_dump(mode="json")
    del body["command"]["payload"]["resource_id"]

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=body)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_cluster_credential_resolver_returns_full_document(monkeypatch: pytest.MonkeyPatch) -> None:
    session = AsyncMock()
    credential_ref = uuid4()
    credential = SimpleNamespace(enabled=True, secret_id=uuid4())
    credential_type = SimpleNamespace(injectors={"extra_vars": {"username": "{{username}}", "token": "{{token}}"}})
    secret_service = SimpleNamespace(
        retrieve_secret=AsyncMock(return_value={"username": "service-account", "token": "resolved-token"})
    )

    async def fetch_credential_with_type(
        _session: AsyncMock,
        _credential_ref: object,
    ) -> tuple[SimpleNamespace, SimpleNamespace]:
        return credential, credential_type

    monkeypatch.setattr(command_credentials, "fetch_credential_with_type", fetch_credential_with_type)
    monkeypatch.setattr(command_credentials, "create_secret_service", lambda _session: secret_service)

    resolved = await command_credentials.CredentialResolveClusterCommandHandler()._resolve_credential_document(
        session,
        credential_ref,
    )

    assert resolved == {"username": "service-account", "token": "resolved-token"}


@pytest.mark.asyncio
async def test_cluster_credential_resolver_rejects_disabled_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    credential_ref = uuid4()
    credential = SimpleNamespace(enabled=False, secret_id=uuid4())
    credential_type = SimpleNamespace(injectors={})

    async def fetch_credential_with_type(
        _session: AsyncMock,
        _credential_ref: object,
    ) -> tuple[SimpleNamespace, SimpleNamespace]:
        return credential, credential_type

    monkeypatch.setattr(command_credentials, "fetch_credential_with_type", fetch_credential_with_type)

    with pytest.raises(CommandResourceStateError):
        await command_credentials.CredentialResolveClusterCommandHandler()._resolve_credential_document(
            session,
            credential_ref,
        )


@pytest.mark.asyncio
async def test_cluster_credential_resolver_returns_documents_without_supported_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    credential_ref = uuid4()
    credential = SimpleNamespace(enabled=True, secret_id=uuid4())
    credential_type = SimpleNamespace(injectors={"extra_vars": {"username": "{{username}}"}})
    secret_service = SimpleNamespace(retrieve_secret=AsyncMock(return_value={"username": "service-account"}))

    async def fetch_credential_with_type(
        _session: AsyncMock,
        _credential_ref: object,
    ) -> tuple[SimpleNamespace, SimpleNamespace]:
        return credential, credential_type

    monkeypatch.setattr(command_credentials, "fetch_credential_with_type", fetch_credential_with_type)
    monkeypatch.setattr(command_credentials, "create_secret_service", lambda _session: secret_service)

    resolved = await command_credentials.CredentialResolveClusterCommandHandler()._resolve_credential_document(
        session,
        credential_ref,
    )

    assert resolved == {"username": "service-account"}


@pytest.mark.asyncio
async def test_cluster_credential_command_handler_rejects_unexpected_payload(
    command_context: AOCommandContext,
) -> None:
    message = credential_command()
    payload = CredentialResolveWorkload(
        work_item_id=uuid4(),
        attempt_id="attempt",
        credential_ref=uuid4(),
        credential_recipe_id="acme.echo.api-token",
        step_revision_id="step-revision",
    )

    with pytest.raises(ProtocolConflict):
        await command_credentials.CredentialResolveClusterCommandHandler().handle(
            message,
            payload,
            command_context,
        )


@pytest.mark.asyncio
async def test_cluster_credential_command_handler_validates_ownership_and_audits_resolution(
    monkeypatch: pytest.MonkeyPatch,
    command_context: AOCommandContext,
) -> None:
    resource_id = uuid4()
    credential_ref = uuid4()
    message = credential_command(resource_id=resource_id, credential_ref=credential_ref)
    payload = CredentialResolveCluster.model_validate(message.command.payload)
    integration = SimpleNamespace(
        integration_type=IntegrationType.OPENSHIFT,
        management_credential_id=credential_ref,
        enabled=True,
    )
    dispatch = MagicMock()
    monkeypatch.setattr(AuditEventDispatcher, "dispatch", dispatch)
    monkeypatch.setattr(
        command_credentials.CredentialResolveClusterCommandHandler,
        "_load_integration",
        AsyncMock(return_value=integration),
    )
    monkeypatch.setattr(
        command_credentials.CredentialResolveClusterCommandHandler,
        "_resolve_credential_document",
        AsyncMock(return_value={"bearer_token": "resolved-token"}),
    )

    handled = await command_credentials.CredentialResolveClusterCommandHandler().handle(
        message,
        payload,
        command_context,
    )

    assert handled.resource is not None
    assert handled.resource.resource_id == resource_id
    dispatch.assert_called_once()
    event = dispatch.call_args.args[0]
    assert isinstance(event, CredentialClusterResolvedEvent)
    assert event.credential_id == credential_ref
    assert event.integration_id == resource_id
    assert event.message_id == message.message_id
    assert event.service_identity == message.source_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "integration",
    [
        None,
        SimpleNamespace(integration_type=IntegrationType.MCP_SERVER, management_credential_id=uuid4()),
        SimpleNamespace(integration_type=IntegrationType.OPENSHIFT, management_credential_id=uuid4()),
        SimpleNamespace(integration_type=IntegrationType.OPENSHIFT, management_credential_id=None),
    ],
)
async def test_cluster_credential_command_handler_rejects_invalid_ownership(
    integration: SimpleNamespace | None,
    monkeypatch: pytest.MonkeyPatch,
    command_context: AOCommandContext,
) -> None:
    message = credential_command()
    payload = CredentialResolveCluster.model_validate(message.command.payload)
    dispatch = MagicMock()
    resolve_credential = AsyncMock(return_value={"bearer_token": "resolved-token"})
    monkeypatch.setattr(AuditEventDispatcher, "dispatch", dispatch)
    monkeypatch.setattr(
        command_credentials.CredentialResolveClusterCommandHandler,
        "_load_integration",
        AsyncMock(return_value=integration),
    )
    monkeypatch.setattr(
        command_credentials.CredentialResolveClusterCommandHandler,
        "_resolve_credential_document",
        resolve_credential,
    )

    with pytest.raises(CommandResourceStateError):
        await command_credentials.CredentialResolveClusterCommandHandler().handle(
            message,
            payload,
            command_context,
        )

    resolve_credential.assert_not_awaited()
    dispatch.assert_not_called()


async def test_cluster_credential_command_handler_rejects_disabled_integration(
    monkeypatch: pytest.MonkeyPatch,
    command_context: AOCommandContext,
) -> None:
    message = credential_command()
    payload = CredentialResolveCluster.model_validate(message.command.payload)
    integration = SimpleNamespace(
        integration_type=IntegrationType.OPENSHIFT,
        management_credential_id=payload.credential_ref,
        enabled=False,
    )
    dispatch = MagicMock()
    resolve_credential = AsyncMock(return_value={"bearer_token": "resolved-token"})
    monkeypatch.setattr(AuditEventDispatcher, "dispatch", dispatch)
    monkeypatch.setattr(
        command_credentials.CredentialResolveClusterCommandHandler,
        "_load_integration",
        AsyncMock(return_value=integration),
    )
    monkeypatch.setattr(
        command_credentials.CredentialResolveClusterCommandHandler,
        "_resolve_credential_document",
        resolve_credential,
    )

    with pytest.raises(CommandResourceStateError):
        await command_credentials.CredentialResolveClusterCommandHandler().handle(
            message,
            payload,
            command_context,
        )

    resolve_credential.assert_not_awaited()
    dispatch.assert_not_called()
