"""Temporal activity for resolving integration settings at execution time.

Fetches integration URL and SSL settings from the database so that
AAP and TFE activity executors use the same connection parameters as the UI.
"""

from typing import Any

import structlog
from sqlalchemy.exc import OperationalError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.core.database.session import AsyncSessionLocal
from syntara.integrations.lib.url_validation import validate_integration_configuration_no_ssrf
from syntara.integrations.models.integration import Integration, IntegrationType
from syntara.integrations.models.integration_configuration import AAPConfiguration, TFEConfiguration
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName

logger = structlog.stdlib.get_logger(__name__)

_session_factory = AsyncSessionLocal


@activity.defn(name=ActivityName.INTEGRATION_RESOLUTION)
async def resolve_workflow_integration(integration_id: str) -> dict[str, Any]:
    """Resolve integration connection settings for workflow activities.

    Fetches the integration record and returns its URL and SSL settings
    so that execution-time connections match the UI browsing path.

    Args:
        integration_id: UUID string of the integration to resolve.

    Returns:
        Dict with base_url, verify_ssl, and type-specific fields
        (organization for TFE).

    Raises:
        ApplicationError: Non-retryable error if integration is missing,
            wrong type, disabled, or has invalid configuration.

    """
    try:
        async with _session_factory() as session:
            return await _resolve_integration(session, integration_id)
    except ApplicationError:
        raise
    except OperationalError as e:
        msg = f"Transient database error during integration resolution: {type(e).__name__}"
        raise ApplicationError(msg, non_retryable=False) from e
    except Exception as e:
        msg = f"Database error during integration resolution: {type(e).__name__}"
        raise ApplicationError(msg, non_retryable=True) from e


async def _resolve_integration(session: AsyncSession, integration_id: str) -> dict[str, Any]:
    """Resolve a single integration's connection settings."""
    stmt = select(Integration).where(Integration.id == integration_id)
    result = await session.exec(stmt)
    integration = result.one_or_none()

    if not integration:
        msg = f"Integration '{integration_id}' not found"
        raise ApplicationError(msg, non_retryable=True)

    if integration.integration_type not in (
        IntegrationType.ANSIBLE_AUTOMATION_PLATFORM,
        IntegrationType.TERRAFORM_ENTERPRISE,
    ):
        msg = (
            f"Integration '{integration_id}' is type '{integration.integration_type}',"
            " expected 'ansible_automation_platform' or 'terraform_enterprise'"
        )
        raise ApplicationError(msg, non_retryable=True)

    if not integration.enabled:
        msg = f"Integration '{integration.name}' is disabled"
        raise ApplicationError(msg, non_retryable=True)

    config = integration.configuration

    if integration.integration_type == IntegrationType.ANSIBLE_AUTOMATION_PLATFORM:
        if not isinstance(config, AAPConfiguration):
            msg = f"Integration '{integration_id}' has invalid configuration type"
            raise ApplicationError(msg, non_retryable=True)
        try:
            validate_integration_configuration_no_ssrf(config)
        except ValueError as e:
            msg = f"Integration '{integration_id}' base_url is not permitted by SSRF policy"
            raise ApplicationError(msg, non_retryable=True) from e

        logger.info(
            "Integration resolved",
            integration_id=integration_id,
            integration_name=integration.name,
            integration_type=integration.integration_type.value,
        )
        return {
            "base_url": config.base_url.rstrip("/"),
            "verify_ssl": not config.insecure_skip_tls_verify,
            "ca_certificate": config.ca_certificate,
            "integration_type": IntegrationType.ANSIBLE_AUTOMATION_PLATFORM.value,
        }

    # Terraform Enterprise
    if not isinstance(config, TFEConfiguration):
        msg = f"Integration '{integration_id}' has invalid configuration type"
        raise ApplicationError(msg, non_retryable=True)
    try:
        validate_integration_configuration_no_ssrf(config)
    except ValueError as e:
        msg = f"Integration '{integration_id}' base_url is not permitted by SSRF policy"
        raise ApplicationError(msg, non_retryable=True) from e

    logger.info(
        "Integration resolved",
        integration_id=integration_id,
        integration_name=integration.name,
        integration_type=integration.integration_type.value,
    )
    return {
        "base_url": config.base_url.rstrip("/"),
        "organization": config.organization,
        "verify_ssl": not config.insecure_skip_tls_verify,
        "ca_certificate": config.ca_certificate,
        "integration_type": IntegrationType.TERRAFORM_ENTERPRISE.value,
    }
