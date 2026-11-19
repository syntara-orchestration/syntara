"""Tests for bootstrap admin email seeding (AAP-87627)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from syntara.auth.exceptions import AdminModifyError
from syntara.authz.seed import (
    BOOTSTRAP_ADMIN_EMAIL,
    BOOTSTRAP_ADMIN_FIRST_NAME,
    BOOTSTRAP_ADMIN_USERNAME,
    _seed_assignments_and_admin,
    try_set_bootstrap_admin_email,
)
from syntara.core.models import User
from syntara.users.services.user_service import UNSET, UsersService


def _add_begin_nested(session: AsyncMock) -> None:
    """Configure begin_nested() as an async context manager on a mock session."""
    mock_nested = AsyncMock()
    mock_nested.__aenter__ = AsyncMock(return_value=None)
    mock_nested.__aexit__ = AsyncMock(return_value=None)
    session.begin_nested = MagicMock(return_value=mock_nested)


class TestBootstrapAdminEmailConstants:
    """Sanity checks for bootstrap admin placeholder constants."""

    def test_placeholder_email_is_example_dot_com(self) -> None:
        assert BOOTSTRAP_ADMIN_EMAIL == "admin@example.com"
        assert BOOTSTRAP_ADMIN_USERNAME == "admin"
        assert BOOTSTRAP_ADMIN_FIRST_NAME == "Administrator"


class TestGuardBuiltinUpdateEmail:
    """Builtin admin may replace email on self; name fields stay protected."""

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


def _mock_seed_session(*, admin: User | None) -> AsyncMock:
    session = AsyncMock()
    session.exec = AsyncMock(return_value=MagicMock(one_or_none=MagicMock(return_value=admin)))
    session.get = AsyncMock(return_value=MagicMock())
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    _add_begin_nested(session)
    return session


async def _run_seed(session: AsyncMock) -> None:
    auth_group = MagicMock()
    admin_group = MagicMock()
    auditors_group = MagicMock()
    users_group = MagicMock()
    default_project = MagicMock()
    default_project.id = uuid4()
    with (
        patch("syntara.authz.seed._ensure_role_assignment", new_callable=AsyncMock),
        patch("syntara.authz.seed._ensure_group_membership", new_callable=AsyncMock),
    ):
        await _seed_assignments_and_admin(
            session, auth_group, admin_group, auditors_group, users_group, default_project
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
    session = _mock_seed_session(admin=admin)
    await _run_seed(session)
    assert admin.email == BOOTSTRAP_ADMIN_EMAIL


@pytest.mark.asyncio
async def test_seed_preserves_existing_admin_email() -> None:
    """Seed must not overwrite a non-null admin email with the placeholder."""
    existing_email = "ops@example.com"
    admin = User(
        id=uuid4(),
        username=BOOTSTRAP_ADMIN_USERNAME,
        first_name=BOOTSTRAP_ADMIN_FIRST_NAME,
        email=existing_email,
        is_enabled=True,
        is_builtin=True,
    )
    session = _mock_seed_session(admin=admin)
    await _run_seed(session)
    assert admin.email == existing_email


@pytest.mark.asyncio
async def test_seed_resyncs_password_for_existing_admin_from_current_secret() -> None:
    """Redeploy must sync the admin password to the current secret file (AAP-89793).

    Reproduces the reported bug: when the admin user already exists in the
    database (e.g. left over from a prior failed deployment whose seeding
    ran before the deployment failed), seeding leaves its password_hash
    untouched even though a subsequent successful deployment's K8s secret
    contains a different password. The stored hash and the current secret
    then disagree and the operator cannot log in with the password from the
    K8s secret.
    """
    admin = User(
        id=uuid4(),
        username=BOOTSTRAP_ADMIN_USERNAME,
        first_name=BOOTSTRAP_ADMIN_FIRST_NAME,
        email="admin@example.com",
        is_enabled=True,
        is_builtin=True,
        password_hash="stale-hash-from-failed-deployment",
    )
    session = _mock_seed_session(admin=admin)

    current_secret_hash = "hash-of-current-deployments-secret"
    with patch("syntara.authz.seed._read_admin_password_hash", return_value=current_secret_hash):
        await _run_seed(session)

    assert admin.password_hash == current_secret_hash


@pytest.mark.asyncio
async def test_try_set_bootstrap_admin_email_skips_on_unique_conflict() -> None:
    """Taken placeholder email leaves admin.email unchanged and returns False."""
    admin = User(
        id=uuid4(),
        username=BOOTSTRAP_ADMIN_USERNAME,
        first_name=BOOTSTRAP_ADMIN_FIRST_NAME,
        email=None,
        is_enabled=True,
        is_builtin=True,
    )
    session = AsyncMock()
    session.flush = AsyncMock(side_effect=IntegrityError("ix_users_email_unique violated", None, BaseException()))
    _add_begin_nested(session)

    assigned = await try_set_bootstrap_admin_email(session, admin)

    assert assigned is False
    assert admin.email is None
