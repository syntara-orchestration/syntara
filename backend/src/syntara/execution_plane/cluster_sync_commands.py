"""Compatibility with EP's current source-key/revision cluster commands."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from execution_plane_client.commands.clusters import ClusterDelete, ClusterRegister, ClusterUpdate
from fastapi import HTTPException, status
from sqlmodel import select

from syntara.core.exceptions import SafeValueError
from syntara.execution_plane.client import (
    EP_AUDIENCE,
    EP_CLIENT_ID,
    ExecutionPlaneHttpClient,
    ExecutionPlaneRejectedError,
    ExecutionPlaneUnavailableError,
)
from syntara.integrations.models.integration import (
    Integration,
    IntegrationProjectAssignment,
    IntegrationScope,
    IntegrationType,
)
from syntara.integrations.models.integration_configuration import OpenShiftConfiguration

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession


async def _submit(
    client: ExecutionPlaneHttpClient,
    command: ClusterRegister | ClusterUpdate | ClusterDelete,
    cluster_id: UUID | None = None,
) -> None:
    receipt = await client.submit_command(
        command.to_message(source_id=EP_CLIENT_ID, destination_id=EP_AUDIENCE, client_id=EP_CLIENT_ID)
    )
    if (
        receipt.resource is None
        or receipt.resource.kind != "cluster"
        or receipt.resource.revision != command.desired_revision
        or (cluster_id is not None and receipt.resource.resource_id != cluster_id)
    ):
        message = "Invalid cluster command receipt"
        raise ExecutionPlaneRejectedError(message)


async def apply_integration_cluster(session_factory: async_sessionmaker[AsyncSession], integration_id: UUID) -> bool:
    """Commit the legacy sequence counter before HTTP, without holding an Integration lock over HTTP."""
    async with ExecutionPlaneHttpClient() as client:
        page = await client.list_clusters(limit=2, filters={"source_integration_id": str(integration_id)})
        resources = page["resources"]
        if len(resources) > 1 or page.get("next") or page.get("prev"):
            message = "Multiple EP clusters match the integration"
            raise ExecutionPlaneRejectedError(message)
        cluster_id = UUID(resources[0]["id"]) if resources else None
        async with session_factory() as session, session.begin():
            integration = (
                await session.exec(select(Integration).where(Integration.id == integration_id).with_for_update())
            ).one_or_none()
            if integration is None or integration.integration_type != IntegrationType.OPENSHIFT:
                return False
            configuration = integration.configuration
            if not isinstance(configuration, OpenShiftConfiguration) or integration.management_credential_id is None:
                message = "OpenShift cluster synchronization requires configuration and a management credential"
                raise SafeValueError(message)
            project_ids: list[UUID] | None = None
            if integration.scope == IntegrationScope.PROJECT:
                projects = await session.exec(
                    select(IntegrationProjectAssignment.project_id).where(
                        IntegrationProjectAssignment.integration_id == integration_id
                    )
                )
                project_ids = list(projects.all())
            integration.execution_plane_revision += 1
            fields = {
                "resource_key": integration_id,
                "desired_revision": integration.execution_plane_revision,
                "name": integration.name,
                "endpoint": configuration.base_url,
                "credential_ref": integration.management_credential_id,
                "ca_certificate": configuration.ca_certificate,
                "project_ids": project_ids,
                "labels": integration.labels or {},
                "enabled": integration.enabled,
            }
            command = (
                ClusterRegister.model_validate({**fields, "namespace": configuration.namespace})
                if cluster_id is None
                else ClusterUpdate.model_validate(fields)
            )
        await _submit(client, command, cluster_id)
    return True


async def delete_integration_cluster(session: AsyncSession, integration: Integration) -> None:
    """Keep explicit deletion and EP default protections until orphan ownership is defined."""
    if integration.integration_type != IntegrationType.OPENSHIFT:
        return
    integration.execution_plane_revision += 1
    await session.flush()
    command = ClusterDelete(resource_key=integration.id, desired_revision=integration.execution_plane_revision)
    try:
        async with ExecutionPlaneHttpClient() as client:
            await _submit(client, command)
    except ExecutionPlaneUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Execution Plane unavailable") from exc
    except ExecutionPlaneRejectedError as exc:
        if exc.status_code in {404, 409, 422}:
            raise HTTPException(exc.status_code, exc.detail or str(exc)) from exc
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Invalid Execution Plane response") from exc
