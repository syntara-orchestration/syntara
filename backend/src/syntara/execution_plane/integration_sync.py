"""Deliver AO integration desired state to EP and reconcile its observed status."""

from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import or_
from sqlmodel import col, select

from syntara.core.database.session import AsyncSessionLocal
from syntara.core.services.secret_service import create_secret_service
from syntara.credentials.exceptions import CredentialDisabledError
from syntara.credentials.lib.injector_resolver import InjectorResolver
from syntara.execution_plane.client import ExecutionPlaneHttpClient, ExecutionPlaneUnavailableError
from syntara.execution_plane.integration_sync_model import ExecutionPlaneIntegrationSync
from syntara.integrations.lib.credential_resolver import fetch_credential_with_type
from syntara.integrations.models.integration import (
    ExecutionPlaneSyncStatus,
    Integration,
    IntegrationProjectAssignment,
    IntegrationScope,
    IntegrationType,
)
from syntara.integrations.models.integration_configuration import OpenShiftConfiguration

if TYPE_CHECKING:
    from uuid import UUID

logger = structlog.stdlib.get_logger(__name__)

POLL_SECONDS = 5
LEASE_SECONDS = 60
MAX_RETRY_SECONDS = 300


async def _claim_outbox() -> list[ExecutionPlaneIntegrationSync]:
    """Lease a bounded set of due outbox rows across AO worker replicas."""
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        result = await session.exec(
            select(ExecutionPlaneIntegrationSync)
            .where(col(ExecutionPlaneIntegrationSync.processed_at).is_(None))
            .where(col(ExecutionPlaneIntegrationSync.next_attempt_at) <= now)
            .where(
                or_(
                    col(ExecutionPlaneIntegrationSync.lease_expires_at).is_(None),
                    col(ExecutionPlaneIntegrationSync.lease_expires_at) < now,
                )
            )
            .order_by(col(ExecutionPlaneIntegrationSync.created_at))
            .limit(25)
            .with_for_update(skip_locked=True)
        )
        rows = list(result.all())
        for row in rows:
            row.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
            row.attempts += 1
        await session.commit()
        return rows


async def _desired_payload(row: ExecutionPlaneIntegrationSync) -> dict[str, Any] | None:
    """Resolve current AO configuration and credential without holding a transaction over HTTP."""
    async with AsyncSessionLocal() as session:
        integration = await session.get(Integration, row.integration_id)
        if row.operation == "upsert":
            if integration is None or integration.execution_plane_revision != row.source_revision:
                return None
            if integration.integration_type is not IntegrationType.OPENSHIFT:
                return None
            configuration = integration.configuration
            if not isinstance(configuration, OpenShiftConfiguration):
                msg = "OpenShift integration has an invalid configuration"
                raise ValueError(msg)
            credential_id = integration.management_credential_id
            if credential_id is None:
                msg = "OpenShift management credential is required for EP synchronization"
                raise ValueError(msg)
            credential, credential_type = await fetch_credential_with_type(session, credential_id)
            if not credential.enabled:
                raise CredentialDisabledError(credential.name)
            secret_service = create_secret_service(session)
            secret_data = await secret_service.retrieve_secret(credential.secret_id)  # type: ignore[arg-type]
            resolved = InjectorResolver.resolve(credential_type.injectors or {}, secret_data).extra_vars
            secret = str(resolved.get("bearer_token") or resolved.get("token") or resolved.get("api_key") or "")
            if not secret:
                msg = "OpenShift credential did not resolve to an API token"
                raise ValueError(msg)
            if integration.scope is IntegrationScope.GLOBAL:
                project_ids = None
            else:
                projects = await session.exec(
                    select(IntegrationProjectAssignment.project_id).where(
                        IntegrationProjectAssignment.integration_id == integration.id
                    )
                )
                project_ids = list(projects.all())
            labels = dict(integration.labels or {})
            labels.update({"integration_id": str(integration.id), "integration_name": integration.name})
            return {
                "revision": integration.execution_plane_revision,
                "name": integration.name,
                "endpoint": configuration.base_url,
                "namespace": configuration.namespace,
                "credential": secret,
                "ca_certificate": configuration.ca_certificate,
                "insecure_skip_tls_verify": configuration.insecure_skip_tls_verify,
                "project_ids": project_ids,
                "labels": labels,
                "enabled": integration.enabled,
            }

        return {
            "revision": row.source_revision,
            "name": row.name,
            "endpoint": row.endpoint,
            "namespace": row.namespace,
            "credential": "",
            "project_ids": [],
            "labels": {"integration_id": str(row.integration_id)},
            "enabled": False,
        }


