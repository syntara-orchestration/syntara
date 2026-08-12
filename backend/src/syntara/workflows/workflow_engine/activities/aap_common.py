"""Shared utilities for AAP (Ansible Automation Platform) activities.

Common functions for both job template and workflow job template activities.
"""

from __future__ import annotations

import asyncio
import math
import re
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import httpx
import structlog
from temporalio import activity
from temporalio.exceptions import ApplicationError, CancelledError

from syntara.core.exceptions import SafeValueError
from syntara.workflows.workflow_engine.utils.credential_scrubber import ensure_resolved_credentials_dict

from .common import (
    DEFAULT_RETRYABLE_ERROR_CODES,
    HEARTBEAT_PARTIAL_OUTPUT_KEY,
    HEARTBEAT_STOP_MONITOR,
    ActivityExecutionError,
    is_retryable_http_status,
)

if TYPE_CHECKING:
    from httpx._client import UseClientDefault

    from syntara.core.config.base import Settings
    from syntara.workflows.workflow_engine.models.aap_types import AAPResourceType

logger = structlog.stdlib.get_logger(__name__)

# ============================================================================
# SECURITY: AAP Label Creation
# ============================================================================
# WARNING: This module creates labels in AAP Controller. Labels are permanent
# resources (no automatic cleanup) scoped to organizations.
#
# Current limits per workflow execution:
# - MAX_LABELS_PER_WORKFLOW = 100 labels
# - Each label is validated against LABEL_NAME_PATTERN (alphanumeric + ._-)
# - Label names are limited to MAX_LABEL_NAME_LENGTH = 512 characters
#
# DoS Risk: No rate limiting exists between workflow executions. A malicious
# user can execute 1000 workflows * 100 labels = 100,000 permanent labels in
# AAP, causing database bloat and performance degradation.
#
# Mitigation: Implement workflow execution rate limiting or label quota systems
# in future versions. Monitor AAP label count growth via AAP metrics.
# ============================================================================


# Security constants for label validation
MAX_LABEL_NAME_LENGTH = 512  # AAP's max label length

# SECURITY: Label creation limits and known issues
# - MAX_LABELS_PER_WORKFLOW = 100 limits labels per single workflow execution to prevent single-workflow DoS.
# - KNOWN LIMITATION: This does NOT prevent multi-workflow DoS (e.g., 1000 runs x 100 labels = 100k labels).
# - Labels are permanent AAP resources with no automatic cleanup, causing database bloat and performance degradation.
#
# #913: Implement comprehensive label quota system:
#   1. Cross-execution quota: Track total labels created per tenant/organization in application database
#   2. Rate limiting: Limit workflow execution frequency to bound label creation velocity
#   3. Cleanup automation: Periodic job to remove labels created by workflows no longer in use
#   4. Quota enforcement: Reject workflow execution when quota is exceeded, not just at label creation time
#
# Recommendation from security review (PR #913): Implement before production deployment to prevent
# resource exhaustion attacks on shared AAP Controller instances.
MAX_LABELS_PER_WORKFLOW = 100  # Prevent resource exhaustion per workflow
LABEL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9 ._-]+$")

# HTTP status codes
HTTP_CONFLICT = 409  # Resource conflict (concurrent creation)


def build_aap_job_url(base_url: str, job_id: int, job_type: str = "playbook") -> str:
    """Build the AAP UI URL for a job.

    Args:
        base_url: AAP controller base URL (e.g. https://aap.example.com)
        job_id: AAP job ID
        job_type: "playbook" for job templates, "workflow" for workflow job templates

    """
    return f"{base_url.rstrip('/')}/execution/jobs/{job_type}/{job_id}/output"


class AAPJobTerminalStatus(StrEnum):
    """AAP job terminal statuses for both regular jobs and workflow jobs."""

    SUCCESSFUL = "successful"
    FAILED = "failed"
    ERROR = "error"
    CANCELED = "canceled"


# Set of terminal statuses for efficient lookup (lowercase)
AAP_JOB_TERMINAL_STATUSES = {status.lower() for status in AAPJobTerminalStatus}


