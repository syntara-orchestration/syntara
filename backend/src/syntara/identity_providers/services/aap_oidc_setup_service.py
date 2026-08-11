"""AAP OIDC push-button setup service.

Orchestrates creating an OAuth2 application on an AAP and
configuring the corresponding identity provider in Nexus.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import httpx
import structlog

from syntara.api.constants import OIDC_CALLBACK_PATH
from syntara.identity_providers.exceptions import (
    AAPAuthenticationError,
    AAPConnectionError,
    AAPSetupError,
)
from syntara.identity_providers.models.identity_provider import (
    IdentityProviderCreate,
    IdentityProviderResponse,
)
from syntara.identity_providers.models.identity_provider_configuration import (
    OIDCClaimMapping,
    OIDCConfiguration,
    OIDCIdpType,
)

if TYPE_CHECKING:
    from syntara.core.config.base import Settings
    from syntara.identity_providers.models.aap_setup import AAPOIDCSetupRequest
    from syntara.identity_providers.services.identity_provider_service import IdentityProviderService

logger = structlog.stdlib.get_logger(__name__)

_AAP_API_PREFIX = "/api/gateway/v1"
_IDP_NAME = "Ansible Automation Platform"
_IDP_DESCRIPTION = "Auto-configured AAP OIDC provider"

_AAP_SCOPES = "read write openid roles"
_AAP_GROUP_JMESPATH = "[aap_teams[*].join('/', [organization, name]), aap_organizations[*].name] | []"


def _is_tls_verification_error(exc: BaseException) -> bool:
    """Check if a connection error was caused by TLS certificate verification failure."""
    return "CERTIFICATE_VERIFY_FAILED" in str(exc)


def _is_duplicate_app_error(body: dict[str, Any]) -> bool:
    """Check if the AAP error response indicates a duplicate application name."""
    for key in ("non_field_errors", "name"):
        errors = body.get(key)
        if isinstance(errors, list) and any("unique" in str(e).lower() for e in errors):
            return True
    return False


def _extract_aap_error_message(response: httpx.Response, *, app_name: str) -> str:
    """Parse an AAP error response into a human-readable message."""
    try:
        body = response.json()
    except ValueError:
        return f"AAP returned HTTP {response.status_code}"

    if not isinstance(body, dict):
        return f"AAP returned HTTP {response.status_code}"

    if _is_duplicate_app_error(body):
        return (
            f"An OAuth2 application named '{app_name}' already exists on this AAP. "
            "Delete the existing application from AAP before retrying, or configure the identity provider manually."
        )

    flat_errors: list[str] = []
    for field, errors in body.items():
        if isinstance(errors, list):
            flat_errors.extend(f"{field}: {e}" for e in errors)
        elif isinstance(errors, str):
            flat_errors.append(f"{field}: {errors}")

    if flat_errors:
        return f"AAP error: {'; '.join(flat_errors)}"

    return f"AAP returned HTTP {response.status_code}"


class AAPOIDCSetupService:
    """Orchestrates push-button AAP OIDC identity provider setup."""

    def __init__(
        self,
        idp_service: IdentityProviderService,
        settings: Settings,
    ) -> None:
        """Initialize with identity provider service and application settings."""
        self._idp_service = idp_service
        self._settings = settings

    async def setup(self, request: AAPOIDCSetupRequest) -> IdentityProviderResponse:
        """Create an OAuth2 app on AAP and configure the IdP in Nexus."""
        aap_url = request.aap_url.rstrip("/")
        redirect_uri = f"{self._settings.jwt_issuer}{OIDC_CALLBACK_PATH}"

        if request.personal_access_token:
            auth = None
            auth_headers = {"Authorization": f"Bearer {request.personal_access_token}"}
        else:
            auth = httpx.BasicAuth(request.admin_username, request.admin_password)  # type: ignore[arg-type]
            auth_headers = None

        async with httpx.AsyncClient(
            verify=not request.insecure_skip_tls_verify,
            timeout=30.0,
        ) as client:
            org_id = await self._resolve_organization(client, aap_url, auth, request.organization, auth_headers)
            client_id, client_secret = await self._create_oauth2_app(
                client, aap_url, auth, redirect_uri, org_id, auth_headers
            )

        issuer_url = f"{aap_url}/o/"

        provider_create = IdentityProviderCreate(
            name=_IDP_NAME,
            description=_IDP_DESCRIPTION,
            configuration=OIDCConfiguration(
                provider_type="oidc",
                idp_type=OIDCIdpType.AAP,
                auto_discovery=True,
                issuer_url=issuer_url,
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                scopes=_AAP_SCOPES,
                claim_mapping=OIDCClaimMapping(),
                group_jmespath_expression=_AAP_GROUP_JMESPATH,
                aap_role_mapping_enabled=True,
                enable_rp_initiated_logout=True,
                allow_all_authenticated=False,
                disable_tls_verify=request.insecure_skip_tls_verify,
            ),
        )

        return await self._idp_service.create_provider(provider_create)

    def _build_post_logout_redirect_uris(self) -> str:
        """Build the post-logout redirect URIs for the AAP OAuth2 app.

        Registers both with and without trailing slash since browsers
        may send either form, and AAP does exact-match validation.
        Includes CORS origins to cover the frontend URL.
        """
        uris: set[str] = set()
        base = self._settings.post_logout_redirect_uri
        uris.add(base.rstrip("/"))
        uris.add(base.rstrip("/") + "/")
        for origin in self._settings.cors_allow_origins:
            origin_str = str(origin).rstrip("/")
            uris.add(origin_str)
            uris.add(origin_str + "/")
        return " ".join(sorted(uris))

    async def _resolve_organization(
        self,
        client: httpx.AsyncClient,
        aap_url: str,
        auth: httpx.BasicAuth | None,
        org_name: str,
        extra_headers: dict[str, str] | None = None,
    ) -> int:
        """Resolve an AAP organization by name, returning its numeric ID."""
        url = f"{aap_url}{_AAP_API_PREFIX}/organizations/"
        data = await self._aap_get(client, url, auth, params={"name": org_name}, extra_headers=extra_headers)

        results = data.get("results", [])
        if not results:
            msg = (
                f"No organization named '{org_name}' found on AAP. "
                "Verify the organization name and that the admin account has permission to access it."
            )
            raise AAPSetupError(msg)

        try:
            return int(results[0]["id"])
        except (KeyError, TypeError, ValueError) as e:
            msg = f"Failed to parse organization '{org_name}' from AAP response"
            raise AAPSetupError(msg) from e

    async def _create_oauth2_app(
        self,
        client: httpx.AsyncClient,
        aap_url: str,
        auth: httpx.BasicAuth | None,
        redirect_uri: str,
        organization_id: int,
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[str, str]:
        """Create an OAuth2 application on AAP, returning (client_id, client_secret)."""
        url = f"{aap_url}{_AAP_API_PREFIX}/applications/"
        oauth2_app_name = self._settings.product_name
        body = {
            "name": oauth2_app_name,
            "description": f"OAuth2 application for {oauth2_app_name} OIDC integration",
            "client_type": "confidential",
            "authorization_grant_type": "authorization-code",
            "redirect_uris": redirect_uri,
            "post_logout_redirect_uris": self._build_post_logout_redirect_uris(),
            "organization": organization_id,
            "algorithm": "RS256",
            "skip_authorization": True,
            "app_url": self._settings.jwt_issuer,
        }

        data = await self._aap_post(client, url, auth, body, extra_headers=extra_headers)

        client_id = data.get("client_id")
        client_secret = data.get("client_secret")

        if not client_id or not client_secret:
            msg = "AAP did not return client credentials"
            raise AAPSetupError(msg)

        logger.info(
            "Created OAuth2 application on AAP",
            app_name=oauth2_app_name,
            aap_host=urlparse(aap_url).hostname,
        )

        return client_id, client_secret

    async def _aap_get(
        self,
        client: httpx.AsyncClient,
        url: str,
        auth: httpx.BasicAuth | None,
        params: dict[str, str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute authenticated GET against AAP."""
        response = await self._send_request(client, "GET", url, auth, params=params, extra_headers=extra_headers)
        self._raise_for_aap_status(response)
        return self._parse_json(response)

    async def _aap_post(
        self,
        client: httpx.AsyncClient,
        url: str,
        auth: httpx.BasicAuth | None,
        body: dict[str, Any],
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute authenticated POST against AAP."""
        response = await self._send_request(client, "POST", url, auth, json_body=body, extra_headers=extra_headers)
        self._raise_for_aap_status(response)
        return self._parse_json(response)

    @staticmethod
    async def _send_request(
        client: httpx.AsyncClient,
        method: str,
        url: str,
        auth: httpx.BasicAuth | None,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Send an HTTP request, mapping transport errors to domain exceptions."""
        try:
            return await client.request(
                method,
                url,
                auth=auth,
                params=params,
                json=json_body,
                headers=extra_headers,
            )
        except httpx.TimeoutException as e:
            msg = "AAP request timed out"
            raise AAPConnectionError(msg) from e
        except httpx.ConnectError as e:
            if _is_tls_verification_error(e):
                msg = (
                    "TLS certificate verification failed for AAP. "
                    "If the server uses a self-signed certificate, "
                    "select 'Disable TLS certificate verification' above and try again."
                )
            else:
                msg = "Cannot connect to AAP"
            raise AAPConnectionError(msg) from e
        except httpx.RequestError as e:
            msg = "AAP request failed"
            raise AAPConnectionError(msg) from e

    def _raise_for_aap_status(self, response: httpx.Response) -> None:
        """Check HTTP response status and raise domain errors for failures."""
        if response.status_code == HTTPStatus.UNAUTHORIZED:
            msg = "AAP authentication failed. Check your admin credentials."
            raise AAPAuthenticationError(msg)

        if response.status_code == HTTPStatus.FORBIDDEN:
            msg = "AAP authorization failed. The provided account does not have admin privileges."
            raise AAPAuthenticationError(msg)

        app_name = self._settings.product_name

        if response.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
            detail = _extract_aap_error_message(response, app_name=app_name)
            logger.error("AAP server error", status_code=response.status_code, detail=detail)
            msg = "AAP encountered an internal error"
            raise AAPConnectionError(msg)

        if response.status_code >= HTTPStatus.BAD_REQUEST:
            detail = _extract_aap_error_message(response, app_name=app_name)
            logger.warning("AAP request rejected", status_code=response.status_code, detail=detail)
            if "already exists" in detail:
                raise AAPSetupError(detail)
            msg = "AAP rejected the setup request"
            raise AAPSetupError(msg)

    @staticmethod
    def _parse_json(response: httpx.Response) -> dict[str, Any]:
        """Parse JSON response, raising on failure."""
        try:
            return response.json()  # type: ignore[no-any-return]
        except ValueError as e:
            msg = "AAP returned an invalid response"
            raise AAPSetupError(msg) from e
