"""E2E tests for user-scoped session revocation (ANSTRAT-1844, API-37).

All assertions use public REST APIs (``syntara_api_client`` and ``/api/v1/auth/*``).
No admin CLI, subprocess, or direct calls into application Python modules.

API mapping:
- API-37: ``PATCH /users/{user_id}`` with ``is_enabled=false`` or ``password`` (revokes all user sessions)
- API-38: ``test_session_revocation_idp.py`` (``DELETE /identity_providers/{provider_id}``)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from orchestrator_test_sdk.e2e import generate_test_password
from orchestrator_test_sdk.e2e.auth import (
    assert_refresh_succeeds,
    assert_refresh_unauthorized,
    local_login_session,
)
from syntara_api_client.models.user_update import UserUpdate

if TYPE_CHECKING:
    from collections.abc import Callable

    from syntara_api_client.api import SyntaraApiRegistry
    from syntara_api_client.models.user_read import UserRead

pytestmark = [pytest.mark.e2e]


class TestAPIUserScopedSessionRevocation:
    """API-37: Revoking all sessions for one user does not affect other users."""

    def test_disable_user_revokes_all_sessions(
        self,
        syntara_api: SyntaraApiRegistry,
        nexus_base_url: str,
        local_user_factory: Callable[..., tuple[UserRead, str]],
    ) -> None:
        """PATCH user with is_enabled=false must invalidate every refresh session for that user."""
        user, password = local_user_factory(first_name="Revoke", last_name="Target")
        other_user, other_password = local_user_factory(first_name="Other", last_name="User")

        _, cookies_a1 = local_login_session(nexus_base_url, user.username, password)
        _, cookies_a2 = local_login_session(nexus_base_url, user.username, password)
        _, cookies_other = local_login_session(nexus_base_url, other_user.username, other_password)

        assert_refresh_succeeds(nexus_base_url, cookies_a1)
        assert_refresh_succeeds(nexus_base_url, cookies_a2)

        syntara_api.users.update(
            user_id=user.id,
            body=UserUpdate(is_enabled=False),
        ).assert_and_get()

        assert_refresh_unauthorized(nexus_base_url, cookies_a1)
        assert_refresh_unauthorized(nexus_base_url, cookies_a2)
        assert_refresh_succeeds(nexus_base_url, cookies_other)

    def test_password_change_revokes_all_sessions(
        self,
        syntara_api: SyntaraApiRegistry,
        nexus_base_url: str,
        local_user_factory: Callable[..., tuple[UserRead, str]],
    ) -> None:
        """PATCH user with a new password must invalidate existing refresh sessions."""
        user, password = local_user_factory(first_name="Password", last_name="Revoke Target")
        new_password = generate_test_password()

        _, cookies_before = local_login_session(nexus_base_url, user.username, password)
        assert_refresh_succeeds(nexus_base_url, cookies_before)

        syntara_api.users.update(
            user_id=user.id,
            body=UserUpdate(password=new_password),
        ).assert_and_get()

        assert_refresh_unauthorized(nexus_base_url, cookies_before)

        _, cookies_after = local_login_session(nexus_base_url, user.username, new_password)
        assert_refresh_succeeds(nexus_base_url, cookies_after)
