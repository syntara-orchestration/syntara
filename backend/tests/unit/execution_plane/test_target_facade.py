"""Exercise the AO HTTP contract through the real EP transport and shared command catalog."""

import json
from uuid import uuid4

import httpx
import pytest
from execution_plane_client.catalog import CommandCatalog
from execution_plane_client.protocol import MessageEnvelope
from fastapi import FastAPI, HTTPException

from syntara.api import execution_plane_facade as facade
from syntara.authz.dependencies import PermissionChecker
from syntara.authz.role_conventions import builtin_role_policy_names
from syntara.execution_plane import client as client_module
from syntara.execution_plane.client import ExecutionPlaneHttpClient

PREFIX = "/api/execution_plane/v1/execution_targets"
CLUSTER_ID = uuid4()
TARGET_ID = uuid4()
PLACEMENT = {"type": "kubernetes", "namespace": "workloads", "node_selectors": ["pool=batch"]}
TARGET = {
    "id": str(TARGET_ID),
    "cluster_id": str(CLUSTER_ID),
    "name": "batch",
    "backend_type": "vanilla_k8s",
    "endpoint": "https://cluster.example",
    "placement": PLACEMENT,
    "status": "active",
    "enabled": True,
    "is_default": False,
    "labels": {},
    "created_at": "2026-10-01T00:00:00Z",
    "api_key": "must-not-leak",
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
    state = {
        "id": str(CLUSTER_ID),
        "source_integration_id": str(uuid4()),
        "status": "active",
        "enabled": True,
        "endpoint": TARGET["endpoint"],
    }
    target = dict(TARGET)

    def handle(request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v1/clusters":
            return httpx.Response(
                200,
                json={
                    "resources": state.get("resources", [dict(state)]),
                    "next": state.get("next"),
                    "prev": None,
                },
            )
        if request.method == "POST":
            message = MessageEnvelope.model_validate_json(request.content)
            CommandCatalog().validate(message)
            target_id = message.command.payload["resource_id"]
            target["id"] = target_id
            return httpx.Response(
                200,
                json={
                    "received": True,
                    "message_id": str(message.message_id),
                    "resource": {"kind": "execution_target", "resource_id": target_id},
                    **state.get("receipt_patch", {}),
                },
            )
        return httpx.Response(200, json={**target, **state.get("target_patch", {})})

    def make_client() -> ExecutionPlaneHttpClient:
        client = object.__new__(ExecutionPlaneHttpClient)
        client._client = httpx.AsyncClient(base_url="https://ep.example", transport=httpx.MockTransport(handle))
        return client

    monkeypatch.setattr(facade, "ExecutionPlaneHttpClient", make_client)
    monkeypatch.setattr(client_module, "create_ep_service_token", lambda: "test-token")
    return app, requests, state


@pytest.mark.asyncio
@pytest.mark.parametrize("is_default", [False, True])
async def test_create_resolves_cluster_and_returns_ep_resource(harness, is_default):
    app, requests, _ = harness
    data = {"name": "batch", "placement": PLACEMENT}
    if is_default:
        data["is_default"] = True
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://ao.example") as client:
        response = await client.post(PREFIX, json=data)
    assert response.status_code == 201
    body = response.json()
    assert response.headers["location"] == f"{PREFIX}/{body['id']}"
    command = json.loads(requests[1].content)["command"]
    assert command["command_type"] == "execution_target.register"
    assert command["payload"]["cluster_id"] == str(CLUSTER_ID)
    assert command["payload"]["resource_id"] != str(CLUSTER_ID)
    assert requests[0].url.path == "/v1/clusters"
    assert requests[0].url.params["limit"] == "2"
    assert command["payload"]["placement"]["namespace"] == "workloads"
    assert command["payload"]["credential_ref"] == "00000000-0000-0000-0000-000000000000"
    assert "credential" not in command["payload"]
    assert command["payload"]["is_default"] is is_default
    assert "api_key" not in body
    assert "must-not-leak" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state_patch",
    [
        {"id": None},
        {"resources": []},
        {"resources": [{}, {}]},
        {"next": "more-clusters"},
    ],
)
async def test_create_requires_one_existing_cluster(harness, state_patch):
    app, requests, state = harness
    state.update(state_patch)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://ao.example") as client:
        response = await client.post(PREFIX, json={"name": "batch", "placement": PLACEMENT})
    assert response.status_code == 409
    assert len(requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("is_default", [False, True])
@pytest.mark.parametrize("status", ["provisioning", "error", "draining", "active"])
async def test_create_can_configure_disabled_or_unready_cluster(harness, is_default, status):
    app, requests, state = harness
    state.update({"status": status, "enabled": False, "id": str(CLUSTER_ID)})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://ao.example") as client:
        response = await client.post(PREFIX, json={"name": "batch", "placement": PLACEMENT, "is_default": is_default})
    assert response.status_code == 201
    command = json.loads(requests[1].content)["command"]
    assert command["payload"]["cluster_id"] == str(CLUSTER_ID)
    assert command["payload"]["is_default"] is is_default


@pytest.mark.asyncio
@pytest.mark.parametrize("include_type", [False, True])
async def test_patch_keeps_omissions_and_explicit_clears(harness, include_type):
    app, requests, _ = harness
    placement = {"namespace": "new", "node_selectors": []}
    if include_type:
        placement["type"] = "kubernetes"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://ao.example") as client:
        response = await client.patch(
            f"{PREFIX}/{TARGET_ID}",
            json={"placement": placement, "labels": {}},
        )
    assert response.status_code == 200
    command = json.loads(requests[0].content)["command"]
    assert command["command_type"] == "execution_target.update"
    assert command["payload"]["placement"] == {"type": "kubernetes", "namespace": "new", "node_selectors": []}
    assert command["payload"]["labels"] == {}
    assert "name" not in command["payload"]
    assert "credential" not in command["payload"]
    assert "credential_ref" not in command["payload"]


@pytest.mark.asyncio
async def test_patch_can_change_enabled_state(harness):
    app, requests, _ = harness
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://ao.example") as client:
        response = await client.patch(f"{PREFIX}/{TARGET_ID}", json={"enabled": False})

    assert response.status_code == 200
    command = json.loads(requests[0].content)["command"]
    assert command["command_type"] == "execution_target.update"
    assert command["payload"] == {"resource_id": str(TARGET_ID), "enabled": False}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "patch",
    [
        {},
        {"name": None},
        {"placement": None},
        {"labels": None},
        {"cluster_id": str(CLUSTER_ID)},
        {"name": "renamed", "cluster_id": str(CLUSTER_ID)},
        {"placement": {"type": "kubernetes", "namespace": "INVALID"}},
        {"placement": {**PLACEMENT, "node_selectors": ["invalid"]}},
    ],
)
async def test_invalid_patches_do_not_reach_ep(harness, patch):
    app, requests, _ = harness
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://ao.example") as client:
        response = await client.patch(f"{PREFIX}/{TARGET_ID}", json=patch)
    assert response.status_code == 422
    assert requests == []


@pytest.mark.asyncio
async def test_delete_uses_command_and_reports_drain_acceptance(harness):
    app, requests, _ = harness
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://ao.example") as client:
        response = await client.delete(f"{PREFIX}/{TARGET_ID}")
    assert response.status_code == 202
    assert response.json() == {"id": str(TARGET_ID), "accepted": True}
    assert len(requests) == 1
    command = json.loads(requests[0].content)["command"]
    assert command["command_type"] == "execution_target.delete"
    assert command["payload"] == {"resource_id": str(TARGET_ID)}


@pytest.mark.asyncio
@pytest.mark.parametrize(("ep_status", "expected"), [(404, 404), (409, 409), (422, 422), (403, 502), (500, 503)])
async def test_ep_errors_preserve_domain_status_without_service_auth_details(harness, monkeypatch, ep_status, expected):
    app, _, _ = harness

    def make_client() -> ExecutionPlaneHttpClient:
        client = object.__new__(ExecutionPlaneHttpClient)
        client._client = httpx.AsyncClient(
            base_url="https://ep.example",
            transport=httpx.MockTransport(lambda _: httpx.Response(ep_status, json={"detail": "EP failure"})),
        )
        return client

    monkeypatch.setattr(facade, "ExecutionPlaneHttpClient", make_client)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://ao.example") as client:
        response = await client.get(f"{PREFIX}/{TARGET_ID}")
    assert response.status_code == expected
    if expected == 502:
        assert "EP failure" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "GET", "PATCH", "DELETE"])