class AAPActivityExecutionError(ActivityExecutionError):
    """Base class for AAP activity execution errors.

    The ``retryable`` flag controls how the activity-level catch block
    converts this into a Temporal ``ApplicationError``.  HTTP status
    classification sets it via ``is_retryable_http_status``; all other
    paths default to ``False`` (non-retryable).
    """

    def __init__(
        self,
        message: str,
        job_id: int | None = None,
        status: str | None = None,
        output: str | None = None,
        *,
        retryable: bool = False,
    ) -> None:
        """Initialize with optional retryable flag for HTTP status classification."""
        super().__init__(message)
        self.job_id = job_id
        self.status = status
        self.output = output
        self.retryable = retryable


async def lookup_resource_by_name(
    client: httpx.AsyncClient,
    resource_name: str,
    organization_name: str,
    resource_type: AAPResourceType,
    auth_headers: dict[str, str],
    basic_auth: httpx.BasicAuth | None,
    base_url: str,
    error_class: type[AAPActivityExecutionError],
) -> int:
    """Lookup AAP resource ID by name and organization.

    Args:
        client: HTTP client
        resource_name: Name of the resource (job template, workflow template, or inventory)
        organization_name: Name of organization
        resource_type: Type of resource (JOB_TEMPLATES, WORKFLOW_JOB_TEMPLATES, or INVENTORIES)
        auth_headers: Authentication headers
        basic_auth: Basic authentication object
        base_url: Base URL for AAP controller
        error_class: Error class to raise on failure

    Returns:
        Resource ID

    Raises:
        error_class: If resource not found or multiple resources found

    """
    auth_param = basic_auth or httpx.USE_CLIENT_DEFAULT

    # Query AAP API for resources by name and organization
    lookup_url = f"{base_url}/api/controller/v2/{resource_type.value}/"
    params = {
        "name": resource_name,
        "organization__name": organization_name,
    }

    # Get display name from enum for error messages
    display_name = resource_type.display_name

    try:
        response = await client.get(lookup_url, params=params, headers=auth_headers, auth=auth_param)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        results: list[dict[str, Any]] = data.get("results", [])

        # Validate exactly one result
        if len(results) == 0:
            msg = f"{display_name.capitalize()} '{resource_name}' not found in organization '{organization_name}'"
            raise error_class(msg, status=None)

        if len(results) > 1:
            msg = (
                f"Multiple {resource_type.display_name_plural} named '{resource_name}' "
                f"found in organization '{organization_name}'"
            )
            raise error_class(msg, status=None)

        # Return the resource ID
        resource_id = int(results[0]["id"])
        logger.info(
            "Resolved %s to ID",
            display_name,
            resource_name=resource_name,
            organization_name=organization_name,
            resource_id=resource_id,
        )
        return resource_id

    except httpx.HTTPStatusError as e:
        msg = (
            f"Failed to lookup {display_name} '{resource_name}' in org '{organization_name}': "
            f"HTTP {e.response.status_code}"
        )
        raise error_class(msg, status=None, retryable=is_retryable_http_status(e.response.status_code)) from e
    except httpx.ConnectError as e:
        msg = f"Failed to connect to AAP for {display_name} lookup: {e}"
        raise error_class(msg) from e
    except httpx.HTTPError as e:
        msg = f"Failed to connect to AAP for {display_name} lookup: {e}"
        raise error_class(msg) from e


def validate_label_name(name: str) -> None:
    r"""Validate label name for security (prevent injection, DoS).

    SECURITY: This validation prevents:
    - Injection attacks: Only alphanumeric + ._- characters allowed
    - DoS via large names: Max 512 characters (MAX_LABEL_NAME_LENGTH)
    - Null byte injection: Explicit check for \x00

    NOTE: This does NOT prevent resource exhaustion from creating many labels.
    Workflows are limited to MAX_LABELS_PER_WORKFLOW (100) per execution, but
    no quota exists across multiple workflow executions.

    Args:
        name: Label name to validate

    Raises:
        SafeValueError: If label name is invalid

    """
    if not name:
        msg = "Label name cannot be empty"
        raise SafeValueError(msg)

    if len(name) > MAX_LABEL_NAME_LENGTH:
        msg = f"Label name exceeds maximum length ({len(name)} > {MAX_LABEL_NAME_LENGTH})"
        raise SafeValueError(msg)

    if "\x00" in name:
        msg = "Label name contains null bytes"
        raise SafeValueError(msg)

    if not LABEL_NAME_PATTERN.match(name):
        msg = f"Label name '{name}' contains invalid characters (allowed: alphanumeric, space, '.', '_', '-')"
        raise SafeValueError(msg)


