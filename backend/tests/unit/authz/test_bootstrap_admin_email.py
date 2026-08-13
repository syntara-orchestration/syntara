"""Tests for bootstrap admin email seeding (AAP-87627)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.auth.exceptions import AdminModifyError
from syntara.authz.seed import (
    BOOTSTRAP_ADMIN_EMAIL,
    BOOTSTRAP_ADMIN_FIRST_NAME,
    BOOTSTRAP_ADMIN_USERNAME,
    _seed_assignments_and_admin,
)
from syntara.core.models import User
from syntara.users.services.user_service import UNSET, UsersService


class TestBootstrapAdminEmailConstants:
    def test_placeholder_email_is_example_dot_com(self) -> None:
        assert BOOTSTRAP_ADMIN_EMAIL == "admin@example.com"
        assert BOOTSTRAP_ADMIN_USERNAME == "admin"
        assert BOOTSTRAP_ADMIN_FIRST_NAME == "Administrator"


class TestGuardBuiltinUpdateEmail:
    def test_self_may_update_email(self) -> None:
        UsersService._guard_builtin_update(
            is_self=True,
            is_enabled=None,
            username=None,
            first_name=None,
            last_name=UNSET,
            email="ops@example.com",
            password=None,
        )

    def test_self_still_blocked_from_renaming(self) -> None:
        with pytest.raises(AdminModifyError):
            UsersService._guard_builtin_update(
                is_self=True,
                is_enabled=None,
                username=None,
                first_name="Nope",
                last_name=UNSET,
                email=None,
                password=None,
            )

    def test_non_self_cannot_update_email(self) -> None:
        with pytest.raises(AdminModifyError):
            UsersService._guard_builtin_update(
                is_self=False,
                is_enabled=None,
                username=None,
                first_name=None,
                last_name=UNSET,
                email="ops@example.com",
                password=None,
            )


@pytest.mark.asyncio
async def test_seed_backfills_null_admin_email() -> None:
    """Existing admin with email=NULL gets the placeholder on seed."""
    admin = User(
        id=uuid4(),
        username=BOOTSTRAP_ADMIN_USERNAME,
        first_name=BOOTSTRAP_ADMIN_FIRST_NAME,
        email=None,
        is_enabled=True,
        is_builtin=True,
    )
    auth_group = MagicMock()
    admin_group = MagicMock()
    auditors_group = MagicMock()
    users_group = MagicMock()
    default_project = MagicMock()
    default_project.id = uuid4()

    session = AsyncMock()
    session.exec = AsyncMock(return_value=MagicMock(one_or_none=MagicMock(return_value=admin)))
    session.get = AsyncMock(return_value=MagicMock())
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()

    with (
        patch("syntara.authz.seed._ensure_role_assignment", new_callable=AsyncMock),
        patch("syntara.authz.seed._ensure_group_membership", new_callable=AsyncMock),
    ):
        await _seed_assignments_and_admin(
            session, auth_group, admin_group, auditors_group, users_group, default_project
        )

    assert admin.email == BOOTSTRAP_ADMIN_EMAIL
