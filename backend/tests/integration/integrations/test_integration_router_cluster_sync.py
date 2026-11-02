"""Integration writes persist desired state even when EP delivery fails."""

from typing import Never
from uuid import UUID

import pytest
from execution_plane_client.protocol import MessageEnvelope
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.execution_plane import cluster_sync_commands
from syntara.execution_plane.client import ExecutionPlaneRejectedError, ExecutionPlaneUnavailableError
from syntara.execution_plane.integration_sync import reconcile_integration_clusters

BASE_URL = "/api/v1/integrations"


@pytest.mark.asyncio
async def test_create_update_delete_and_recreate_submit_ep_commands(
    auth_client: AsyncClient,
    http_bearer_token_credential_id: UUID,
    ep_cluster_commands: list[MessageEnvelope],
) -> None:
    payload = {
        "name": "test-cluster",
        "integration_type": "openshift",
        "configuration": {
            "integration_type": "openshift",
            "base_url": "https://api.example.com:6443",
            "namespace": "default",
        },
        "management_credential_id": str(http_bearer_token_credential_id),
        "scope": "global",
    }
    first = await auth_client.post(BASE_URL, json=payload)
    assert first.status_code == 201, first.text
    assert not {"execution_plane_status", "execution_plane_revision", "execution_plane_error"} & first.json().keys()
    first_id = first.json()["id"]

    updated = await auth_client.patch(f"{BASE_URL}/{first_id}", json={"enabled": False})
    assert updated.status_code == 200, updated.text
    assert updated.json()["enabled"] is False
    assert (await auth_client.delete(f"{BASE_URL}/{first_id}")).status_code == 204

    second = await auth_client.post(BASE_URL, json=payload)
    assert second.status_code == 201, second.text
    assert second.json()["id"] != first_id
    assert [message.command.command_type for message in ep_cluster_commands] == [
        "cluster.register",
        "cluster.update",
        "cluster.delete",
        "cluster.register",
    ]
    assert [message.command.payload["desired_revision"] for message in ep_cluster_commands] == [1, 2, 3, 1]
    assert ep_cluster_commands[-1].command.payload["resource_key"] == second.json()["id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("conflict", [False, True])
async def test_ep_failure_preserves_ao_update_and_later_reconciliation_applies_it(
    auth_client: AsyncClient,
    http_bearer_token_credential_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    ep_cluster_commands: list[MessageEnvelope],
    *,
    conflict: bool,
) -> None:
    created = await auth_client.post(
        BASE_URL,
        json={
            "name": "cluster-before-failure",
            "integration_type": "openshift",
            "configuration": {
                "integration_type": "openshift",
                "base_url": "https://api.example.com:6443",
                "namespace": "default",
            },
            "management_credential_id": str(http_bearer_token_credential_id),
        },
    )
    assert created.status_code == 201, created.text
    integration_id = created.json()["id"]

    def fail_client() -> Never:
        if conflict:
            raise ExecutionPlaneRejectedError(status_code=409, detail="Cluster conflict")
        raise ExecutionPlaneUnavailableError

    with monkeypatch.context() as unavailable:
        unavailable.setattr(cluster_sync_commands, "ExecutionPlaneHttpClient", fail_client)
        response = await auth_client.patch(f"{BASE_URL}/{integration_id}", json={"enabled": False})
    assert response.status_code == 200, response.text
    current = await auth_client.get(f"{BASE_URL}/{integration_id}")
    assert current.status_code == 200
    assert current.json()["enabled"] is False
    assert len(ep_cluster_commands) == 1
    result = await reconcile_integration_clusters(test_db_session_factory, UUID(integration_id))
    assert result == {"synced": 1, "failed": 0, "skipped": 0}
    assert ep_cluster_commands[-1].command.command_type == "cluster.update"
    assert ep_cluster_commands[-1].command.payload["enabled"] is False