async def _mark_outbox(
    row_id: UUID,
    *,
    delivered: bool,
    error: str | None = None,
    retry_after_seconds: int = MAX_RETRY_SECONDS,
) -> None:
    """Complete or reschedule one leased AO outbox row."""
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        row = await session.get(ExecutionPlaneIntegrationSync, row_id, with_for_update=True)
        if row is None or row.processed_at is not None:
            return
        row.lease_expires_at = None
        row.last_error = error
        if delivered:
            row.processed_at = now
        else:
            row.next_attempt_at = now + timedelta(seconds=retry_after_seconds)
            integration = await session.get(Integration, row.integration_id, with_for_update=True)
            if integration is not None and integration.execution_plane_revision == row.source_revision:
                integration.execution_plane_status = ExecutionPlaneSyncStatus.ERROR
                integration.execution_plane_error = error
        await session.commit()


async def _deliver(row: ExecutionPlaneIntegrationSync) -> None:
    """Send one current desired state; stale outbox revisions are safely discarded."""
    try:
        payload = await _desired_payload(row)
        if payload is None:
            await _mark_outbox(row.id, delivered=True)
            return
        async with ExecutionPlaneHttpClient() as client:
            await client.upsert_cluster_binding(source_integration_id=row.integration_id, **payload)
    except Exception as exc:  # noqa: BLE001 — all delivery failures must retain the durable retry record
        retry_after = min(MAX_RETRY_SECONDS, 2 ** min(row.attempts, 8))
        retry_after = int(retry_after * secrets.SystemRandom().uniform(0.8, 1.2))
        error = f"EP synchronization request failed ({type(exc).__name__})"
        await _mark_outbox(row.id, delivered=False, error=error, retry_after_seconds=retry_after)
        logger.warning(
            "AO-to-EP integration synchronization will retry",
            integration_id=str(row.integration_id),
            revision=row.source_revision,
            attempt=row.attempts,
            error_type=type(exc).__name__,
        )
    else:
        await _mark_outbox(row.id, delivered=True)
        logger.info(
            "AO integration desired state accepted by EP",
            integration_id=str(row.integration_id),
            revision=row.source_revision,
        )


async def _reconcile_observed_status() -> None:
    """Poll EP's safe status resource to update AO's user-visible readiness fields."""
    async with AsyncSessionLocal() as session:
        result = await session.exec(
            select(Integration)
            .where(Integration.integration_type == IntegrationType.OPENSHIFT)
            .where(
                col(Integration.execution_plane_status).in_(
                    [ExecutionPlaneSyncStatus.PENDING, ExecutionPlaneSyncStatus.ERROR]
                )
            )
            .order_by(col(Integration.updated_at))
            .limit(50)
        )
        ids = [(integration.id, integration.execution_plane_revision) for integration in result.all()]

    if not ids:
        return
    async with ExecutionPlaneHttpClient() as client:
        for integration_id, revision in ids:
            try:
                state = await client.get_cluster_binding(source_integration_id=integration_id)
            except ExecutionPlaneUnavailableError:
                logger.warning("EP status polling failed", integration_id=str(integration_id))
                continue
            observed_revision = int(state.get("observed_revision", 0))
            if observed_revision != revision:
                continue
            raw_status = state.get("status")
            status_map = {
                "ready": ExecutionPlaneSyncStatus.READY,
                "error": ExecutionPlaneSyncStatus.ERROR,
                "deleting": ExecutionPlaneSyncStatus.DELETING,
                "deleted": ExecutionPlaneSyncStatus.DELETING,
                "pending": ExecutionPlaneSyncStatus.PENDING,
                "reconciling": ExecutionPlaneSyncStatus.PENDING,
            }
            observed = status_map.get(str(raw_status))
            if observed is None:
                continue
            async with AsyncSessionLocal() as session:
                integration = await session.get(Integration, integration_id, with_for_update=True)
                if integration is None or integration.execution_plane_revision != revision:
                    continue
                integration.execution_plane_status = observed
                integration.execution_plane_error = state.get("status_message")
                await session.commit()


async def run_integration_sync_bridge() -> None:
    """Continuously deliver durable integration intents and refresh observed EP state."""
    while True:
        try:
            rows = await _claim_outbox()
            for row in rows:
                await _deliver(row)
            await _reconcile_observed_status()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("AO integration synchronization iteration failed")
        await asyncio.sleep(POLL_SECONDS)
