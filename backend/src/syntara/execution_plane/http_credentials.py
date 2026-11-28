"""Authorize HTTP workload destinations without resolving secret values."""

from urllib.parse import urlsplit
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.execution_plane.commands.errors import CommandResourceStateError
from syntara.integrations.exceptions import IntegrationCredentialNotFoundError
from syntara.integrations.lib.credential_resolver import fetch_credential_with_type
from syntara.integrations.models.integration import (
    Integration,
    IntegrationProjectAssignment,
    IntegrationScope,
    IntegrationType,
)
from syntara.integrations.models.integration_configuration import HTTPConfiguration
from syntara.workflow_core.models import APIExecutorParameters

HTTP_BEARER_RECIPE = "syntara.http.bearer"


def https_origin(url: str) -> tuple[str, int]:
    """Normalize an HTTPS destination for comparison with an authorized origin."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        message = "Credentialed HTTP requires an HTTPS destination without URL credentials"
        raise ValueError(message)
    port = parsed.port if parsed.port is not None else 443
    if not port:
        message = "Invalid HTTPS port"
        raise ValueError(message)
    return parsed.hostname.lower(), port


async def authorize_http_binding(session: AsyncSession, parameters: APIExecutorParameters, project_id: UUID) -> str:
    """Validate the stored integration, project, bearer binding, and destination."""
    if parameters.integration_id is None or parameters.credential_id or len(parameters.credential_bindings) != 1:
        raise CommandResourceStateError
    binding = parameters.credential_bindings[0]
    integration = await session.get(Integration, parameters.integration_id)
    if (
        integration is None
        or not integration.enabled
        or integration.integration_type != IntegrationType.HTTP
        or not isinstance(integration.configuration, HTTPConfiguration)
        or binding.credential_recipe_id != HTTP_BEARER_RECIPE
        or integration.management_credential_id != binding.credential_ref
    ):
        raise CommandResourceStateError
    if integration.scope == IntegrationScope.PROJECT:
        assignment = (
            await session.exec(
                select(IntegrationProjectAssignment.id).where(
                    IntegrationProjectAssignment.integration_id == integration.id,
                    IntegrationProjectAssignment.project_id == project_id,
                )
            )
        ).first()
        if assignment is None:
            raise CommandResourceStateError
    try:
        credential, credential_type = await fetch_credential_with_type(session, binding.credential_ref)
    except IntegrationCredentialNotFoundError as error:
        raise CommandResourceStateError from error
    if not credential.enabled or credential.project_id != project_id or credential_type.name != "HTTP Bearer Token":
        raise CommandResourceStateError
    endpoint = integration.configuration.base_url
    try:
        if https_origin(parameters.url or "") != https_origin(endpoint):
            raise CommandResourceStateError
    except ValueError as error:
        raise CommandResourceStateError from error
    return endpoint