async def lookup_organization_id(
    client: httpx.AsyncClient,
    organization_name: str,
    auth_headers: dict[str, str],
    auth_param: httpx.BasicAuth | httpx._client.UseClientDefault,
    base_url: str,
    error_class: type[AAPActivityExecutionError],
) -> int:
    """Look up organization ID by name.

    Args:
        client: HTTP client
        organization_name: Organization name to look up
        auth_headers: Authentication headers
        auth_param: Authentication parameter for requests
        base_url: Base URL for AAP controller
        error_class: Error class to raise on failure

    Returns:
        Organization ID

    Raises:
        error_class: If organization lookup fails or not found

    """
    org_lookup_url = f"{base_url}/api/controller/v2/organizations/"
    org_params = {"name": organization_name}
    try:
        org_response = await client.get(org_lookup_url, params=org_params, headers=auth_headers, auth=auth_param)
        org_response.raise_for_status()
        org_data: dict[str, Any] = org_response.json()
        org_results: list[dict[str, Any]] = org_data.get("results", [])
        if not org_results:
            msg = f"Organization '{organization_name}' not found"
            raise error_class(msg, status=None)
        organization_id = int(org_results[0]["id"])
        logger.info(
            "Resolved organization to ID for label operations",
            organization_name=organization_name,
            organization_id=organization_id,
        )
        return organization_id
    except httpx.HTTPStatusError as e:
        msg = f"Failed to lookup organization '{organization_name}': HTTP {e.response.status_code}"
        raise error_class(msg, status=None, retryable=is_retryable_http_status(e.response.status_code)) from e


async def resolve_single_label(
    client: httpx.AsyncClient,
    name: str,
    organization_id: int,
    organization_name: str | None,
    auth_headers: dict[str, str],
    auth_param: httpx.BasicAuth | httpx._client.UseClientDefault,
    base_url: str,
    error_class: type[AAPActivityExecutionError],
) -> int:
    """Resolve a single label name to ID, creating if needed.

    SECURITY NOTE: This function creates labels as a side effect. Labels are
    permanent AAP resources with no automatic cleanup. Each workflow execution
    can create up to MAX_LABELS_PER_WORKFLOW (100) labels.

    Concurrent Creation: Uses optimistic concurrency control - if a 409 Conflict
    occurs during label creation (another workflow created the same label), this
    function retries the query to retrieve the newly created label ID.

    Args:
        client: HTTP client
        name: Label name to resolve
        organization_id: Organization ID for label scoping
        organization_name: Organization name (for logging)
        auth_headers: Authentication headers
        auth_param: Authentication parameter for requests
        base_url: Base URL for AAP controller
        error_class: Error class to raise on failure

    Returns:
        Label ID (either existing or newly created)

    Raises:
        error_class: If label resolution or creation fails
        SafeValueError: If label name fails validation (see validate_label_name)

    """
    lookup_url = f"{base_url}/api/controller/v2/labels/"
    params = {"name": name, "page_size": "200"}

    try:
        response = await client.get(lookup_url, params=params, headers=auth_headers, auth=auth_param)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        all_results: list[dict[str, Any]] = data.get("results", [])

        # AAP labels API doesn't filter by organization in query - filter client-side
        results = [r for r in all_results if r.get("organization") == organization_id]

        logger.debug(
            "Label query result",
            label_name=name,
            organization_name=organization_name,
            organization_id=organization_id,
            total_found=len(all_results),
            org_filtered_count=len(results),
            results=results or None,
        )

        if results:
            # Label exists in this organization - use its ID
            label_id = int(results[0]["id"])
            logger.info("Resolved label to ID", label_name=name, label_id=label_id, organization_id=organization_id)
            return label_id

        # Label doesn't exist in this organization - create it
        create_url = f"{base_url}/api/controller/v2/labels/"
        create_body = {"name": name, "organization": organization_id}

        create_response = await client.post(create_url, json=create_body, headers=auth_headers, auth=auth_param)
        create_response.raise_for_status()
        created_data: dict[str, Any] = create_response.json()
        label_id = int(created_data["id"])
        logger.info("Created new label", label_name=name, label_id=label_id)
        return label_id

    except httpx.HTTPStatusError as e:
        # Handle concurrent creation (409 Conflict)
        if e.response.status_code == HTTP_CONFLICT:
            # Label was created by another workflow - re-query to get its ID
            logger.info("Label creation conflict, re-querying", label_name=name, organization_id=organization_id)
            try:
                retry_response = await client.get(lookup_url, params=params, headers=auth_headers, auth=auth_param)
                retry_response.raise_for_status()
                retry_data: dict[str, Any] = retry_response.json()
                retry_results: list[dict[str, Any]] = retry_data.get("results", [])
                # Filter by organization
                filtered_results = [r for r in retry_results if r.get("organization") == organization_id]

                if filtered_results:
                    label_id = int(filtered_results[0]["id"])
                    logger.info(
                        "Resolved label after conflict",
                        label_name=name,
                        label_id=label_id,
                        organization_id=organization_id,
                    )
                    return label_id

                # Label still not found after retry - this is unexpected
                msg = f"Label '{name}' not found after 409 Conflict retry"
                raise error_class(msg, status=None) from e
            except httpx.HTTPError as retry_error:
                msg = f"Failed to re-query label '{name}' after 409 Conflict: {retry_error}"
                raise error_class(msg) from retry_error

        response_text = e.response.text if hasattr(e.response, "text") else ""
        msg = f"Failed to resolve/create label '{name}': HTTP {e.response.status_code} - {response_text}"
        raise error_class(msg, status=None, retryable=is_retryable_http_status(e.response.status_code)) from e
    except httpx.HTTPError as e:
        msg = f"Failed to connect to AAP for label resolution: {e}"
        raise error_class(msg) from e


