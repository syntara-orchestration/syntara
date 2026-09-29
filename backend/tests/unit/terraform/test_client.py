"""Terraform HTTP request contracts, including safe deletion defaults."""

import json

import httpx
import pytest
import respx

from syntara.terraform.client import TFEClient
from syntara.terraform.presets import workspace_preset_parts

BASE_URL = "https://terraform.example.com/api/v2"


@pytest.fixture
def client() -> TFEClient:
    return TFEClient(base_url="https://terraform.example.com", token="test", organization="acme")  # noqa: S106


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
