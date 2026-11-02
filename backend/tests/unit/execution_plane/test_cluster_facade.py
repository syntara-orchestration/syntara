"""Exercise the standalone cluster registration through the real EP transport and command catalog."""

import json
from uuid import uuid4

import httpx
import pytest
from execution_plane_client.catalog import CommandCatalog
from execution_plane_client.protocol import MessageEnvelope
from fastapi import FastAPI

from syntara.api import execution_plane_facade as facade
from syntara.authz.dependencies import PermissionChecker
from syntara.execution_plane import client as client_module
from syntara.execution_plane.client import ExecutionPlaneHttpClient
from syntara.execution_plane.clusters import standalone_cluster_resource_key

PREFIX = "/api/execution_plane/v1/clusters"
CLUSTER_ID = uuid4()
CREDENTIAL_REF = uuid4()
RESOURCE_KEY = standalone_cluster_resource_key("kind")
CLUSTER = {
    "id": str(CLUSTER_ID),
    "source_integration_id": str(RESOURCE_KEY),
    "name": "kind",
    "endpoint": "https://kubernetes.default.svc",
    "status": "active",
    "status_message": None,
    "enabled": True,
    "is_default": False,
    "labels": {"execution-plane.syntara.io/local": "kind"},
    "project_ids": None,
    "created_at": "2026-10-30T00:00:00Z",
    "updated_at": "2026-10-30T00:00:00Z",
    "api_key": "must-not-leak",
}
REGISTRATION = {
    "name": "kind",
    "endpoint": "https://kubernetes.default.svc",
    "namespace": "execution-plane",
    "credential_ref": str(CREDENTIAL_REF),
    "labels": {"execution-plane.syntara.io/local": "kind"},
}


async def allow():
    return None


@pytest.fixture
def harness(monkeypatch):
    app = FastAPI()
    app.include_router(facade.router)
    for route in facade.router.routes:
        for dependency in getattr(route, "dependencies", []):
            if isinstance(dependency.dependency, PermissionChecker):
                app.dependency_overrides[dependency.dependency] = allow

    requests = []
    state = {"resources": None, "receipt_resource": {"kind": "cluster", "resource_id": str(CLUSTER_ID)}}

    def handle(request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v1/clusters":
            resources = state["resources"]
            if resources is None:
                wanted = request.url.params.get("source_integration_id")
                resources = [dict(c) for c in [CLUSTER] if wanted in (None, c["source_integration_id"])]
            return httpx.Response(200, json={"resources": [dict(c) for c in resources], "next": None, "prev": None})
        if request.method == "POST":
            message = MessageEnvelope.model_validate_json(request.content)
            CommandCatalog().validate(message)
            return httpx.Response(
                200,
                json={
                    "received": True,
                    "message_id": str(message.message_id),
                    "resource": state["receipt_resource"],
                },
            )
        return httpx.Response(404)

    def make_client() -> ExecutionPlaneHttpClient:
        client = object.__new__(ExecutionPlaneHttpClient)
        client._client = httpx.AsyncClient(base_url="https://ep.example", transport=httpx.MockTransport(handle))
        return client

    monkeypatch.setattr(facade, "ExecutionPlaneHttpClient", make_client)
    monkeypatch.setattr(client_module, "create_ep_service_token", lambda: "test-token")
    return app, requests, state


@pytest.mark.asyncio
async def test_register_sends_cluster_provision_and_returns_ep_resource(harness):
    app, requests, _ = harness
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://ao.example") as client:
        response = await client.post(PREFIX, json=REGISTRATION)
    assert response.status_code == 201
    body = response.json()
    assert response.headers["location"] == f"{PREFIX}/{body['id']}"
    command = json.loads(requests[0].content)["command"]
    assert command["command_type"] == "cluster.provision"
    assert command["payload"]["resource_key"] == str(RESOURCE_KEY)
    assert command["payload"]["desired_revision"] == 1
    assert command["payload"]["name"] == "kind"
    assert command["payload"]["endpoint"] == "https://kubernetes.default.svc"
    assert command["payload"]["namespace"] == "execution-plane"
    assert command["payload"]["credential_ref"] == str(CREDENTIAL_REF)
    assert command["payload"]["labels"] == {"execution-plane.syntara.io/local": "kind"}
    # Read back through the stable source key.
    assert requests[1].url.path == "/v1/clusters"
    assert requests[1].url.params["source_integration_id"] == str(RESOURCE_KEY)
    assert body["id"] == str(CLUSTER_ID)
    assert "must-not-leak" not in response.text


@pytest.mark.asyncio
async def test_register_is_keyed_by_name_for_idempotency(harness):
    app, requests, _ = harness
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://ao.example") as client:
        first = await client.post(PREFIX, json=REGISTRATION)
        second = await client.post(PREFIX, json=REGISTRATION)
    assert first.status_code == second.status_code == 201
    first_key = json.loads(requests[0].content)["command"]["payload"]["resource_key"]
    second_key = json.loads(requests[2].content)["command"]["payload"]["resource_key"]
    assert first_key == second_key
    other = {**REGISTRATION, "name": "other-cluster"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://ao.example") as client:
        await client.post(PREFIX, json=other)
    third_key = json.loads(requests[4].content)["command"]["payload"]["resource_key"]
    assert third_key != first_key


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state_patch",
    [
        {"resources": []},
        {"resources": [{}, {}]},
        {"receipt_resource": None},
        {"receipt_resource": {"kind": "execution_target", "resource_id": str(CLUSTER_ID)}},
    ],
)
async def test_register_rejects_invalid_readback_or_receipt(harness, state_patch):
    app, _, state = harness
    state.update(state_patch)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://ao.example") as client:
        response = await client.post(PREFIX, json=REGISTRATION)
    assert response.status_code == 502


@pytest.mark.asyncio
async def test_register_validates_payload(harness):
    app, _, _ = harness
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://ao.example") as client:
        bad_namespace = await client.post(PREFIX, json={**REGISTRATION, "namespace": "Bad_NS!"})
        extra_field = await client.post(PREFIX, json={**REGISTRATION, "unexpected": True})
    assert bad_namespace.status_code == 422
    assert extra_field.status_code == 422


@pytest.mark.asyncio
async def test_list_forwards_filters_and_hides_secrets(harness):
    app, requests, _ = harness
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://ao.example") as client:
        response = await client.get(PREFIX, params={"limit": 5, "name": "kind"})
    assert response.status_code == 200
    body = response.json()
    assert [resource["id"] for resource in body["resources"]] == [str(CLUSTER_ID)]
    assert "must-not-leak" not in response.text
    assert requests[0].url.path == "/v1/clusters"
    assert requests[0].url.params["limit"] == "5"
    assert requests[0].url.params["name"] == "kind"
