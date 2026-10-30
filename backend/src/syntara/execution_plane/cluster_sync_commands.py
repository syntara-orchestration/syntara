"""Synchronize an Integration's EP Cluster addressed by their shared physical id.

The EP Cluster's primary key is the Integration's UUID (same id on both servers),
so there is no correlation key, no configuration revision, and no discovery by
filter: register is an idempotent upsert on that id.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from execution_plane_client.commands.clusters import ClusterDelete, ClusterRegister
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
from syntara.integrations.models.integration import Integration, IntegrationType
from syntara.integrations.models.integration_configuration import OpenShiftConfiguration

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession


async def _submit(
    client: ExecutionPlaneHttpClient,
    command: ClusterRegister | ClusterDelete,
    cluster_id: UUID,
) -> None:
    receipt = await client.submit_command(
        command.to_message(source_id=EP_CLIENT_ID, destination_id=EP_AUDIENCE, client_id=EP_CLIENT_ID)
    )
    if receipt.resource is None or receipt.resource.kind != "cluster" or receipt.resource.resource_id != cluster_id:
        message = "Invalid cluster command receipt"
        raise ExecutionPlaneRejectedError(message)


async def apply_integration_cluster(session_factory: async_sessionmaker[AsyncSession], integration_id: UUID) -> bool:
    """Upsert the EP Cluster whose physical id is this Integration's id."""
    async with session_factory() as session:
        integration = (await session.exec(select(Integration).where(Integration.id == integration_id))).one_or_none()
        if integration is None or integration.integration_type != IntegrationType.OPENSHIFT:
            return False
        configuration = integration.configuration
        if not isinstance(configuration, OpenShiftConfiguration) or integration.management_credential_id is None:
            message = "OpenShift cluster synchronization requires configuration and a management credential"
            raise SafeValueError(message)
        command = ClusterRegister.model_validate(
            {
                "resource_id": integration.id,
                "name": integration.name,
                "endpoint": configuration.base_url,
                "credential_ref": integration.management_credential_id,
                "ca_certificate": configuration.ca_certificate,
                "labels": integration.labels or {},
                "enabled": integration.enabled,
            }
        )
    async with ExecutionPlaneHttpClient() as client:
        await _submit(client, command, integration_id)
    return True


async def delete_integration_cluster(integration: Integration) -> None:
    """Request EP cluster deletion by the Integration's shared id."""
    if integration.integration_type != IntegrationType.OPENSHIFT:
        return
    command = ClusterDelete(resource_id=integration.id)
    try:
        async with ExecutionPlaneHttpClient() as client:
            await _submit(client, command, integration.id)
    except ExecutionPlaneUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Execution Plane unavailable") from exc
    except ExecutionPlaneRejectedError as exc:
        if exc.status_code in {404, 409, 422}:
            raise HTTPException(exc.status_code, exc.detail or str(exc)) from exc
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Invalid Execution Plane response") from exc