async def test_denied_target_operation_does_not_contact_ep(harness, method):
    app, requests, _ = harness

    async def deny() -> None:
        raise HTTPException(403, "Not permitted")

    for dependency in app.dependency_overrides:
        app.dependency_overrides[dependency] = deny
    path = PREFIX if method == "POST" else f"{PREFIX}/{TARGET_ID}"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://ao.example") as client:
        response = await client.request(method, path, json={"name": "batch", "placement": PLACEMENT})
    assert response.status_code == 403
    assert requests == []


@pytest.mark.asyncio
async def test_detail_returns_authoritative_target_without_credentials(harness):
    app, requests, _ = harness
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://ao.example") as client:
        response = await client.get(f"{PREFIX}/{TARGET_ID}")
    assert response.status_code == 200
    assert response.json()["id"] == str(TARGET_ID)
    assert response.json()["placement"]["namespace"] == "workloads"
    assert "must-not-leak" not in response.text
    assert len(requests) == 1


def test_service_token_can_submit_target_commands():
    assert {"execution_target.register", "execution_target.update", "execution_target.delete"} <= set(
        client_module.EP_SCOPES.split()
    )


@pytest.mark.parametrize("action", ["create", "update", "delete"])
def test_target_writes_are_granted_only_to_administrators(action):
    policy = f"execution_target:{action}:any"
    assert policy in builtin_role_policy_names("admin")
    for role in ("auditor", "user", "project-admin", "project-user", "project-auditor"):
        assert policy not in builtin_role_policy_names(role)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PATCH"])
