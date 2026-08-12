"""E2E tests for ANSTRAT-1844 session APIs (API-20).

Test Coverage:
- API-20: Concurrent session handling (login, refresh, logout)

See Also:
- test_session_revocation.py (API-37)
- test_session_revocation_idp.py (API-38, requires Keycloak)
- test_rp_initiated_logout.py (API-42-44, requires Keycloak)

Out of scope for REST E2E: API-39 (global revocation, CLI only). API-21 (IdP group
re-auth) — follow-up when Keycloak coverage is added.

Security Note:
SSL verification is intentionally disabled in these E2E tests as they run against
localhost or test environments with self-signed certificates. This is acceptable
for test code but should NEVER be used in production.

"""

from __future__ import annotations

from http import HTTPStatus

import pytest
from orchestrator_test_sdk.e2e.auth import (
    admin_password,
    assert_refresh_succeeds,
    assert_refresh_unauthorized,
    local_login_session,
    logout_with_session,
)
from orchestrator_test_sdk.e2e.tls import e2e_ssl_context
from syntara_api_client import AuthenticatedClient
from syntara_api_client.api.authentication.get_current_user import sync_detailed as get_user_sync

pytestmark = [pytest.mark.e2e]


class TestAPIConcurrentSessionHandling:
    """API-20: Verify multiple concurrent sessions are supported."""

    def test_concurrent_sessions_independent(
        self,
        syntara_base_url: str,
    ) -> None:
        """Multiple concurrent sessions must be valid simultaneously; revoking one leaves the other."""
        password = admin_password()
        token_a, cookies_a = local_login_session(syntara_base_url, "admin", password)
        token_b, cookies_b = local_login_session(syntara_base_url, "admin", password)

        assert token_a != token_b, "Expected different access tokens for concurrent sessions"
        assert cookies_a["ao_refresh_token"] != cookies_b["ao_refresh_token"]

        assert_refresh_succeeds(syntara_base_url, cookies_a)
        assert_refresh_succeeds(syntara_base_url, cookies_b)

        logout_resp = logout_with_session(syntara_base_url, token_a, cookies_a)
        assert logout_resp.status_code == HTTPStatus.OK

        assert_refresh_unauthorized(syntara_base_url, cookies_a)
        refreshed_b = assert_refresh_succeeds(syntara_base_url, cookies_b)

        user_b = get_user_sync(
            client=AuthenticatedClient(
                base_url=f"{syntara_base_url}/api/v1",
                token=refreshed_b.access_token,
                verify_ssl=e2e_ssl_context(),
            )
        )
        assert user_b.status_code == HTTPStatus.OK
