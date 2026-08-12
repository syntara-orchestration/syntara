"""Ansible Automation Platform adapter implementing validate() and discover().

validate(): Hits GET /api/gateway/v1/me/ to confirm both endpoint
  reachability and credential validity in a single call.

  Auth precedence: oauth_token (Bearer) → username+password (Basic).
  Longer-term, the Credential backend will make these mutually exclusive.

discover(): Delegates to validate() and returns an empty DiscoverResult.
  Ansible Automation Platform has no discoverable resources at the integration level;
  AAP objects (job templates, inventories) are browsed at workflow-design
  time using the execution credential.
"""

from __future__ import annotations

import ssl
from datetime import UTC, datetime
from typing import Any, cast

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
from syntara.integrations.models.integration_configuration import AAPConfiguration  # noqa: TC001

logger = structlog.stdlib.get_logger(__name__)

_AAP_OAUTH_TOKEN_KEY = "aap_oauth_token"  # noqa: S105
_AAP_USERNAME_KEY = "aap_username"
_AAP_PASSWORD_KEY = "aap_password"  # noqa: S105
_AAP_HEALTH_ENDPOINT = "/api/gateway/v1/me/"


class AAPAdapter:
    """Adapter for Ansible Automation Platform integrations implementing validate() and discover().

    Uses a single authenticated endpoint (GET /api/gateway/v1/me/) to verify
    both connectivity and credential validity. The Ansible Automation Platform does not expose
    discoverable resources at the integration level, so discover() delegates
    to validate() and returns an empty DiscoverResult.
    """

    def __init__(self, config: AAPConfiguration) -> None:
        """Initialize with Ansible Automation Platform configuration.

        Args:
            config: Non-sensitive integration configuration containing
                base_url and insecure_skip_tls_verify.

        """
        self._config = config

    def _resolve_auth(
        self,
        resolved_credential: dict[str, Any],
    ) -> tuple[dict[str, str], httpx.BasicAuth | None, str] | None:
        """Resolve authentication from credential extra_vars.

        Returns (headers, basic_auth, auth_method) or None if no usable
        credentials are present.
        """
        token = (resolved_credential.get(_AAP_OAUTH_TOKEN_KEY) or "").strip()
        username = (resolved_credential.get(_AAP_USERNAME_KEY) or "").strip()
        password = (resolved_credential.get(_AAP_PASSWORD_KEY) or "").strip()

        if token:
            return {"Authorization": f"Bearer {token}"}, None, "oauth_token"
        if username and password:
            return {}, httpx.BasicAuth(username=username, password=password), "basic"
        return None

    async def validate(
        self,
        resolved_credential: dict[str, Any],
        timeout_seconds: int,
    ) -> ValidateResult:
        """Validate connectivity and credential against the Ansible Automation Platform.

        Hits GET {base_url}/api/gateway/v1/me/ with authenticated request.
        A 200 response confirms both reachability and credential validity.

        Auth precedence: oauth_token (Bearer) → username+password (Basic).

        Args:
            resolved_credential: extra_vars dict from InjectorResolver.resolve().
                Recognized keys: ``aap_oauth_token``, ``aap_username``,
                ``aap_password``.
            timeout_seconds: Maximum seconds to wait for the HTTP response.

        """
        auth = self._resolve_auth(resolved_credential)
        if auth is None:
            logger.warning(
                "Ansible Automation Platform validate: no usable credentials configured",
                base_url=self._config.base_url,
            )
            return ValidateResult(
                success=False,
                checked_at=datetime.now(UTC),
                error="Authentication configuration is incomplete",
                error_type=HealthCheckErrorType.AUTH_FAILURE,
            )

        headers, basic_auth, auth_method = auth
        url = f"{self._config.base_url.rstrip('/')}{_AAP_HEALTH_ENDPOINT}"

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
            async with httpx.AsyncClient(
                verify=verify,
                timeout=timeout_seconds,
            ) as client:
                response = await client.get(url, headers=headers, auth=basic_auth)
                response.raise_for_status()

            logger.info(
                "Ansible Automation Platform validate succeeded",
                base_url=self._config.base_url,
                auth_method=auth_method,
            )

        except* (TimeoutError, httpx.TimeoutException):
            success = False
            error_msg = f"Connection timed out after {timeout_seconds}s"
            error_type = HealthCheckErrorType.TIMEOUT
            logger.warning(
                "Ansible Automation Platform validate timed out",
                base_url=self._config.base_url,
                timeout_seconds=timeout_seconds,
            )

        except* HTTPStatusError as eg:
            success = False
            errors = extract_all_exceptions(eg)
            error_type, error_msg = classify_http_error(errors)
            logger.warning(
                "Ansible Automation Platform validate HTTP error",
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
                "Ansible Automation Platform validate SSL error",
                base_url=self._config.base_url,
                error=str(errors[0]) if errors else "",
            )

        except* (httpx.ConnectError, OSError) as eg:
            success = False
            errors = extract_all_exceptions(eg)
            error_msg = "Unable to connect to Ansible Automation Platform"
            error_type = HealthCheckErrorType.CONNECTION_ERROR
            logger.warning(
                "Ansible Automation Platform validate connection error",
                base_url=self._config.base_url,
                error=str(errors[0]) if errors else "",
            )

        except* Exception as eg:
            success = False
            errors = extract_all_exceptions(eg)
            error_msg = "Request failed unexpectedly"
            error_type = HealthCheckErrorType.CONNECTION_ERROR
            logger.exception(
                "Unexpected error during Ansible Automation Platform validate",
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
        """Discover resources from the Ansible Automation Platform.

        Ansible Automation Platform has no discoverable resources at the integration level.
        This method delegates to validate() and wraps the result in a
        DiscoverResult with empty resource fields.

        Args:
            resolved_credential: extra_vars dict from InjectorResolver.resolve().
            timeout_seconds: Maximum seconds to wait for the HTTP response.

        """
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
    IntegrationType.ANSIBLE_AUTOMATION_PLATFORM,
    lambda c: AAPAdapter(cast("AAPConfiguration", c)),
)
