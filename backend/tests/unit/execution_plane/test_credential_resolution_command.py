"""AO's credential-resolution callback contract."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
from execution_plane_client.commands.credentials import CredentialResolve, CredentialResolveWorkload
from execution_plane_client.errors import ProtocolConflict
from fastapi import FastAPI, Request, Response

from syntara.authz.exceptions import AuthorizationDeniedError, authorization_denied_handler
from syntara.core.config.base import get_settings
from syntara.core.database.session import get_db
from syntara.core.models.principal import service_principal_id
from syntara.execution_plane import bridge
from syntara.execution_plane.commands import credentials as command_credentials
from syntara.execution_plane.commands.context import AOCommandContext

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


def credential_command() -> MessageEnvelope:
    return CredentialResolve(credential_ref=uuid4()).to_message(
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

    async def resolve_credential(_handler: object, _session: AsyncMock, credential_ref: object) -> str:
        resolved["credential_ref"] = credential_ref
        return "resolved-token"

    monkeypatch.setattr(command_credentials.CredentialResolveCommandHandler, "_resolve_credential", resolve_credential)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=message.model_dump(mode="json"))

    assert response.status_code == 200, response.text
    assert response.json() == {
        "received": True,
        "message_id": str(message.message_id),
        "resource": None,
        "result": {
            "command_type": "credential.resolve",
            "command_revision": 1,
            "credential": "resolved-token",
        },
    }
    assert resolved["credential_ref"] == CredentialResolve.model_validate(message.command.payload).credential_ref


@pytest.mark.asyncio
async def test_credential_command_uses_credential_specific_permission(
    callback: tuple[FastAPI, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _ = callback
    authorize = AsyncMock()
    authorize.return_value.allowed = True
    monkeypatch.setattr(bridge, "authorize", authorize)
    monkeypatch.setattr(
        command_credentials.CredentialResolveCommandHandler,
        "_resolve_credential",
        AsyncMock(return_value="resolved-token"),
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post(
            "/api/execution_plane/v1/commands", json=credential_command().model_dump(mode="json")
        )

    assert response.status_code == 200, response.text
    assert authorize.await_count == 1
    await_args = authorize.await_args
    assert await_args is not None
    request_arg = await_args.args[2]
    assert request_arg.user_id == service_principal_id(get_settings().ep_callback_service_cn)
    assert request_arg.resource_type == "execution-plane-callback"
    assert request_arg.action == "resolve-credential"


@pytest.mark.asyncio
async def test_credential_command_rejects_service_principal_without_callback_role(
    callback: tuple[FastAPI, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _ = callback
    authorize = AsyncMock()
    authorize.return_value.allowed = False
    monkeypatch.setattr(bridge, "authorize", authorize)
    resolve_credential = AsyncMock(return_value="resolved-token")
    monkeypatch.setattr(
        command_credentials.CredentialResolveCommandHandler,
        "_resolve_credential",
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
@pytest.mark.parametrize("token_field", ["bearer_token", "token", "api_key"])
async def test_cluster_credential_resolver_returns_configured_token(
    monkeypatch: pytest.MonkeyPatch,
    token_field: str,
) -> None:
    session = AsyncMock()
    credential_ref = uuid4()
    credential = SimpleNamespace(enabled=True, secret_id=uuid4())
    credential_type = SimpleNamespace(injectors={"extra_vars": {token_field: "{{token}}"}})
    secret_service = SimpleNamespace(retrieve_secret=AsyncMock(return_value={"token": "resolved-token"}))

    async def fetch_credential_with_type(
        _session: AsyncMock,
        _credential_ref: object,
    ) -> tuple[SimpleNamespace, SimpleNamespace]:
        return credential, credential_type

    monkeypatch.setattr(command_credentials, "fetch_credential_with_type", fetch_credential_with_type)
    monkeypatch.setattr(command_credentials, "create_secret_service", lambda _session: secret_service)

    resolved = await command_credentials.CredentialResolveCommandHandler()._resolve_credential(
        session,
        credential_ref,
    )

    assert resolved == "resolved-token"


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

    with pytest.raises(ValueError, match="Credential is disabled"):
        await command_credentials.CredentialResolveCommandHandler()._resolve_credential(session, credential_ref)


@pytest.mark.asyncio
async def test_cluster_credential_resolver_rejects_documents_without_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    credential_ref = uuid4()
    credential = SimpleNamespace(enabled=True, secret_id=uuid4())
    credential_type = SimpleNamespace(injectors={"extra_vars": {}})
    secret_service = SimpleNamespace(retrieve_secret=AsyncMock(return_value={}))

    async def fetch_credential_with_type(
        _session: AsyncMock,
        _credential_ref: object,
    ) -> tuple[SimpleNamespace, SimpleNamespace]:
        return credential, credential_type

    monkeypatch.setattr(command_credentials, "fetch_credential_with_type", fetch_credential_with_type)
    monkeypatch.setattr(command_credentials, "create_secret_service", lambda _session: secret_service)

    with pytest.raises(ValueError, match="Credential did not resolve to an API token"):
        await command_credentials.CredentialResolveCommandHandler()._resolve_credential(session, credential_ref)


@pytest.mark.asyncio
async def test_cluster_credential_command_handler_rejects_unexpected_payload(
    command_context: AOCommandContext,
) -> None:
    message = credential_command()
    payload = CredentialResolveWorkload(
        attempt_id="attempt",
        credential_ref=uuid4(),
        credential_recipe_id="acme.echo.api-token",
        workflow_run_id="workflow-run",
        step_revision_id="step-revision",
    )

    with pytest.raises(ProtocolConflict):
        await command_credentials.CredentialResolveCommandHandler().handle(
            message,
            payload,
            command_context,
        )
