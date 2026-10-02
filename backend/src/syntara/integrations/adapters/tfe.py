"""Terraform Enterprise adapter implementing validate() and discover().

validate(): Hits GET /api/v2/organizations/{org} to confirm endpoint
  reachability, credential validity, and organization access.

discover(): Delegates to validate() and returns an empty DiscoverResult.
  TFE has no discoverable resources at the integration level; workspace
  and project operations are workflow steps.
"""

from __future__ import annotations

import ssl
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import quote

import httpx
import structlog
from httpx import HTTPStatusError

from syntara.core.lib.tls_utils import build_integration_httpx_verify
from syntara.core.utils.exceptions import extract_all_exceptions
from syntara.integrations.adapters.factory import register_health_check_adapter
from syntara.integrations.adapters.protocol import (
    DiscoverResult,
    HealthCheckErrorType,
    ValidateResult,
    classify_http_error,
)
from syntara.integrations.models.integration import IntegrationType
from syntara.integrations.models.integration_configuration import TFEConfiguration  # noqa: TC001

logger = structlog.stdlib.get_logger(__name__)

_BEARER_TOKEN_KEY = "bearer_token"  # noqa: S105
_TFE_API_PREFIX = "/api/v2"
_TFE_JSON_API_ACCEPT = "application/vnd.api+json"


class TFEAdapter:
    """Adapter for Terraform Enterprise integrations."""

    def __init__(self, config: TFEConfiguration) -> None:
        """Initialize with TFE configuration."""
        self._config = config

    def _resolve_token(self, resolved_credential: dict[str, Any]) -> str | None:
        """Extract Bearer token from HTTP Bearer Token credential injectors."""
        token = (resolved_credential.get(_BEARER_TOKEN_KEY) or "").strip()
        return token or None

    async def validate(
        self,
        resolved_credential: dict[str, Any],
        timeout_seconds: int,
    ) -> ValidateResult:
        """Validate connectivity and credential against Terraform Enterprise."""
        token = self._resolve_token(resolved_credential)
        if token is None:
            logger.warning(
                "TFE validate: no usable credentials configured",
                base_url=self._config.base_url,
            )
            return ValidateResult(
                success=False,
                checked_at=datetime.now(UTC),
                error="Authentication configuration is incomplete",
                error_type=HealthCheckErrorType.AUTH_FAILURE,
            )

        org = quote(self._config.organization, safe="")
        url = f"{self._config.base_url.rstrip('/')}{_TFE_API_PREFIX}/organizations/{org}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": _TFE_JSON_API_ACCEPT,
            "Accept": _TFE_JSON_API_ACCEPT,
        }

        if self._config.insecure_skip_tls_verify:
            logger.warning(
                "TLS verification disabled. Connection is vulnerable to MITM attacks",
                base_url=self._config.base_url,
            )

        verify = build_integration_httpx_verify(
            insecure_skip_tls_verify=self._config.insecure_skip_tls_verify,
            ca_certificate=self._config.ca_certificate,
        )

        success = True
        error_msg: str | None = None
        error_type: HealthCheckErrorType | None = None

        try:
            async with httpx.AsyncClient(verify=verify, timeout=timeout_seconds) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()

            logger.info(
                "TFE validate succeeded",
                base_url=self._config.base_url,
                organization=self._config.organization,
            )

        except* (TimeoutError, httpx.TimeoutException):
            success = False
            error_msg = f"Connection timed out after {timeout_seconds}s"
            error_type = HealthCheckErrorType.TIMEOUT
            logger.warning(
                "TFE validate timed out",
                base_url=self._config.base_url,
                timeout_seconds=timeout_seconds,
            )

        except* HTTPStatusError as eg:
            success = False
            errors = extract_all_exceptions(eg)
            error_type, error_msg = classify_http_error(errors)
            logger.warning(
                "TFE validate HTTP error",
                base_url=self._config.base_url,
                error_type=error_type.value,
                status_codes=[e.response.status_code for e in errors if isinstance(e, HTTPStatusError)],
            )

        except* ssl.SSLError as eg:
            success = False
            errors = extract_all_exceptions(eg)
            error_msg = "SSL/TLS verification failed"
            error_type = HealthCheckErrorType.SSL_ERROR
            logger.warning(
                "TFE validate SSL error",
                base_url=self._config.base_url,
                error=str(errors[0]) if errors else "",
            )

        except* (httpx.ConnectError, OSError) as eg:
            success = False
            errors = extract_all_exceptions(eg)
            error_msg = "Unable to connect to Terraform Enterprise"
            error_type = HealthCheckErrorType.CONNECTION_ERROR
            logger.warning(
                "TFE validate connection error",
                base_url=self._config.base_url,
                error=str(errors[0]) if errors else "",
            )

        except* Exception as eg:
            success = False
            errors = extract_all_exceptions(eg)
            error_msg = "Request failed unexpectedly"
            error_type = HealthCheckErrorType.CONNECTION_ERROR
            logger.exception(
                "Unexpected error during TFE validate",
                base_url=self._config.base_url,
                error=str(errors[0]) if errors else "",
            )

        return ValidateResult(
            success=success,
            checked_at=datetime.now(UTC),
            error=error_msg,
            error_type=error_type,
        )

    async def discover(
        self,
        resolved_credential: dict[str, Any],
        timeout_seconds: int,
    ) -> DiscoverResult:
        """Discover resources from Terraform Enterprise (connectivity only)."""
        result = await self.validate(resolved_credential, timeout_seconds)
        return DiscoverResult(
            success=result.success,
            checked_at=result.checked_at,
            error=result.error,
            error_type=result.error_type,
            discovered_tools=None,
            discovered_models=None,
        )


register_health_check_adapter(
    IntegrationType.TERRAFORM_ENTERPRISE,
    lambda c: TFEAdapter(cast("TFEConfiguration", c)),
)
