"""AO's credential-resolution callback contract."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from execution_plane_client.commands.credentials import CredentialResolve
from fastapi import FastAPI, Request, Response

from syntara.core.config.base import get_settings
from syntara.core.database.session import get_db
from syntara.execution_plane import bridge
from syntara.execution_plane.commands import credentials as command_credentials

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


def credential_command() -> MessageEnvelope:
    return CredentialResolve(credential_ref=uuid4()).to_message(
        source_id="execution-plane",
        destination_id="syntara-orchestration",
        client_id="syntara-orchestration",
    )


@pytest.mark.asyncio
async def test_credential_command_returns_typed_correlated_resolution(
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
    assert response.json() == {"message_id": str(message.message_id), "credential": "resolved-token"}
    assert resolved["credential_ref"] == CredentialResolve.model_validate(message.command.payload).credential_ref


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