async def resolve_label_ids(
    client: httpx.AsyncClient,
    label_names: list[str],
    organization_name: str | None,
    organization_id: int | None,
    auth_headers: dict[str, str],
    basic_auth: httpx.BasicAuth | None,
    base_url: str,
    error_class: type[AAPActivityExecutionError],
) -> list[int]:
    """Resolve label names to AAP label IDs, creating new labels if needed.

    Queries AAP for each label by name within the organization.
    Creates new labels if they don't exist (per AAP's on-launch behavior).

    Security: Validates label names and enforces limits to prevent injection and DoS.

    Args:
        client: HTTP client
        label_names: List of label names to resolve
        organization_name: Organization name (labels are org-scoped, used for lookup if ID not provided)
        organization_id: Organization ID (takes precedence over name, skips lookup)
        auth_headers: Authentication headers
        basic_auth: Basic authentication object
        base_url: Base URL for AAP controller
        error_class: Error class to raise on failure

    Returns:
        List of label IDs corresponding to input names

    Raises:
        error_class: If label resolution or creation fails
        SafeValueError: If label validation fails

    """
    # Security: Prevent resource exhaustion
    if len(label_names) > MAX_LABELS_PER_WORKFLOW:
        msg = f"Cannot process more than {MAX_LABELS_PER_WORKFLOW} labels per workflow (got {len(label_names)})"
        raise SafeValueError(msg)

    # Security: Validate all label names upfront
    for name in label_names:
        validate_label_name(name)

    auth_param = basic_auth or httpx.USE_CLIENT_DEFAULT

    # Use provided organization_id or look it up from name
    resolved_org_id: int
    if organization_id is not None:
        resolved_org_id = organization_id
        logger.info("Using organization ID directly for label resolution", organization_id=organization_id)
    elif organization_name is not None:
        resolved_org_id = await lookup_organization_id(
            client, organization_name, auth_headers, auth_param, base_url, error_class
        )
        logger.info(
            "Resolved organization name to ID for label resolution",
            organization_name=organization_name,
            organization_id=resolved_org_id,
        )
    else:
        msg = "Either organization_id or organization_name must be provided for label resolution"
        raise SafeValueError(msg)

    # Resolve each label name to its ID
    label_ids: list[int] = []
    for name in label_names:
        label_id = await resolve_single_label(
            client, name, resolved_org_id, organization_name, auth_headers, auth_param, base_url, error_class
        )
        label_ids.append(label_id)

    return label_ids


def get_aap_auth_headers(settings: Settings) -> dict[str, str]:
    """Get AAP authentication headers (token preferred).

    Args:
        settings: Application settings

    Returns:
        Dictionary of auth headers for token auth, or empty dict for basic auth

    Raises:
        AAPActivityExecutionError: If no authentication configured

    """
    # NOTE: Change to get settings from AAP Tool integration once it is implemented.
    if settings.aap_token:
        # Token authentication (preferred)
        return {"Authorization": f"Bearer {settings.aap_token.get_secret_value()}"}
    if settings.aap_username and settings.aap_password:
        # Basic authentication will be handled via auth parameter
        return {}
    msg = "AAP authentication not configured. Set APP_AAP_TOKEN or APP_AAP_USERNAME/PASSWORD"
    raise AAPActivityExecutionError(msg)