@pytest.mark.parametrize("field", ["project_id", "project_ids"])
async def test_target_writes_reject_project_fields(harness, method, field):
    app, requests, _ = harness
    body = {"name": "batch", field: str(uuid4()) if field == "project_id" else [str(uuid4())]}
    path = f"{PREFIX}/{TARGET_ID}"
    if method == "POST":
        body.update({"placement": PLACEMENT})
        path = PREFIX
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://ao.example") as client:
        response = await client.request(method, path, json=body)
    assert response.status_code == 422
    assert requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field", ["integration_id", "cluster_id", "endpoint", "credential", "credential_ref", "backend_type"]
)
async def test_create_rejects_cluster_selection_and_credentials(harness, field):
    app, requests, _ = harness
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://ao.example") as client:
        response = await client.post(PREFIX, json={"name": "batch", "placement": PLACEMENT, field: "forbidden"})
    assert response.status_code == 422
    assert requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "patch",
    [
        {"id": "not-a-uuid"},
        {"endpoint": "http://insecure.example"},
        {"resources": ["invalid"]},
    ],
)
async def test_malformed_cluster_inventory_fails_before_command(harness, patch):
    app, requests, state = harness
    state.update(patch)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://ao.example") as client:
        response = await client.post(PREFIX, json={"name": "batch", "placement": PLACEMENT})
    assert response.status_code == 502
    assert len(requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "patch",
    [
        {"message_id": str(uuid4())},
        {"resource": None},
        {"resource": {"kind": "cluster", "resource_id": str(TARGET_ID)}},
        {"resource": {"kind": "execution_target", "resource_id": str(uuid4())}},
        {"received": False},
    ],
)
async def test_invalid_command_receipt_prevents_success_and_readback(harness, patch):
    app, requests, state = harness
    state["receipt_patch"] = patch
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://ao.example") as client:
        response = await client.patch(f"{PREFIX}/{TARGET_ID}", json={"name": "renamed"})
    assert response.status_code == 502
    assert len(requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "PATCH"])
async def test_readback_cannot_return_another_target(harness, method):
    app, requests, state = harness
    state["target_patch"] = {"id": str(uuid4())}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://ao.example") as client:
        response = await client.request(method, f"{PREFIX}/{TARGET_ID}", json={"name": "renamed"})
    assert response.status_code == 502
    assert len(requests) == (2 if method == "PATCH" else 1)


@pytest.mark.asyncio
async def test_default_promotion_is_forwarded_without_cluster_mutation(harness):
    app, requests, _ = harness
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://ao.example") as client:
        response = await client.patch(f"{PREFIX}/{TARGET_ID}", json={"is_default": True})
    assert response.status_code == 200
    payload = json.loads(requests[0].content)["command"]["payload"]
    assert payload == {"resource_id": str(TARGET_ID), "is_default": True}
    assert [request.url.path for request in requests] == ["/v1/commands", f"/v1/execution-targets/{TARGET_ID}"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "body"), [("DELETE", None), ("PATCH", {"is_default": False})])
async def test_protected_default_conflict_is_preserved(harness, monkeypatch, method, body):
    app, requests, _ = harness

    def handle(request) -> httpx.Response:
        requests.append(request)
        CommandCatalog().validate(MessageEnvelope.model_validate_json(request.content))
        return httpx.Response(409, json={"detail": "Promote another target before removing the default"})

    def make_client() -> ExecutionPlaneHttpClient:
        client = object.__new__(ExecutionPlaneHttpClient)
        client._client = httpx.AsyncClient(base_url="https://ep.example", transport=httpx.MockTransport(handle))
        return client

    monkeypatch.setattr(facade, "ExecutionPlaneHttpClient", make_client)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://ao.example") as client:
        response = await client.request(method, f"{PREFIX}/{TARGET_ID}", json=body)
    assert response.status_code == 409
    assert "Promote another target" in response.json()["detail"]
    assert len(requests) == 1
