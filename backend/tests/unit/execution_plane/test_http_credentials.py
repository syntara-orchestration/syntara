"""HTTP integration authorization before secret resolution."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from syntara.execution_plane.commands.errors import CommandResourceStateError
from syntara.execution_plane.http_credentials import HTTP_BEARER_RECIPE, authorize_http_binding, https_origin
from syntara.integrations.adapters.http import HTTPAdapter
from syntara.integrations.exceptions import IntegrationCredentialNotFoundError
from syntara.integrations.models.integration import IntegrationScope, IntegrationType
from syntara.integrations.models.integration_configuration import HTTPConfiguration
from syntara.workflow_core.models import APIExecutorParameters


@pytest.mark.parametrize("url", ["http://example.com", "https://user:pass@example.com", "https://example.com:0"])
def test_invalid_credential_destination(url: str) -> None:
    with pytest.raises(ValueError):
        https_origin(url)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "origin", "credential", "disabled", "project", "type", "scope"])
async def test_authorize_stored_http_integration(monkeypatch: pytest.MonkeyPatch, failure: str | None) -> None:
    project_id, credential_id, integration_id = uuid4(), uuid4(), uuid4()
    config = APIExecutorParameters.model_validate(
        {
            "method": "GET",
            "url": "https://other.example.com/data" if failure == "origin" else "https://example.com/data",
            "integration_id": integration_id,
            "credential_bindings": [{"credential_recipe_id": HTTP_BEARER_RECIPE, "credential_ref": credential_id}],
        }
    )
    integration = SimpleNamespace(
        id=integration_id,
        enabled=failure != "disabled",
        integration_type=IntegrationType.HTTP,
        configuration=HTTPConfiguration(base_url="https://example.com"),
        management_credential_id=uuid4() if failure == "credential" else credential_id,
        scope=IntegrationScope.PROJECT if failure == "scope" else IntegrationScope.GLOBAL,
    )
    session = AsyncMock()
    session.get.return_value = integration
    session.exec.return_value = SimpleNamespace(first=lambda: None)
    metadata = AsyncMock(
        return_value=(
            SimpleNamespace(enabled=True, project_id=uuid4() if failure == "project" else project_id),
            SimpleNamespace(name="HTTP Basic Auth" if failure == "type" else "HTTP Bearer Token"),
        )
    )
    monkeypatch.setattr("syntara.execution_plane.http_credentials.fetch_credential_with_type", metadata)
    if failure:
        with pytest.raises(CommandResourceStateError):
            await authorize_http_binding(session, config, project_id)
    else:
        assert await authorize_http_binding(session, config, project_id) == "https://example.com"


@pytest.mark.parametrize(
    "values",
    [
        {"base_url": "http://localhost"},
        {"base_url": "https://example.com/path"},
        {"base_url": "https://user:pass@example.com"},
        {"base_url": "https://example.com", "allow_http": True},
        {"base_url": "https://example.com", "insecure_skip_tls_verify": True},
    ],
)
def test_http_configuration_rejects_unsafe_settings(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        HTTPConfiguration.model_validate(values)


@pytest.mark.asyncio
async def test_missing_credential_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    credential_id = uuid4()
    config = APIExecutorParameters.model_validate(
        {
            "method": "GET",
            "url": "https://example.com/data",
            "integration_id": uuid4(),
            "credential_bindings": [{"credential_recipe_id": HTTP_BEARER_RECIPE, "credential_ref": credential_id}],
        }
    )
    session = AsyncMock()
    session.get.return_value = SimpleNamespace(
        enabled=True,
        integration_type=IntegrationType.HTTP,
        configuration=HTTPConfiguration(base_url="https://example.com"),
        management_credential_id=credential_id,
        scope=IntegrationScope.GLOBAL,
    )
    monkeypatch.setattr(
        "syntara.execution_plane.http_credentials.fetch_credential_with_type",
        AsyncMock(side_effect=IntegrationCredentialNotFoundError(credential_id)),
    )
    with pytest.raises(CommandResourceStateError):
        await authorize_http_binding(session, config, uuid4())


@pytest.mark.asyncio
async def test_connection_check_does_not_follow_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://other.example.com"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond), follow_redirects=False)
    context = AsyncMock()
    context.__aenter__.return_value = client
    constructor = Mock(return_value=context)
    monkeypatch.setattr("syntara.integrations.adapters.http.httpx.AsyncClient", constructor)
    adapter = HTTPAdapter(HTTPConfiguration(base_url="https://example.com"))
    try:
        await adapter.validate({"bearer_token": "test-token"}, 5)
    finally:
        await client.aclose()
    constructor.assert_called_once_with(timeout=5, follow_redirects=False, trust_env=False)
    assert len(requests) == 1
    assert requests[0].url.host == "example.com"
    assert requests[0].headers["Authorization"] == "Bearer test-token"