def get_aap_basic_auth(settings: Settings) -> httpx.BasicAuth | None:
    """Get AAP basic authentication object.

    Args:
        settings: Application settings

    Returns:
        BasicAuth object if using basic auth, None otherwise

    """
    if settings.aap_username and settings.aap_password and not settings.aap_token:
        return httpx.BasicAuth(settings.aap_username, settings.aap_password.get_secret_value())
    return None


@dataclass
class AAPCredentialAuth:
    """Resolved AAP authentication from Nexus credentials."""

    headers: dict[str, str]
    basic_auth: httpx.BasicAuth | None


def get_aap_auth_from_credentials(
    resolved_creds: dict[str, Any],
) -> AAPCredentialAuth:
    """Extract AAP auth headers from resolved Nexus credentials.

    Args:
        resolved_creds: Resolved credential data with extra_vars from InjectorResolver.

    Returns:
        AAPCredentialAuth with auth headers and basic auth.

    """
    extra_vars = resolved_creds.get("extra_vars", {})

    token = extra_vars.get("aap_oauth_token", "")
    if token:
        return AAPCredentialAuth({"Authorization": f"Bearer {token}"}, None)

    username = extra_vars.get("aap_username", "")
    password = extra_vars.get("aap_password", "")
    if username:
        return AAPCredentialAuth({}, httpx.BasicAuth(username, password))

    logger.warning(
        "AAP credential resolved but contains no auth fields (oauth_token or username). "
        "Verify the correct credential type is linked to this activity."
    )
    return AAPCredentialAuth({}, None)


@dataclass
class AAPResolvedAuth:
    """Resolved AAP authentication ready for use in HTTP requests."""

    base_url: str
    auth_headers: dict[str, str]
    basic_auth: httpx.BasicAuth | None
    verify_ssl: bool
    ca_certificate: str | None = None


def resolve_aap_auth(input_config: dict[str, Any], settings: Settings) -> AAPResolvedAuth:
    """Resolve AAP authentication from integration and credentials.

    URL and SSL come exclusively from the resolved integration.
    Auth (headers/basic_auth) comes from the credential or environment settings.
    """
    resolved_creds = input_config.get("_resolved_credentials")
    resolved_integration = input_config.get("_resolved_integration")

    if not resolved_integration:
        msg = "AAP integration not configured. Attach an AAP integration to this node."
        raise ApplicationError(msg, type="ConfigError", non_retryable=True)

    base_url = resolved_integration["base_url"]
    verify_ssl = resolved_integration["verify_ssl"]
    ca_certificate = resolved_integration.get("ca_certificate")

    try:
        if resolved_creds:
            resolved_creds = ensure_resolved_credentials_dict(resolved_creds)
            cred_auth = get_aap_auth_from_credentials(resolved_creds)
            auth_headers = cred_auth.headers
            basic_auth = cred_auth.basic_auth
        else:
            auth_headers = get_aap_auth_headers(settings)
            basic_auth = get_aap_basic_auth(settings)
    except (AAPActivityExecutionError, TypeError, KeyError, ValueError) as e:
        logger.warning("AAP auth resolution failed", error=str(e), exc_info=True)
        msg = "Authentication failed — verify AAP credentials"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True) from None
    return AAPResolvedAuth(base_url, auth_headers, basic_auth, verify_ssl, ca_certificate)


def check_timeout(elapsed: float, timeout_seconds: int, job_id: int, *, configured_timeout: int | None = None) -> None:
    """Check if job execution has exceeded timeout.

    Args:
        elapsed: Elapsed time in seconds
        timeout_seconds: Timeout threshold in seconds
        job_id: AAP job ID
        configured_timeout: Original user-configured timeout for error messages.
            Falls back to timeout_seconds if not provided.

    Raises:
        AAPActivityExecutionError: If timeout exceeded

    """
    if elapsed >= timeout_seconds:
        display_timeout = configured_timeout if configured_timeout is not None else timeout_seconds
        msg = f"Job {job_id} timed out after {display_timeout} seconds"
        raise AAPActivityExecutionError(msg, job_id=job_id)


