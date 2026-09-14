"""AAP Proxy Service — BFF proxy for AAP Controller REST API v2.

Handles auth resolution, request forwarding, and response shaping for
the UI's cascading resource dropdowns.

Connection resolution:
- ``integration_id`` selects the AAP Gateway (URL/TLS). If omitted, the unique
  visible enabled AAP integration is used. If more than one is visible, the
  caller must pass ``integration_id``.
- ``credential_id`` selects an Orchestrator AAP credential (owner check). If omitted,
  the selected integration's management credential is used.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

import httpx
import structlog
from pydantic import BaseModel
from sqlmodel import col, select

from syntara.aap.auth import AAPConnection
from syntara.aap.credential_resolver import (
    resolve_aap_connection_from_credential,
    resolve_aap_connection_from_management_credential,
)
from syntara.aap.exceptions import AAPAuthenticationError, AAPConnectionError, AAPNotConfiguredError, AAPUpstreamError
from syntara.aap.models.responses import (
    AAPCredential,
    AAPExecutionEnvironment,
    AAPInstanceGroup,
    AAPInventory,
    AAPJobTemplate,
    AAPJobTemplateDetail,
    AAPLabel,
    AAPListResponse,
    AAPOrganization,
    AAPWorkflowJobTemplate,
    AAPWorkflowJobTemplateDetail,
)
from syntara.core.lib.tls_utils import build_integration_httpx_verify
from syntara.integrations.lib.url_validation import validate_integration_configuration_no_ssrf
from syntara.integrations.models.integration import Integration, IntegrationType
from syntara.integrations.models.integration_configuration import AAPConfiguration
from syntara.integrations.services.integration_service import IntegrationService

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.aap.models.queries import AAPBaseQuery, AAPResourceQuery
    from syntara.authz.engine import AllowedProjectsResult
    from syntara.core.config.base import Settings

logger = structlog.stdlib.get_logger(__name__)

# AAP Controller API v2 base path
_AAP_API_PREFIX = "/api/controller/v2"

# HTTP status code thresholds
_HTTP_STATUS_CLIENT_ERROR = 400

# Log messages
_LOG_ORG_NOT_FOUND = "Organization not found in AAP"

# ASCII control character boundaries for input sanitization
_MIN_PRINTABLE_CHAR = 0x20  # Space character (first printable ASCII)
_DEL_CHAR = 0x7F  # DEL control character


def _safe_map[T](data: dict[str, Any], mapper: Callable[[dict[str, Any]], T]) -> list[T]:
    """Map AAP response results through *mapper*, skipping malformed entries.

    Logs a warning for each entry that raises ``KeyError``, ``TypeError``,
    ``ValueError``, or ``AssertionError`` (e.g. missing ``id`` / ``name``
    fields or invalid values), rather than letting one bad record break
    the entire response.
    """
    results: list[T] = []
    for entry in data.get("results", []):
        try:
            results.append(mapper(entry))
        except (KeyError, TypeError, ValueError, AssertionError) as exc:
            # Log only safe identifiers, not the full entry (which may contain sensitive data)
            entry_id = entry.get("id")
            entry_name = entry.get("name")
            logger.warning(
                "Skipping malformed AAP resource entry",
                entry_id=entry_id,
                entry_name=entry_name,
                error=str(exc),
            )
    return results


class AAPProxyService:
    """BFF proxy service that forwards requests to AAP Controller REST API v2.

    Each public method resolves AAP auth, calls the appropriate AAP endpoint,
    and returns typed Pydantic models for the router to serialize.
    """

    def __init__(
        self,
        settings: Settings,
        session: AsyncSession,
        allowed_projects: AllowedProjectsResult | None = None,
    ) -> None:
        """Initialize with injected dependencies."""
        self._settings = settings
        self._session = session
        self._allowed_projects = allowed_projects
        # Lazily created per-connection client to avoid repeated TCP/TLS setup
        # within the same request (e.g., org resolution + resource list).
        self._client: httpx.AsyncClient | None = None
        self._client_connection: AAPConnection | None = None

    async def close(self) -> None:
        """Close the underlying httpx client, if any."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            self._client_connection = None

    # ------------------------------------------------------------------
    # Shared template helpers (DRY - reduce duplication)
    # ------------------------------------------------------------------

    async def _list_templates[T](
        self,
        resource_path: str,
        mapper: Callable[[dict[str, Any]], T],
        query: AAPResourceQuery,
        user_id: UUID | None = None,
    ) -> AAPListResponse[T]:
        """List templates generically for job_templates and workflow_job_templates.

        Reduces code duplication between list_job_templates and list_workflow_job_templates.
        """
        connection = await self._resolve_connection(
            credential_id=query.credential_id, user_id=user_id, integration_id=query.integration_id
        )
        params = self._build_params(search=query.search, page_size=query.page_size)

        if query.organization:
            org_id = await self._resolve_organization_id(connection, query.organization)
            if org_id is None:
                # Organization not found — return empty list rather than widening the query
                logger.warning(_LOG_ORG_NOT_FOUND, organization=query.organization)
                return AAPListResponse(count=0, results=[])
            params["organization"] = str(org_id)

        data = await self._proxy_get(connection, f"{_AAP_API_PREFIX}/{resource_path}/", params)
        results = _safe_map(data, mapper)
        return AAPListResponse(count=data.get("count", len(results)), results=results)

    async def _get_template_detail[T: BaseModel](
        self,
        resource_path: str,
        template_id: int,
        model_class: type[T],
        url_path: str,
        credential_id: str | None = None,
        user_id: UUID | None = None,
        integration_id: UUID | str | None = None,
    ) -> T:
        """Get template detail generically for job_templates and workflow_job_templates.

        Reduces code duplication between get_job_template and get_workflow_job_template.
        """
        connection = await self._resolve_connection(
            credential_id=credential_id, user_id=user_id, integration_id=integration_id
        )
        data = await self._proxy_get(connection, f"{_AAP_API_PREFIX}/{resource_path}/{template_id}/", {})
        detail = model_class.model_validate(data)
        # Only set detail.url if aap_public_url is explicitly configured (avoid leaking internal addresses)
        # Type ignore: T is bound to BaseModel but url attribute exists on both AAPJobTemplateDetail
        # and AAPWorkflowJobTemplateDetail (the only two types passed to this helper)
        if self._settings.aap_public_url:
            public_url = self._settings.aap_public_url.rstrip("/")
            detail.url = f"{public_url}/execution/templates/{url_path}/{template_id}/details"  # type: ignore[attr-defined]
        else:
            detail.url = None  # type: ignore[attr-defined]
        return detail

    # ------------------------------------------------------------------
    # Public service methods
    # ------------------------------------------------------------------

    async def list_organizations(
        self, query: AAPBaseQuery, user_id: UUID | None = None
    ) -> AAPListResponse[AAPOrganization]:
        """List AAP organizations."""
        connection = await self._resolve_connection(
            credential_id=query.credential_id, user_id=user_id, integration_id=query.integration_id
        )
        params = self._build_params(search=query.search, page_size=query.page_size)
        data = await self._proxy_get(connection, f"{_AAP_API_PREFIX}/organizations/", params)
        results = _safe_map(data, lambda r: AAPOrganization(id=r["id"], name=r["name"]))
        return AAPListResponse(count=data.get("count", len(results)), results=results)

    async def list_job_templates(
        self, query: AAPResourceQuery, user_id: UUID | None = None
    ) -> AAPListResponse[AAPJobTemplate]:
        """List AAP job templates, optionally filtered by organization."""
        return await self._list_templates(
            "job_templates",
            lambda r: AAPJobTemplate(id=r["id"], name=r["name"], description=r.get("description")),
            query,
            user_id,
        )

    async def get_job_template(
        self,
        job_template_id: int,
        credential_id: str | None = None,
        user_id: UUID | None = None,
        integration_id: UUID | str | None = None,
    ) -> AAPJobTemplateDetail:
        """Get AAP job template details including prompt-on-launch flags."""
        return await self._get_template_detail(
            "job_templates",
            job_template_id,
            AAPJobTemplateDetail,
            "job-template",
            credential_id,
            user_id,
            integration_id,
        )

    async def list_workflow_job_templates(
        self, query: AAPResourceQuery, user_id: UUID | None = None
    ) -> AAPListResponse[AAPWorkflowJobTemplate]:
        """List AAP workflow job templates, optionally filtered by organization."""
        return await self._list_templates(
            "workflow_job_templates",
            lambda r: AAPWorkflowJobTemplate(id=r["id"], name=r["name"], description=r.get("description")),
            query,
            user_id,
        )

    async def get_workflow_job_template(
        self,
        workflow_job_template_id: int,
        credential_id: str | None = None,
        user_id: UUID | None = None,
        integration_id: UUID | str | None = None,
    ) -> AAPWorkflowJobTemplateDetail:
        """Get AAP workflow job template details including prompt-on-launch flags."""
        return await self._get_template_detail(
            "workflow_job_templates",
            workflow_job_template_id,
            AAPWorkflowJobTemplateDetail,
            "workflow-job-template",
            credential_id,
            user_id,
            integration_id,
        )

    async def list_inventories(
        self, query: AAPResourceQuery, user_id: UUID | None = None
    ) -> AAPListResponse[AAPInventory]:
        """List AAP inventories, optionally filtered by organization."""
        connection = await self._resolve_connection(
            credential_id=query.credential_id, user_id=user_id, integration_id=query.integration_id
        )
        params = self._build_params(search=query.search, page_size=query.page_size)

        if query.organization:
            org_id = await self._resolve_organization_id(connection, query.organization)
            if org_id is None:
                # Organization not found — return empty list rather than widening the query
                logger.warning(_LOG_ORG_NOT_FOUND, organization=query.organization)
                return AAPListResponse(count=0, results=[])
            params["organization"] = str(org_id)

        data = await self._proxy_get(connection, f"{_AAP_API_PREFIX}/inventories/", params)
        results = _safe_map(data, lambda r: AAPInventory(id=r["id"], name=r["name"], description=r.get("description")))
        return AAPListResponse(count=data.get("count", len(results)), results=results)

    async def list_execution_environments(
        self, query: AAPResourceQuery, user_id: UUID | None = None
    ) -> AAPListResponse[AAPExecutionEnvironment]:
        """List AAP execution environments belonging to the selected org or having no org."""
        connection = await self._resolve_connection(
            credential_id=query.credential_id, user_id=user_id, integration_id=query.integration_id
        )
        params = self._build_params(search=query.search, page_size=query.page_size)

        if query.organization:
            org_id = await self._resolve_organization_id(connection, query.organization)
            if org_id is None:
                # Organization not found — return empty list rather than widening the query
                logger.warning(_LOG_ORG_NOT_FOUND, organization=query.organization)
                return AAPListResponse(count=0, results=[])
            params["or__organization__id"] = str(org_id)
            params["or__organization__isnull"] = "True"

        data = await self._proxy_get(connection, f"{_AAP_API_PREFIX}/execution_environments/", params)
        results = _safe_map(
            data, lambda r: AAPExecutionEnvironment(id=r["id"], name=r["name"], description=r.get("description"))
        )
        return AAPListResponse(count=data.get("count", len(results)), results=results)

    async def list_credentials(
        self, query: AAPBaseQuery, user_id: UUID | None = None
    ) -> AAPListResponse[AAPCredential]:
        """List AAP credentials (not organization-scoped)."""
        connection = await self._resolve_connection(
            credential_id=query.credential_id, user_id=user_id, integration_id=query.integration_id
        )
        params = self._build_params(search=query.search, page_size=query.page_size)
        data = await self._proxy_get(connection, f"{_AAP_API_PREFIX}/credentials/", params)
        results = _safe_map(data, lambda r: AAPCredential(id=r["id"], name=r["name"]))
        return AAPListResponse(count=data.get("count", len(results)), results=results)

    async def list_instance_groups(
        self, query: AAPBaseQuery, user_id: UUID | None = None
    ) -> AAPListResponse[AAPInstanceGroup]:
        """List AAP instance groups (not organization-scoped)."""
        connection = await self._resolve_connection(
            credential_id=query.credential_id, user_id=user_id, integration_id=query.integration_id
        )
        params = self._build_params(search=query.search, page_size=query.page_size)
        data = await self._proxy_get(connection, f"{_AAP_API_PREFIX}/instance_groups/", params)
        results = _safe_map(data, lambda r: AAPInstanceGroup(id=r["id"], name=r["name"]))
        return AAPListResponse(count=data.get("count", len(results)), results=results)

    async def list_labels(self, query: AAPBaseQuery, user_id: UUID | None = None) -> AAPListResponse[AAPLabel]:
        """List AAP labels."""
        connection = await self._resolve_connection(
            credential_id=query.credential_id, user_id=user_id, integration_id=query.integration_id
        )
        params = self._build_params(search=query.search, page_size=query.page_size)
        data = await self._proxy_get(connection, f"{_AAP_API_PREFIX}/labels/", params)
        results = _safe_map(
            data,
            lambda r: AAPLabel(id=r["id"], name=r["name"], organization=r.get("organization")),
        )
        return AAPListResponse(count=data.get("count", len(results)), results=results)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _resolve_connection(
        self,
        credential_id: UUID | str | None = None,
        user_id: UUID | None = None,
        integration_id: UUID | str | None = None,
    ) -> AAPConnection:
        """Resolve AAP connection from an integration and credential.

        ``integration_id`` and ``credential_id`` are optional. When omitted, the
        proxy uses the unique visible enabled AAP integration and its
        management credential. ``validation_status`` is not considered.

        When the caller supplies ``credential_id``, that credential's owner
        must match ``user_id``. Omitted ``credential_id`` uses the integration's
        management credential after visibility has been enforced.

        Args:
            credential_id: Syntara credential ID for AAP authentication.
            user_id: User ID for authorization check.
            integration_id: AAP Gateway integration ID for connection URL resolution.

        Returns:
            AAPConnection with auth resolved and TLS verification enforced.

        Raises:
            AAPNotConfiguredError: Integration/credential not found, disabled, or IDs missing.
            AAPAuthenticationError: Credential decryption failed or user not authorized.
            ValueError: user_id not provided for connection resolution.

        """
        if credential_id is not None and user_id is None:
            msg = "user_id is required when credential_id is provided (authorization check cannot be bypassed)"
            raise ValueError(msg)
        integration = await self._resolve_aap_integration(integration_id)
        if user_id is None:
            msg = "user_id is required for AAP proxy connection resolution"
            raise ValueError(msg)
        return await self._resolve_connection_from_integration(
            integration=integration,
            credential_id=credential_id,
            user_id=user_id,
        )

    async def _enforce_integration_visibility(self, integration: Integration) -> None:
        """Raise AAPNotConfiguredError if the caller cannot see the integration.

        Delegates to ``IntegrationService.resolve_visible_integration_ids`` so
        proxy defaulting and ``GET /integrations`` share the same GLOBAL /
        project-assignment rules.
        """
        if self._allowed_projects is None:
            return
        visible_ids = await IntegrationService.resolve_visible_integration_ids(self._session, self._allowed_projects)
        if visible_ids is not None and integration.id not in set(visible_ids):
            msg = f"Integration {integration.id} not found"
            raise AAPNotConfiguredError(msg)

    async def _list_visible_aap_integrations(self) -> list[Integration]:
        """Return enabled AAP integrations the caller is allowed to see."""
        stmt = select(Integration).where(
            Integration.integration_type == IntegrationType.ANSIBLE_AUTOMATION_PLATFORM,
            col(Integration.enabled).is_(True),
        )
        if self._allowed_projects is not None:
            visible_ids = await IntegrationService.resolve_visible_integration_ids(
                self._session, self._allowed_projects
            )
            if visible_ids is not None:
                if not visible_ids:
                    return []
                stmt = stmt.where(col(Integration.id).in_(visible_ids))
        result = await self._session.exec(stmt)
        return list(result.all())

    @staticmethod
    def _select_default_aap_integration(integrations: list[Integration]) -> Integration:
        """Pick the unique visible enabled AAP integration when integration_id is omitted.

        Uniqueness is exactly one visible enabled integration, matching the
        public API contract. ``validation_status`` is not a tie-break.
        """
        if not integrations:
            msg = "No enabled AAP Controller integration is configured"
            raise AAPNotConfiguredError(msg)
        if len(integrations) > 1:
            msg = "Multiple AAP Controller integrations are configured; pass integration_id to select one"
            raise AAPNotConfiguredError(msg)
        return integrations[0]

    async def _resolve_aap_integration(self, integration_id: UUID | str | None) -> Integration:
        """Load the requested AAP integration, or the unique visible default."""
        if integration_id:
            return await self._load_aap_integration(integration_id)
        candidates = await self._list_visible_aap_integrations()
        integration = self._select_default_aap_integration(candidates)
        logger.info(
            "AAP proxy using default integration",
            integration_id=str(integration.id),
            integration_name=integration.name,
        )
        return integration

    async def _load_aap_integration(self, integration_id: UUID | str) -> Integration:
        """Fetch an AAP integration by ID and enforce type, enabled, and visibility."""
        parsed_id: UUID
        if isinstance(integration_id, str):
            try:
                parsed_id = UUID(integration_id)
            except ValueError as e:
                msg = f"Invalid integration_id format: must be a valid UUID, got '{integration_id}'"
                raise AAPNotConfiguredError(msg) from e
        else:
            parsed_id = integration_id

        stmt = select(Integration).where(Integration.id == parsed_id)
        result = await self._session.exec(stmt)
        integration = result.one_or_none()

        if not integration:
            msg = f"Integration {parsed_id} not found"
            raise AAPNotConfiguredError(msg)

        if integration.integration_type != IntegrationType.ANSIBLE_AUTOMATION_PLATFORM:
            msg = (
                f"Integration {parsed_id} is type '{integration.integration_type}',"
                " expected 'ansible_automation_platform'"
            )
            raise AAPNotConfiguredError(msg)

        if not integration.enabled:
            msg = f"Integration '{integration.name}' is disabled"
            raise AAPNotConfiguredError(msg)

        await self._enforce_integration_visibility(integration)
        return integration

    async def _resolve_connection_from_integration(
        self,
        integration: Integration,
        credential_id: UUID | str | None,
        user_id: UUID,
    ) -> AAPConnection:
        """Resolve AAP connection URL from an integration, with auth from a credential."""
        config = integration.configuration
        if not isinstance(config, AAPConfiguration):
            msg = f"Integration {integration.id} has invalid configuration type"
            raise AAPNotConfiguredError(msg)

        # Re-run the integration SSRF policy at request time: the stored base_url may have
        # been re-pointed to a private/metadata address (DNS rebinding) since write time.
        try:
            validate_integration_configuration_no_ssrf(config)
        except ValueError as e:
            msg = "AAP base_url is not permitted by SSRF policy"
            raise AAPNotConfiguredError(msg) from e

        base_url = config.base_url.rstrip("/")
        verify_ssl = not config.insecure_skip_tls_verify

        if credential_id:
            logger.debug(
                "Resolving AAP auth from credential with integration URL",
                integration_id=str(integration.id),
                credential_id=str(credential_id),
            )
            cred_connection = await resolve_aap_connection_from_credential(
                session=self._session,
                credential_id=credential_id,
                user_id=user_id,
            )
        else:
            logger.info(
                "AAP proxy using integration management credential",
                integration_id=str(integration.id),
                credential_id=str(integration.management_credential_id)
                if integration.management_credential_id
                else None,
            )
            cred_connection = await resolve_aap_connection_from_management_credential(
                session=self._session,
                integration=integration,
            )
        return AAPConnection(
            base_url=base_url,
            headers=cred_connection.headers,
            basic_auth=cred_connection.basic_auth,
            verify_ssl=verify_ssl,
            ca_certificate=config.ca_certificate,
            timeout=cred_connection.timeout,
        )

    async def _resolve_organization_id(self, connection: AAPConnection, org_name: str) -> int | None:
        """Resolve an organization name to its AAP ID.

        Uses AAP's ``name`` query parameter for exact matching (not ``search``
        which is full-text/contains).

        Returns None if the organization is not found (results will be unfiltered).
        """
        # Sanitize organization name by removing control characters
        sanitized_name = "".join(
            char for char in org_name if ord(char) >= _MIN_PRINTABLE_CHAR and ord(char) != _DEL_CHAR
        )
        params: dict[str, str] = {"name": sanitized_name, "page_size": "1"}
        data = await self._proxy_get(connection, f"{_AAP_API_PREFIX}/organizations/", params)
        results = data.get("results", [])
        if results:
            try:
                return int(results[0]["id"])
            except (KeyError, TypeError, ValueError):
                logger.warning("Malformed organization entry in AAP response", entry=results[0])
                return None
        return None

    @staticmethod
    def _build_params(
        search: str | None = None,
        page_size: int = 50,
    ) -> dict[str, str]:
        """Build query params dict for AAP API.

        Sanitizes search input by removing control characters to prevent
        unexpected behavior in the upstream AAP API.
        """
        params: dict[str, str] = {"page_size": str(page_size)}
        if search:
            # Strip control characters (ASCII 0x00-0x1F, 0x7F) from search input
            sanitized = "".join(char for char in search if ord(char) >= _MIN_PRINTABLE_CHAR and ord(char) != _DEL_CHAR)
            if sanitized:
                params["search"] = sanitized
        return params

    async def _get_client(self, connection: AAPConnection) -> httpx.AsyncClient:
        """Return a reusable httpx client for the given connection.

        A new client is created only when the connection details change,
        avoiding repeated TCP/TLS handshakes within the same request
        (e.g., org-name resolution followed by a resource list).
        Closes the previous client if connection details changed.
        """
        if self._client is not None and self._client_connection != connection:
            await self._client.aclose()
            self._client = None
            self._client_connection = None
        if self._client is None:
            verify = build_integration_httpx_verify(
                insecure_skip_tls_verify=not connection.verify_ssl,
                ca_certificate=connection.ca_certificate,
            )
            self._client = httpx.AsyncClient(
                verify=verify,
                timeout=connection.timeout,
            )
            self._client_connection = connection
        return self._client

    async def _proxy_get(
        self,
        connection: AAPConnection,
        path: str,
        params: dict[str, str],
    ) -> dict[str, Any]:
        """Execute authenticated GET against AAP Controller.

        Raises:
            AAPConnectionError: Network error or timeout.
            AAPAuthenticationError: AAP returned 401/403.
            AAPUpstreamError: AAP returned other 4xx/5xx.

        """
        url = f"{connection.base_url}{path}"
        client = await self._get_client(connection)
        logger.debug("AAP proxy GET", path=path)

        response = await self._send_request(client, url, connection, params)

        logger.debug("AAP proxy response", path=path, status=response.status_code)

        self._check_response_status(response)

        try:
            return response.json()  # type: ignore[no-any-return]
        except ValueError as e:
            msg = "AAP Controller returned an invalid response"
            logger.exception(
                "AAP invalid JSON response",
                url=url,
                content_type=response.headers.get("content-type"),
                content_length=len(response.text),
            )
            raise AAPUpstreamError(msg) from e

    @staticmethod
    async def _send_request(
        client: httpx.AsyncClient,
        url: str,
        connection: AAPConnection,
        params: dict[str, str],
    ) -> httpx.Response:
        """Send GET request to AAP Controller, mapping transport errors."""
        try:
            return await client.get(
                url,
                headers=connection.headers,
                auth=connection.basic_auth,
                params=params,
            )
        except httpx.TimeoutException as e:
            msg = "AAP Controller request timed out"
            logger.exception("AAP timeout", error_type=type(e).__name__)
            raise AAPConnectionError(msg) from e
        except httpx.ConnectError as e:
            msg = "Cannot connect to AAP Controller"
            logger.exception("AAP ConnectError", error_type=type(e).__name__)
            raise AAPConnectionError(msg) from e
        except httpx.RequestError as e:
            msg = "AAP Controller request failed"
            logger.exception("AAP RequestError", error_type=type(e).__name__)
            raise AAPConnectionError(msg) from e
        except Exception as e:
            msg = "AAP Controller request failed unexpectedly"
            logger.exception("AAP unexpected error", error_type=type(e).__name__)
            raise AAPConnectionError(msg) from e

    @staticmethod
    def _check_response_status(response: httpx.Response) -> None:
        """Check HTTP response status and raise domain errors for failures."""
        if response.status_code in (401, 403):
            msg = "AAP Controller authentication failed"
            logger.error("AAP auth failed", status=response.status_code)
            raise AAPAuthenticationError(msg)

        if response.status_code >= _HTTP_STATUS_CLIENT_ERROR:
            logger.error("AAP upstream error", status=response.status_code)
            msg = f"AAP Controller returned HTTP {response.status_code}"
            raise AAPUpstreamError(msg)
