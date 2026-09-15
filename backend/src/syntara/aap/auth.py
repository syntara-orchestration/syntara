"""Shared AAP Controller connection types and env-var auth resolution.

``AAPConnection`` is the resolved connection used by the AAP proxy and by
AAP job-template activities.

``resolve_aap_connection`` reads environment variables
(``APP_AAP_BASE_URL``, ``APP_AAP_TOKEN``, ``APP_AAP_USERNAME``,
``APP_AAP_PASSWORD``, ``APP_AAP_VERIFY_SSL``). The BFF proxy no longer uses
this path — it resolves URL and auth from the AAP integration and credential.
Env-var resolution remains for workflow execution when no credential is
injected at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import httpx
import structlog

from syntara.aap.exceptions import AAPNotConfiguredError

if TYPE_CHECKING:
    from syntara.core.config.base import Settings

logger = structlog.stdlib.get_logger(__name__)


@dataclass(frozen=True)
class AAPConnection:
    """Resolved AAP Controller connection details."""

    base_url: str
    headers: dict[str, str] = field(default_factory=dict)
    basic_auth: httpx.BasicAuth | None = None
    verify_ssl: bool = True
    ca_certificate: str | None = None
    timeout: float = 30.0


def _get_auth_headers_from_settings(settings: Settings) -> dict[str, str]:
    """Get AAP auth headers from environment settings (token preferred).

    Returns:
        Auth headers dict, or empty dict if basic auth should be used.

    Raises:
        AAPNotConfiguredError: If no authentication is configured.

    """
    if settings.aap_token:
        return {"Authorization": f"Bearer {settings.aap_token.get_secret_value()}"}
    if settings.aap_username and settings.aap_password:
        return {}
    msg = "AAP authentication not configured. Set APP_AAP_TOKEN or APP_AAP_USERNAME/PASSWORD."
    raise AAPNotConfiguredError(msg)


def _get_basic_auth_from_settings(settings: Settings) -> httpx.BasicAuth | None:
    """Get AAP basic auth from environment settings."""
    if settings.aap_username and settings.aap_password and not settings.aap_token:
        return httpx.BasicAuth(settings.aap_username, settings.aap_password.get_secret_value())
    return None


def resolve_aap_connection(settings: Settings) -> AAPConnection:
    """Resolve AAP connection from environment settings.

    Used by workflow execution when no Orchestrator credential is injected.
    The BFF proxy (``/proxies/aap/*``) does not call this — it resolves
    from the AAP integration and credential instead.

    Args:
        settings: Application settings.

    Returns:
        AAPConnection with resolved auth details.

    Raises:
        AAPNotConfiguredError: If AAP host or auth is not configured.

    """
    base_url = (settings.aap_base_url or "").rstrip("/")
    verify_ssl = settings.aap_verify_ssl
    headers = _get_auth_headers_from_settings(settings)
    basic_auth = _get_basic_auth_from_settings(settings)

    if not base_url:
        msg = "AAP host not configured. Set APP_AAP_BASE_URL."
        raise AAPNotConfiguredError(msg)

    # Reject plaintext HTTP when credentials would be sent in the clear
    if (basic_auth is not None or headers) and not base_url.startswith("https://"):
        msg = "AAP credentials require HTTPS. Set APP_AAP_BASE_URL to an https:// URL."
        raise AAPNotConfiguredError(msg)

    # Reject disabled SSL verification when basic auth sends passwords in every request
    if not verify_ssl and basic_auth is not None:
        msg = "AAP basic auth requires SSL verification. Remove APP_AAP_VERIFY_SSL=false or switch to token auth."
        raise AAPNotConfiguredError(msg)

    if not verify_ssl:
        logger.warning(
            "AAP SSL verification disabled — connections are vulnerable to MITM attacks",
            base_url=base_url,
        )

    return AAPConnection(
        base_url=base_url,
        headers=headers,
        basic_auth=basic_auth,
        verify_ssl=verify_ssl,
        timeout=float(settings.aap_proxy_timeout_seconds),
    )