async def handle_cancellation(
    client: httpx.AsyncClient,
    job_id: int,
    auth_headers: dict[str, str],
    auth_param: httpx.BasicAuth | UseClientDefault,
    base_url: str,
    job_type: str,
) -> None:
    """Handle activity cancellation by cancelling AAP job.

    Args:
        client: HTTP client
        job_id: AAP job ID
        auth_headers: Authentication headers
        auth_param: Authentication parameter for request
        base_url: Base URL for AAP controller
        job_type: Type of job ("jobs" or "workflow_jobs")

    Raises:
        CancelledError: Always raised after attempting to cancel job

    """
    if activity.is_cancelled():
        logger.warning("Activity cancelled, cancelling AAP %s", job_type, job_id=job_id)
        cancel_url = f"{base_url}/api/controller/v2/{job_type}/{job_id}/cancel/"
        try:
            await client.post(cancel_url, headers=auth_headers, auth=auth_param)
        except httpx.HTTPError:
            logger.exception("Failed to cancel AAP %s", job_type, job_id=job_id)
        msg = f"Activity cancelled, AAP {job_type} cancelled"
        raise CancelledError(msg)


class _TransientPollError(Exception):
    """Raised when a poll request fails with a transient error.

    Not propagated outside poll_until_complete — used to signal the poll loop
    to log, sleep, and retry on the next cycle.
    """


_HTTP_NOT_FOUND = 404
_HTTP_INTERNAL_SERVER_ERROR = 500

# HTTP 500 is treated as transient during polling but NOT during launch.
# Polling is a read-only GET to check job status — safe to retry.
# Launch-phase 500s use DEFAULT_RETRYABLE_ERROR_CODES (which excludes 500)
# because a 500 during POST .../launch/ may indicate a real server-side
# rejection that won't self-resolve.
_TRANSIENT_POLL_STATUS_CODES = DEFAULT_RETRYABLE_ERROR_CODES | {_HTTP_INTERNAL_SERVER_ERROR}


