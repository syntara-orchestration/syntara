"""OpenShift integration writes synchronously save the corresponding EP cluster."""

from typing import Never
from uuid import UUID

import pytest
from execution_plane_client.protocol import MessageEnvelope
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.execution_plane.integration_sync import reconcile_integration_clusters
from syntara.integrations.exceptions import IntegrationCredentialRequiredError
from syntara.integrations.models.integration import (
    Integration,
    IntegrationCreate,
    IntegrationScope,
    IntegrationType,
    IntegrationUpdate,
)
from syntara.integrations.services.integration_service import IntegrationService
from tests.integration.helpers.credential import CredentialFactory


def _openshift_create(credential_id: UUID | None = None) -> IntegrationCreate:
    return IntegrationCreate(
        name="Test OpenShift",
        integration_type=IntegrationType.OPENSHIFT,
        configuration={
            "integration_type": "openshift",
            "base_url": "https://openshift.example.com:6443",
            "namespace": "syntara-workers",
        },
        management_credential_id=credential_id,
    )


@pytest.mark.asyncio
async def test_openshift_crud_and_project_assignments_submit_cluster_commands(
    test_db_session: AsyncSession,
    test_user: User,
    credential_factory: CredentialFactory,
    http_bearer_token_credential_id: UUID,
    ep_cluster_commands: list[MessageEnvelope],
) -> None:
    service = IntegrationService(test_db_session, test_user)
    integration = await service.create_integration(_openshift_create(http_bearer_token_credential_id))

    updated = await service.update_integration(
        integration.id,
        IntegrationUpdate(
            name="Renamed OpenShift",
            enabled=False,
            scope=IntegrationScope.PROJECT,
            labels={"team": "platform"},
            management_credential_id=http_bearer_token_credential_id,
            configuration={
                "integration_type": "openshift",
                "base_url": "https://other.example.com:6443",
                "namespace": "other-workers",
            },
        ),
    )
    assert updated.name == "Renamed OpenShift"
    assert updated.enabled is False
    project = await credential_factory.create_project()
    assignment = await service.assign_project(integration.id, project.id)
    assert assignment.project_id == project.id
    await service.unassign_project(integration.id, project.id)
    await service.delete_integration(integration.id)

    assert await test_db_session.get(Integration, integration.id) is None
    assert [message.command.command_type for message in ep_cluster_commands] == [
        "cluster.register",
        "cluster.update",
        "cluster.update",
        "cluster.update",
        "cluster.delete",
    ]
    payloads = [message.command.payload for message in ep_cluster_commands]
    assert [payload["desired_revision"] for payload in payloads] == [1, 2, 3, 4, 5]
    assert all(payload["resource_key"] == str(integration.id) for payload in payloads)
    assert payloads[0]["namespace"] == "syntara-workers"
    assert payloads[0]["credential_ref"] == str(http_bearer_token_credential_id)
    assert payloads[1]["enabled"] is False
    assert payloads[2]["project_ids"] == [str(project.id)]
    assert payloads[3]["project_ids"] == []


@pytest.mark.asyncio
async def test_openshift_create_still_requires_a_management_credential(
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    service = IntegrationService(test_db_session, test_user)
    with pytest.raises(IntegrationCredentialRequiredError):
        await service.create_integration(_openshift_create())


@pytest.mark.asyncio
async def test_manual_reconciliation_recovers_missing_cluster_and_reuses_it(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    http_bearer_token_credential_id: UUID,
    ep_cluster_commands: list[MessageEnvelope],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from syntara.execution_plane import cluster_sync_commands
    from syntara.execution_plane.client import ExecutionPlaneUnavailableError

    def unavailable() -> Never:
        raise ExecutionPlaneUnavailableError

    service = IntegrationService(test_db_session, test_user)
    with monkeypatch.context() as outage:
        outage.setattr(cluster_sync_commands, "ExecutionPlaneHttpClient", unavailable)
        integration = await service.create_integration(_openshift_create(http_bearer_token_credential_id))
    assert ep_cluster_commands == []
    async with test_db_session_factory() as reader:
        assert await reader.get(Integration, integration.id) is not None

    for _ in range(2):
        result = await reconcile_integration_clusters(test_db_session_factory, integration.id)
        assert result == {"synced": 1, "failed": 0, "skipped": 0}
    assert [message.command.command_type for message in ep_cluster_commands] == ["cluster.register", "cluster.update"]
    assert all(message.command.payload["resource_key"] == str(integration.id) for message in ep_cluster_commands)
