"""AAP-83651: revoke_user_sessions must not clobber request actor ContextVars."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.admin.services import revoke_user_sessions
from syntara.audit.emitter import AuditActorContext, actor_context_var
from syntara.core.models.principal import PrincipalType
from syntara.core.models.user import User


@pytest.mark.asyncio
async def test_api_revoke_preserves_middleware_actor_id() -> None:
    """Authenticated API revoke must keep middleware actor_id for token_version CRUD."""
    target = User(
        id=uuid4(),
        username="target",
        first_name="T",
        last_name="U",
        is_enabled=True,
        password_hash="$argon2id$x",  # noqa: S106
    )
    api_actor_id = uuid4()
    token = actor_context_var.set(
        AuditActorContext(
            actor_id=api_actor_id,
            actor_username="admin-api",
            actor_type=PrincipalType.USER,
        )
    )
    mock_store = AsyncMock()
    mock_store.revoke_all_for_user.return_value = 1
    seen: AuditActorContext | None = None

    async def _capture(_uid: object) -> int:
        nonlocal seen
        seen = actor_context_var.get()
        return 2

    mock_store.increment_token_version.side_effect = _capture

    try:
        with (
            patch("syntara.admin.services.create_session_store", return_value=mock_store),
            patch("syntara.admin.services.AuditEventDispatcher.dispatch"),
        ):
            await revoke_user_sessions(
                AsyncMock(),
                target,
                actor_username="admin-api",
                actor_source="api",
            )
    finally:
        actor_context_var.reset(token)

    assert seen is not None
    assert seen.actor_id == api_actor_id
    assert seen.actor_username == "admin-api"


@pytest.mark.asyncio
async def test_cli_revoke_sets_username_when_no_middleware_actor() -> None:
    """CLI revoke with empty ContextVars still attributes token_version by username."""
    target = User(
        id=uuid4(),
        username="target",
        first_name="T",
        last_name="U",
        is_enabled=True,
        password_hash="$argon2id$x",  # noqa: S106
    )
    # Ensure no ambient actor
    clear = actor_context_var.set(None)
    mock_store = AsyncMock()
    mock_store.revoke_all_for_user.return_value = 0
    seen_username: str | None = None

    async def _capture(_uid: object) -> int:
        nonlocal seen_username
        actor = actor_context_var.get()
        seen_username = actor.actor_username if actor else None
        return 1

    mock_store.increment_token_version.side_effect = _capture

    try:
        with (
            patch("syntara.admin.services.create_session_store", return_value=mock_store),
            patch("syntara.admin.services.AuditEventDispatcher.dispatch"),
        ):
            await revoke_user_sessions(
                MagicMock(),
                target,
                actor_username="ops-cli",
                actor_source="cli",
            )
    finally:
        actor_context_var.reset(clear)

    assert seen_username == "ops-cli"
