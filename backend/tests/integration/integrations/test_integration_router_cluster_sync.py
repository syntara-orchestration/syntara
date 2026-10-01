"""OpenShift integration routes persist EP sync intent in AO's outbox."""

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.execution_plane.integration_sync_model import ExecutionPlaneIntegrationSync
from syntara.integrations.models.integration import IntegrationType

BASE_URL = "/api/v1/integrations"


def _payload(name: str, credential_id: UUID) -> dict[str, object]:
    return {
        "name": name,
        "integration_type": IntegrationType.OPENSHIFT.value,
        "configuration": {
            "integration_type": IntegrationType.OPENSHIFT.value,
            "base_url": "https://api.example.com:6443",
            "namespace": "default",
            "insecure_skip_tls_verify": False,
            "allow_http": False,
            "ca_certificate": None,
        },
        "management_credential_id": str(credential_id),
        "scope": "global",
    }


async def _sync_rows(session: AsyncSession, integration_id: UUID) -> list[ExecutionPlaneIntegrationSync]:
    result = await session.exec(
        select(ExecutionPlaneIntegrationSync)
        .where(ExecutionPlaneIntegrationSync.integration_id == integration_id)
        .order_by(ExecutionPlaneIntegrationSync.source_revision)
    )
    return list(result.all())


class TestOpenShiftIntegrationSyncOutbox:
    """HTTP CRUD records asynchronous desired-state changes for the EP adapter."""

    @pytest.mark.asyncio
    async def test_create_records_upsert_and_pending_status(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        http_bearer_token_credential_id: UUID,
    ) -> None:
        response = await auth_client.post(
            BASE_URL, json=_payload("test-cluster-create", http_bearer_token_credential_id)
        )
        assert response.status_code == 201
        body = response.json()
        rows = await _sync_rows(test_db_session, UUID(body["id"]))

        assert body["execution_plane_status"] == "pending"
        assert len(rows) == 1
        assert rows[0].operation == "upsert"
        assert rows[0].source_revision == 1
        assert rows[0].endpoint == "https://api.example.com:6443"
        assert rows[0].namespace == "default"

    @pytest.mark.asyncio
    async def test_delete_records_a_tombstone(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        http_bearer_token_credential_id: UUID,
    ) -> None:
        response = await auth_client.post(
            BASE_URL, json=_payload("test-cluster-delete", http_bearer_token_credential_id)
        )
        assert response.status_code == 201
        integration_id = UUID(response.json()["id"])

        delete_response = await auth_client.delete(f"{BASE_URL}/{integration_id}")
        assert delete_response.status_code == 204

        rows = await _sync_rows(test_db_session, integration_id)
        assert [row.operation for row in rows] == ["upsert", "delete"]
        assert rows[-1].source_revision == 2

    @pytest.mark.asyncio
    async def test_recreated_name_gets_a_new_independent_binding(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        http_bearer_token_credential_id: UUID,
    ) -> None:
        first = await auth_client.post(
            BASE_URL, json=_payload("test-cluster-recreate", http_bearer_token_credential_id)
        )
        assert first.status_code == 201
        first_id = UUID(first.json()["id"])
        assert (await auth_client.delete(f"{BASE_URL}/{first_id}")).status_code == 204

        second = await auth_client.post(
            BASE_URL, json=_payload("test-cluster-recreate", http_bearer_token_credential_id)
        )
        assert second.status_code == 201
        second_id = UUID(second.json()["id"])

        assert second_id != first_id
        assert [row.operation for row in await _sync_rows(test_db_session, first_id)] == ["upsert", "delete"]
        assert [row.operation for row in await _sync_rows(test_db_session, second_id)] == ["upsert"]
