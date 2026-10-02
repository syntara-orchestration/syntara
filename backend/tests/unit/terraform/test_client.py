"""Terraform HTTP request contracts, including safe deletion defaults."""

import json
from unittest.mock import patch

import httpx
import pytest
import respx

from syntara.terraform.client import (
    DEFAULT_TFE_HTTP_TIMEOUT_SECONDS,
    TFEClient,
    resolve_http_timeout_from_engine,
)
from syntara.terraform.errors import TFEError, TFEErrorCode
from syntara.terraform.presets import workspace_preset_parts

BASE_URL = "https://terraform.example.com/api/v2"


@pytest.fixture
def client() -> TFEClient:
    return TFEClient(base_url="https://terraform.example.com", token="test", organization="acme")  # noqa: S106


def test_resolve_http_timeout_from_engine_leaves_margin() -> None:
    """Client HTTP budget must stay under the activity timeout."""
    assert resolve_http_timeout_from_engine(180) == 170.0
    assert resolve_http_timeout_from_engine(900) == 890.0
    assert resolve_http_timeout_from_engine(5) == 1.0
    assert resolve_http_timeout_from_engine(None) == DEFAULT_TFE_HTTP_TIMEOUT_SECONDS


def test_request_timeout_divides_budget_for_reads() -> None:
    """Read retries share the activity HTTP budget; mutating calls use the full budget."""
    client = TFEClient(
        base_url="https://terraform.example.com",
        token="test",  # noqa: S106
        organization="acme",
        timeout_seconds=170.0,
    )
    assert client._request_timeout(mutating=True) == 170.0
    assert client._request_timeout(mutating=False) == pytest.approx(170.0 / 3)


@pytest.mark.asyncio
@respx.mock
async def test_default_delete_uses_safe_delete(client: TFEClient) -> None:
    route = respx.post(f"{BASE_URL}/workspaces/ws-1/actions/safe-delete").mock(return_value=httpx.Response(204))
    await client.delete_workspace("ws-1")
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_force_delete_requires_explicit_opt_in(client: TFEClient) -> None:
    route = respx.delete(f"{BASE_URL}/workspaces/ws-1").mock(return_value=httpx.Response(204))
    await client.delete_workspace("ws-1", force=True)
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_variable_mutations_are_workspace_scoped(client: TFEClient) -> None:
    update = respx.patch(f"{BASE_URL}/workspaces/ws-1/vars/var-1").mock(
        return_value=httpx.Response(200, json={"data": {"id": "var-1"}})
    )
    delete = respx.delete(f"{BASE_URL}/workspaces/ws-1/vars/var-1").mock(return_value=httpx.Response(204))
    await client.update_variable("ws-1", "var-1", {"value": "updated"})
    await client.delete_variable("ws-1", "var-1")
    assert json.loads(update.calls[0].request.content)["data"]["attributes"] == {"value": "updated"}
    assert delete.called


@pytest.mark.asyncio
@respx.mock
async def test_github_installation_endpoints(client: TFEClient) -> None:
    listing = respx.get(f"{BASE_URL}/github-app/installations").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    detail = respx.get(f"{BASE_URL}/github-app/installation/ghain-1").mock(
        return_value=httpx.Response(200, json={"data": {"id": "ghain-1"}})
    )
    await client.list_github_app_installations()
    await client.get_github_app_installation("ghain-1")
    assert listing.called
    assert detail.called


@pytest.mark.asyncio
@respx.mock
async def test_agent_pool_is_sent_as_workspace_attribute(client: TFEClient) -> None:
    route = respx.post(f"{BASE_URL}/organizations/acme/workspaces").mock(
        return_value=httpx.Response(201, json={"data": {"id": "ws-1"}})
    )
    attributes, relationships = workspace_preset_parts("agent", agent_pool_id="apool-1")
    await client.create_workspace("demo", attributes=attributes, relationships=relationships)
    data = json.loads(route.calls[0].request.content)["data"]
    assert data["attributes"]["agent-pool-id"] == "apool-1"
    assert "relationships" not in data


@pytest.mark.asyncio
@respx.mock
async def test_upload_configuration_version_omits_authorization(client: TFEClient) -> None:
    upload_url = "https://uploads.example.com/config?X-Amz-Signature=abc"
    route = respx.put(upload_url).mock(return_value=httpx.Response(200))
    with patch(
        "syntara.terraform.client.validate_url_no_ssrf",
    ) as mock_validate:
        await client.upload_configuration_version(upload_url, b"archive-bytes")
    mock_validate.assert_called_once()
    assert route.called
    request = route.calls[0].request
    assert "Authorization" not in request.headers
    assert request.headers["Content-Type"] == "application/octet-stream"
    assert request.content == b"archive-bytes"


@pytest.mark.asyncio
async def test_upload_configuration_version_rejects_unsafe_url(client: TFEClient) -> None:
    with (
        patch(
            "syntara.terraform.client.validate_url_no_ssrf",
            side_effect=ValueError("URL resolves to a private IP address"),
        ),
        pytest.raises(TFEError) as exc_info,
    ):
        await client.upload_configuration_version("http://169.254.169.254/latest/meta-data/", b"x")
    assert exc_info.value.error_code == TFEErrorCode.VALIDATION
    assert exc_info.value.retryable is False
