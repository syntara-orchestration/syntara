"""Contract tests for AO's shared-command HTTP transport."""

import json
from uuid import uuid4

import httpx
import pytest
from execution_plane_client.commands.bulk_work import WorkCancelBulk, WorkItemSelector

from syntara.execution_plane import client as client_module
from syntara.execution_plane.client import ExecutionPlaneHttpClient, ExecutionPlaneRejectedError


def cancellation():
    return WorkCancelBulk(selector=WorkItemSelector(work_item_ids=[uuid4()])).to_message(
        source_id="syntara-orchestration", destination_id="execution-plane", client_id="syntara-orchestration"
    )


@pytest.mark.asyncio
async def test_command_transport_sends_shared_envelope_and_checks_receipt(monkeypatch):
    message = cancellation()
    requests = []

    def handle(request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202, json={"received": True, "message_id": str(message.message_id)})

    monkeypatch.setattr(client_module, "create_ep_service_token", lambda: "test-token")
    client = object.__new__(ExecutionPlaneHttpClient)
    client._client = httpx.AsyncClient(base_url="https://ep.example", transport=httpx.MockTransport(handle))
    async with client:
        receipt = await client.submit_command(message)
    assert receipt.message_id == message.message_id
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/v1/commands"
    assert requests[0].headers["Authorization"] == "Bearer test-token"
    assert json.loads(requests[0].content) == message.model_dump(mode="json")
    assert "work.cancel_bulk" in client_module.EP_SCOPES.split()
    assert {"work.cancel", "work.delete"}.isdisjoint(client_module.EP_SCOPES.split())
    assert "work.execute" in client_module.EP_SCOPES.split()
    assert {"cluster.register", "cluster.update", "cluster.delete"} <= set(client_module.EP_SCOPES.split())
    assert "clusters:read" in client_module.EP_SCOPES.split()


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"received": True, "message_id": str(uuid4())}, {"status": "accepted"}])
async def test_command_transport_rejects_invalid_or_unrelated_receipt(monkeypatch, body):
    monkeypatch.setattr(client_module, "create_ep_service_token", lambda: "test-token")
    client = object.__new__(ExecutionPlaneHttpClient)
    client._client = httpx.AsyncClient(
        base_url="https://ep.example", transport=httpx.MockTransport(lambda _: httpx.Response(202, json=body))
    )
    async with client:
        with pytest.raises(ExecutionPlaneRejectedError):
            await client.submit_command(cancellation())


@pytest.mark.asyncio
async def test_conflict_preserves_status_for_work_recovery(monkeypatch):
    monkeypatch.setattr(client_module, "create_ep_service_token", lambda: "test-token")
    client = object.__new__(ExecutionPlaneHttpClient)
    client._client = httpx.AsyncClient(
        base_url="https://ep.example",
        transport=httpx.MockTransport(lambda _: httpx.Response(409, json={"detail": "Resource conflict"})),
    )
    async with client:
        with pytest.raises(ExecutionPlaneRejectedError) as error:
            await client.submit_command(cancellation())
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_cluster_inventory_uses_actual_cluster_ids(monkeypatch):
    cluster_id = uuid4()
    integration_id = uuid4()
    requests = []

    def handle(request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "resources": [{"id": str(cluster_id), "source_integration_id": str(integration_id)}],
                "next": None,
                "prev": None,
            },
        )

    monkeypatch.setattr(client_module, "create_ep_service_token", lambda: "test-token")
    client = object.__new__(ExecutionPlaneHttpClient)
    client._client = httpx.AsyncClient(base_url="https://ep.example", transport=httpx.MockTransport(handle))
    async with client:
        result = await client.list_clusters(limit=2)
    assert requests[0].url.path == "/v1/clusters"
    assert requests[0].url.params["limit"] == "2"
    assert result["resources"][0]["id"] == str(cluster_id)
    assert result["resources"][0]["source_integration_id"] == str(integration_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["cancel", "delete"])
@pytest.mark.parametrize("field", ["work_item_ids", "project_id", "workflow_id", "execution_id"])
async def test_bulk_command_selector_wire_contract(monkeypatch, command, field):
    owner_id = uuid4()
    value = [str(owner_id)] if field == "work_item_ids" else str(owner_id)
    messages = []

    def handle(request) -> httpx.Response:
        message = json.loads(request.content)
        messages.append(message)
        return httpx.Response(202, json={"received": True, "message_id": message["message_id"]})

    monkeypatch.setattr(client_module, "create_ep_service_token", lambda: "test-token")
    client = object.__new__(ExecutionPlaneHttpClient)
    client._client = httpx.AsyncClient(base_url="https://ep.example", transport=httpx.MockTransport(handle))
    async with client:
        method = client.cancel_work_items if command == "cancel" else client.delete_work_items
        selector = {field: value} if field == "work_item_ids" else {"runtime_context": {field: value}}
        await method(selector=WorkItemSelector.model_validate(selector))
    assert len(messages) == 1
    assert messages[0]["command"]["command_type"] == f"work.{command}_bulk"
    assert messages[0]["command"]["command_revision"] == 1
    wire_selector = messages[0]["command"]["payload"]["selector"]
    assert {key: value for key, value in wire_selector.items() if value is not None} == selector
    assert f"work.{command}_bulk" in client_module.EP_SCOPES.split()
