"""OIDC discovery service for testing identity provider connections."""

from pydantic import BaseModel

from syntara.auth.services.oidc_service import OIDCError, OIDCService

CLAIM_ALIASES: dict[str, list[str]] = {
    "sub": ["sub"],
    "email": ["email", "mail", "upn", "emailaddress"],
    "username": ["preferred_username", "login", "uid", "sAMAccountName", "upn"],
    "first_name": ["given_name", "givenName", "first_name", "firstName", "name", "displayName"],
    "last_name": ["family_name", "familyName", "last_name", "lastName", "sn", "surname"],
}


class OIDCTestResult(BaseModel):
    """Result of an OIDC connection test."""

    success: bool
    message: str
    metadata: dict[str, str] | None = None
    claims_supported: list[str] | None = None
    claim_aliases: dict[str, list[str]] | None = None
    end_session_endpoint_supported: bool = False


async def test_oidc_connection(issuer_url: str, *, disable_tls_verify: bool = False) -> OIDCTestResult:  # noqa: PT028
    """Test OIDC connection by fetching the well-known configuration.

    Delegates to OIDCService.fetch_discovery_config to avoid duplicating
    the discovery fetch/validation logic.

    Args:
        issuer_url: The OIDC issuer URL to test
        disable_tls_verify: Skip TLS certificate verification (insecure)

    Returns:
        OIDCTestResult with success status, message, and discovered metadata

    """
    try:
        oidc_service = OIDCService()
        data = await oidc_service.fetch_discovery_config(issuer_url, disable_tls_verify=disable_tls_verify)

        return OIDCTestResult(
            success=True,
            message="OIDC discovery successful",
            metadata={
                "authorization_endpoint": data["authorization_endpoint"],
                "token_endpoint": data["token_endpoint"],
                "issuer": data["issuer"],
                "jwks_uri": data["jwks_uri"],
            },
            claims_supported=data.get("claims_supported"),
            claim_aliases=CLAIM_ALIASES,
            end_session_endpoint_supported="end_session_endpoint" in data,
        )

    except OIDCError as e:
        return OIDCTestResult(
            success=False,
            message=str(e),
        )
    except Exception as e:  # noqa: BLE001
        return OIDCTestResult(
            success=False,
            message=f"Unexpected error: {e}",
        )
