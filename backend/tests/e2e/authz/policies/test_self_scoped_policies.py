"""Policy coverage: self-scoped policies (5 policies).

Self-scoped policies (user:read:self, user:update:self,
role-assignment:read:self, user_identity:read:self,
user_identity:detach:self) are granted to all authenticated users
via the ``authenticated`` built-in role.

The primary test coverage lives in ``test_baseline.py``. This file
adds supplementary checks for the user_identity self-scope policies.
"""

from __future__ import annotations

import os
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from orchestrator_test_sdk.factories import UserFactory
    from syntara_api_client.api import SyntaraApiRegistry

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)

from orchestrator_test_sdk.e2e.auth import api_for

pytestmark = [pytest.mark.e2e]


class TestUserIdentitySelfScope:
    """Verify user_identity self-scope policies."""

    def test_can_read_own_identities(
        self, syntara_base_url: str, admin_api: SyntaraApiRegistry, create_user: UserFactory
    ) -> None:
        user_id, username, password = create_user(admin_api, "uid-self")
        user_api = api_for(syntara_base_url, username, password)
        user_api.users.list_identities(user_id=user_id).assert_and_get()

    def test_cannot_read_other_identities(
        self, syntara_base_url: str, admin_api: SyntaraApiRegistry, create_user: UserFactory
    ) -> None:
        _, u1_name, u1_pass = create_user(admin_api, "uid-s1")
        u2_id, _, _ = create_user(admin_api, "uid-s2")
        u1_api = api_for(syntara_base_url, u1_name, u1_pass)
        resp = u1_api.users.list_identities(user_id=u2_id)
        assert resp.status_code == HTTPStatus.FORBIDDEN
