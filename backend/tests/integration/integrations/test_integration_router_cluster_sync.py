"""Integration updates require EP acceptance before saving desired state."""

from typing import Never
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from execution_plane_client.protocol import MessageEnvelope
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.core.models import User
from syntara.execution_plane import cluster_sync_commands
from syntara.execution_plane.client import ExecutionPlaneRejectedError, ExecutionPlaneUnavailableError
from syntara.execution_plane.integration_sync import reconcile_integration_clusters
from syntara.integrations.audit import IntegrationUpdateEvent

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
    second_id = second.json()["id"]
    assert second_id != first_id
    # Every write reconciles the EP cluster with an idempotent upsert (register);
    # only deletion sends a delete. There is no configuration revision.
    assert [message.command.command_type for message in ep_cluster_commands] == [
        "cluster.register",
        "cluster.register",
        "cluster.delete",
        "cluster.register",
    ]
    # Commands are addressed by the shared resource_id (= integration id), so the
    # first three target the original integration and the last targets the recreated one.
    assert [message.command.payload["resource_id"] for message in ep_cluster_commands] == [
        first_id,
        first_id,
        first_id,
        second_id,
    ]
    assert ep_cluster_commands[-1].command.payload["resource_id"] == second_id


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["conflict", "default", "unavailable", "timeout", "invalid", "unauthorized"])
async def test_ep_failure_rolls_back_entire_update_and_audits_failure(
    auth_client: AsyncClient,
    test_user: User,
    test_db_session: AsyncSession,
    http_bearer_token_credential_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    ep_cluster_commands: list[MessageEnvelope],
    *,
    failure: str,
) -> None:
    created = await auth_client.post(
        BASE_URL,
        json={
            "name": "cluster-before-failure",
            "integration_type": "openshift",
            "configuration": {
                "integration_type": "openshift",
                "base_url": "https://api.example.com:6443",
            },
            "management_credential_id": str(http_bearer_token_credential_id),
        },
    )
    assert created.status_code == 201, created.text
    integration_id = created.json()["id"]

    def fail_client() -> Never:
        if failure == "unavailable":
            raise ExecutionPlaneUnavailableError
        if failure == "timeout":
            raise TimeoutError
        raise ExecutionPlaneRejectedError(
            status_code={"conflict": 409, "default": 409, "unauthorized": 403}.get(failure),
            code="DEFAULT_CLUSTER_PROTECTED" if failure == "default" else None,
        )

    audit = MagicMock()
    monkeypatch.setattr(AuditEventDispatcher, "dispatch", audit)
    with monkeypatch.context() as unavailable:
        unavailable.setattr(cluster_sync_commands, "ExecutionPlaneHttpClient", fail_client)
        response = await auth_client.patch(
            f"{BASE_URL}/{integration_id}", json={"enabled": False, "name": "rejected-name", "labels": {"new": "label"}}
        )
    expected_status = (
        503 if failure in {"unavailable", "timeout"} else 409 if failure in {"conflict", "default"} else 502
    )
    assert response.status_code == expected_status, response.text
    if failure == "default":
        assert "cannot be disabled" in response.text
    events = [call.args[0] for call in audit.call_args_list if isinstance(call.args[0], IntegrationUpdateEvent)]
    assert len(events) == 1
    assert events[0].error_type == (
        "ExecutionPlaneUnavailableError" if failure in {"unavailable", "timeout"} else "ExecutionPlaneRejectedError"
    )
    # The test client reuses this ORM user across requests; rollback expires it.
    await test_db_session.refresh(test_user)
    current = await auth_client.get(f"{BASE_URL}/{integration_id}")
    assert current.status_code == 200
    assert current.json()["enabled"] is True
    assert current.json()["name"] == "cluster-before-failure"
    assert not current.json()["labels"]
    assert len(ep_cluster_commands) == 1
    result = await reconcile_integration_clusters(test_db_session_factory, UUID(integration_id))
    assert result == {"synced": 1, "failed": 0, "skipped": 0}
    assert ep_cluster_commands[-1].command.command_type == "cluster.register"
    assert ep_cluster_commands[-1].command.payload["enabled"] is True
