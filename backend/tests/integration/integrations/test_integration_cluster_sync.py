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
    # Create, update, assign and unassign each reconcile the EP cluster with an
    # idempotent upsert (register); only deletion sends a delete. There is no
    # configuration revision, namespace or project list on the cluster command.
    assert [message.command.command_type for message in ep_cluster_commands] == [
        "cluster.register",
        "cluster.register",
        "cluster.register",
        "cluster.register",
        "cluster.delete",
    ]
    payloads = [message.command.payload for message in ep_cluster_commands]
    # Every command is addressed by the shared resource_id (= integration id).
    assert all(payload["resource_id"] == str(integration.id) for payload in payloads)
    assert payloads[0]["endpoint"] == "https://openshift.example.com:6443"
    assert payloads[0]["credential_ref"] == str(http_bearer_token_credential_id)
    assert payloads[1]["enabled"] is False


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
    # Each reconciliation re-sends an idempotent register addressed by the shared id.
    assert [message.command.command_type for message in ep_cluster_commands] == [
        "cluster.register",
        "cluster.register",
    ]
    assert all(message.command.payload["resource_id"] == str(integration.id) for message in ep_cluster_commands)


@pytest.mark.asyncio
async def test_commit_failure_reconciles_committed_configuration(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    http_bearer_token_credential_id: UUID,
    ep_cluster_commands: list[MessageEnvelope],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from sqlalchemy.exc import OperationalError

    from syntara.audit.dispatcher import AuditEventDispatcher
    from syntara.integrations.audit import IntegrationUpdateEvent

    service = IntegrationService(test_db_session, test_user)
    integration = await service.create_integration(_openshift_create(http_bearer_token_credential_id))
    integration_id = integration.id
    audit = MagicMock()
    monkeypatch.setattr(AuditEventDispatcher, "dispatch", audit)
    with monkeypatch.context() as failing_commit:
        failing_commit.setattr(
            test_db_session, "commit", AsyncMock(side_effect=OperationalError("commit", {}, Exception()))
        )
        with pytest.raises(OperationalError):
            await service.update_integration(integration_id, IntegrationUpdate(name="Uncommitted cluster"))
    assert [message.command.payload["name"] for message in ep_cluster_commands] == [
        "Test OpenShift",
        "Uncommitted cluster",
        "Test OpenShift",
    ]
    async with test_db_session_factory() as reader:
        saved = await reader.get(Integration, integration_id)
        assert saved is not None
        assert saved.name == "Test OpenShift"
    events = [call.args[0] for call in audit.call_args_list if isinstance(call.args[0], IntegrationUpdateEvent)]
    assert len(events) == 1
    assert events[0].error_type == "OperationalError"


@pytest.mark.asyncio
async def test_reconciliation_waits_for_update_before_reading_desired_state(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    http_bearer_token_credential_id: UUID,
    ep_cluster_commands: list[MessageEnvelope],
) -> None:
    import asyncio

    from sqlmodel import select

    from syntara.execution_plane.cluster_sync_commands import apply_integration_cluster

    service = IntegrationService(test_db_session, test_user)
    integration = await service.create_integration(_openshift_create(http_bearer_token_credential_id))
    integration_id = integration.id
    async with test_db_session_factory() as writer:
        saved = (await writer.exec(select(Integration).where(Integration.id == integration_id).with_for_update())).one()
        saved.name = "Latest committed name"
        await writer.flush()
        task = asyncio.create_task(apply_integration_cluster(test_db_session_factory, integration_id))
        try:
            done, _ = await asyncio.wait({task}, timeout=0.1)
            assert not done
            await writer.commit()
            assert await asyncio.wait_for(task, timeout=5)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert ep_cluster_commands[-1].command.payload["name"] == "Latest committed name"


@pytest.mark.asyncio
async def test_reconciliation_holds_row_lock_until_ep_delivery_finishes(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    http_bearer_token_credential_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    from sqlalchemy.exc import DBAPIError
    from sqlmodel import select

    from syntara.execution_plane import cluster_sync_commands

    service = IntegrationService(test_db_session, test_user)
    integration = await service.create_integration(_openshift_create(http_bearer_token_credential_id))
    integration_id = integration.id
    # Release the service's response-read transaction before testing independent sessions.
    await test_db_session.rollback()
    submitting = asyncio.Event()
    release = asyncio.Event()

    async def delayed_submit(_integration: Integration) -> None:
        submitting.set()
        await release.wait()

    monkeypatch.setattr(cluster_sync_commands, "submit_integration_cluster", delayed_submit)
    task = asyncio.create_task(cluster_sync_commands.apply_integration_cluster(test_db_session_factory, integration_id))
    try:
        await asyncio.wait_for(submitting.wait(), timeout=5)
        async with test_db_session_factory() as writer:
            with pytest.raises(DBAPIError) as error:
                await writer.exec(
                    select(Integration).where(Integration.id == integration_id).with_for_update(nowait=True)
                )
        assert getattr(error.value.orig, "sqlstate", None) == "55P03"
        release.set()
        assert await asyncio.wait_for(task, timeout=5)
        async with test_db_session_factory() as writer:
            saved = (
                await writer.exec(
                    select(Integration).where(Integration.id == integration_id).with_for_update(nowait=True)
                )
            ).one()
            assert saved.name == "Test OpenShift"
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_rejected_scope_update_restores_project_assignments(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    credential_factory: CredentialFactory,
    http_bearer_token_credential_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import AsyncMock

    from sqlmodel import select

    from syntara.execution_plane.client import ExecutionPlaneRejectedError
    from syntara.integrations.exceptions import IntegrationClusterSyncError
    from syntara.integrations.models.integration import IntegrationProjectAssignment
    from syntara.integrations.services import integration_service

    service = IntegrationService(test_db_session, test_user)
    data = _openshift_create(http_bearer_token_credential_id)
    data.scope = IntegrationScope.PROJECT
    integration = await service.create_integration(data)
    integration_id = integration.id
    project = await credential_factory.create_project()
    project_id = project.id
    await service.assign_project(integration_id, project_id)
    monkeypatch.setattr(
        integration_service,
        "submit_integration_cluster",
        AsyncMock(side_effect=ExecutionPlaneRejectedError(status_code=409)),
    )
    with pytest.raises(IntegrationClusterSyncError):
        await service.update_integration(
            integration_id, IntegrationUpdate(scope=IntegrationScope.GLOBAL, enabled=False)
        )
    async with test_db_session_factory() as reader:
        saved = await reader.get(Integration, integration_id)
        assert saved is not None
        assert saved.scope == IntegrationScope.PROJECT
        assert saved.enabled
        assignment = (
            await reader.exec(
                select(IntegrationProjectAssignment).where(
                    IntegrationProjectAssignment.integration_id == integration_id,
                    IntegrationProjectAssignment.project_id == project_id,
                )
            )
        ).one()
        assert assignment.project_id == project_id