def _is_transient_poll_error(exc: httpx.HTTPError) -> bool:
    """Return True if a poll HTTP error is transient and should be retried.

    Treats HTTP 500 as transient (in addition to 429, 502, 503, 504) because
    the poll request is an idempotent GET. A transient 500 from AAP Controller
    (load spike, pod restart, DB contention) should not immediately fail a
    node whose job may have completed successfully.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == _HTTP_NOT_FOUND:
            return False
        return status in _TRANSIENT_POLL_STATUS_CODES
    # Connection / timeout errors are transient
    return isinstance(exc, httpx.ConnectError | httpx.TimeoutException)


async def fetch_job_status(
    client: httpx.AsyncClient,
    status_url: str,
    auth_headers: dict[str, str],
    auth_param: httpx.BasicAuth | UseClientDefault,
    job_id: int,
    error_class: type[AAPActivityExecutionError],
) -> dict[str, Any]:
    """Fetch current job status from AAP.

    Transient HTTP errors (429, 500, 502, 503, 504, connection/timeout) raise
    _TransientPollError so the poll loop can retry on the next cycle.
    Non-transient errors (404, 401, 403, etc.) raise error_class immediately.

    Args:
        client: HTTP client
        status_url: URL to fetch job status
        auth_headers: Authentication headers
        auth_param: Authentication parameter for request
        job_id: AAP job ID
        error_class: Error class to raise on non-transient failure

    Returns:
        Job data dictionary

    Raises:
        _TransientPollError: If error is transient (retry on next poll cycle)
        error_class: If status fetch fails with a non-transient error

    """
    try:
        status_response = await client.get(status_url, headers=auth_headers, auth=auth_param)
        status_response.raise_for_status()
        job_data: dict[str, Any] = status_response.json()
        return job_data
    except httpx.HTTPError as e:
        if _is_transient_poll_error(e):
            msg = f"Transient error polling job {job_id} status: {e}"
            raise _TransientPollError(msg) from e
        msg = f"Failed to poll job {job_id} status: {e}"
        raise error_class(msg, job_id=job_id) from e


MAX_CONSECUTIVE_POLL_ERRORS = 5


async def poll_until_complete(
    client: httpx.AsyncClient,
    settings: Settings,
    job_id: int,
    auth_headers: dict[str, str],
    basic_auth: httpx.BasicAuth | None,
    base_url: str,
    timeout_seconds: int,
    start_time: float,
    job_type: str,
    terminal_statuses: set[str],
    error_class: type[AAPActivityExecutionError],
    partial_output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Poll job status until completion.

    Transient poll errors (429, 500, 502, 503, 504, connection, timeout) are
    absorbed and retried on the next poll cycle. If transient errors occur
    MAX_CONSECUTIVE_POLL_ERRORS times in a row without a single successful
    poll, the activity fails early with a "launched but lost contact" message
    rather than holding the Temporal worker slot until the full timeout.

    If the timeout expires while poll errors are occurring, the error
    message distinguishes "job timed out" from "launched but lost contact".

    Args:
        client: HTTP client
        settings: Application settings
        job_id: AAP job ID
        auth_headers: Authentication headers
        basic_auth: Basic authentication object
        base_url: Base URL for AAP controller
        timeout_seconds: Timeout for job execution in seconds
        start_time: Start time of job execution (from time.time())
        job_type: Type of job ("jobs" or "workflow_jobs")
        terminal_statuses: Set of terminal status strings (lowercase)
        error_class: Error class to raise on timeout/failure
        partial_output: Optional early output data to include in heartbeats

    Returns:
        Final job data

    Raises:
        error_class: If polling fails or timeout is exceeded
        CancelledError: If activity is cancelled

    """
    poll_interval = settings.aap_poll_interval_seconds
    status_url = f"{base_url}/api/controller/v2/{job_type}/{job_id}/"
    auth_param = basic_auth or httpx.USE_CLIENT_DEFAULT

    # Margin accounts for one final sleep after the last passing check.
    margin = math.ceil(poll_interval)
    effective_timeout = max(timeout_seconds - margin, 1)

    last_poll_error: str | None = None
    consecutive_poll_errors = 0

    while True:
        elapsed = time.time() - start_time
        try:
            check_timeout(elapsed, effective_timeout, job_id, configured_timeout=timeout_seconds)
        except AAPActivityExecutionError as timeout_err:
            if last_poll_error is not None:
                msg = (
                    f"AAP job {job_id} launched successfully but unable to determine completion "
                    f"status — polling failed repeatedly until timeout ({timeout_seconds}s). "
                    f"Last error: {last_poll_error}"
                )
                raise error_class(msg, job_id=job_id) from timeout_err
            raise

        # Check for cancellation (Temporal best practice)
        await handle_cancellation(client, job_id, auth_headers, auth_param, base_url, job_type)

        # Poll job status — transient errors are retried on next cycle
        try:
            job_data = await fetch_job_status(client, status_url, auth_headers, auth_param, job_id, error_class)
        except _TransientPollError as e:
            consecutive_poll_errors += 1
            last_poll_error = str(e)
            logger.warning(
                "Transient error polling %s status, will retry next cycle",
                job_type,
                job_id=job_id,
                error=str(e),
                consecutive_errors=consecutive_poll_errors,
                max_consecutive_errors=MAX_CONSECUTIVE_POLL_ERRORS,
            )
            if consecutive_poll_errors >= MAX_CONSECUTIVE_POLL_ERRORS:
                msg = (
                    f"AAP job {job_id} launched successfully but unable to determine completion "
                    f"status — polling failed {consecutive_poll_errors} consecutive times. "
                    f"Check the job directly in AAP Controller. "
                    f"Last error: {last_poll_error}"
                )
                raise error_class(msg, job_id=job_id) from e
            activity.heartbeat({HEARTBEAT_STOP_MONITOR: True, HEARTBEAT_PARTIAL_OUTPUT_KEY: partial_output})
            await asyncio.sleep(poll_interval)
            continue

        consecutive_poll_errors = 0
        last_poll_error = None
        status = job_data["status"]

        logger.info(
            "%s status", job_type.capitalize(), job_id=job_id, status=status, response_keys=list(job_data.keys())
        )

        # Check if job reached terminal state
        if isinstance(status, str) and status.lower() in terminal_statuses:
            logger.info("%s reached terminal status", job_type.capitalize(), job_id=job_id, status=status)
            return job_data

        # Send heartbeat to keep activity alive (Temporal best practice)
        activity.heartbeat({HEARTBEAT_STOP_MONITOR: True, HEARTBEAT_PARTIAL_OUTPUT_KEY: partial_output})

        # Sleep before next poll (global setting)
        await asyncio.sleep(poll_interval)
