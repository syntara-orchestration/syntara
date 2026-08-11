"""AAP-83651: token_version CRUD audit must carry acting principal.

Security-critical ``token_version`` bumps must not emit database.trigger
``user_update`` CRUD events with null actor fields when an acting principal
is available in ContextVars.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import text

from syntara.audit.context_managers import actor_context
from syntara.auth.session.session_store import SessionStore
from syntara.core.models.user import User

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def _ensure_users_audit_metadata(test_db_session: AsyncSession) -> None:
    """Restore users audit metadata wiped by the integration DB template truncate.

    Triggers remain on the table after truncate; without a metadata row the
    trigger no-ops and no outbox event is written.
    """
    await test_db_session.exec(  # type: ignore[call-overload]
        text("""
            INSERT INTO audit_table_metadata (table_name, model_name, audit_level, auditable_fields)
            VALUES ('users', 'User', 'full', NULL)
            ON CONFLICT (table_name) DO NOTHING
        """)
    )
    await test_db_session.commit()


@pytest.fixture
async def target_user(test_db_session: AsyncSession) -> User:
    """User whose token_version will be mutated."""
    user = User(
        username=f"target-{uuid4().hex[:8]}",
        first_name="Target",
        last_name="User",
        is_enabled=True,
        password_hash="$argon2id$placeholder",  # noqa: S106
    )
    test_db_session.add(user)
    await test_db_session.commit()
    await test_db_session.refresh(user)
    return user


@pytest.fixture
async def acting_admin(test_db_session: AsyncSession) -> User:
    """Admin principal that should appear on the CRUD audit event."""
    user = User(
        username=f"admin-{uuid4().hex[:8]}",
        first_name="Acting",
        last_name="Admin",
        is_enabled=True,
        password_hash="$argon2id$placeholder",  # noqa: S106
    )
    test_db_session.add(user)
    await test_db_session.commit()
    await test_db_session.refresh(user)
    return user


async def _latest_token_version_user_update(
    session: AsyncSession,
    *,
    resource_id: str,
) -> dict[str, object]:
    """Return the newest user_update outbox payload that changed token_version."""
    result = await session.exec(  # type: ignore[call-overload]
        text(
            """
            SELECT event_payload
            FROM audit_outbox
            WHERE event_source = 'crud_event'
              AND event_payload->>'event_action' = 'user_update'
              AND event_payload->'structured_data'->>'resource_id' = :resource_id
              AND event_payload->'structured_data'->'changes' ? 'token_version'
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        params={"resource_id": resource_id},
    )
    row = result.first()
    assert row is not None, f"No crud user_update outbox row with changes.token_version for resource_id={resource_id}"
    payload = row[0]
    assert isinstance(payload, dict)
    return payload


@pytest.mark.asyncio
async def test_token_version_increment_crud_audit_carries_actor(
    test_db_session: AsyncSession,
    target_user: User,
    acting_admin: User,
) -> None:
    """Raw token_version bump must SET LOCAL actor vars so the trigger is attributed.

    Regression for AAP-83651: SessionStore.increment_token_version uses Core SQL
    that bypasses before_flush; without applying audit context first, actor_* on
    the database.trigger user_update event are null.
    """
    store = SessionStore(test_db_session)

    with actor_context(actor=acting_admin):
        await store.increment_token_version(target_user.id)
        await test_db_session.commit()

    payload = await _latest_token_version_user_update(
        test_db_session,
        resource_id=str(target_user.id),
    )

    assert payload["actor_id"] == str(acting_admin.id)
    assert payload["actor_username"] == acting_admin.username
    assert payload["actor_type"] == "user"
    assert payload["source_component"] == "database.trigger"


@pytest.mark.asyncio
async def test_last_login_update_crud_audit_carries_actor(
    test_db_session: AsyncSession,
    target_user: User,
) -> None:
    """last_login ORM update must carry the logging-in user as CRUD actor (AAP-83651)."""
    with actor_context(actor=target_user):
        target_user.update_last_login()
        test_db_session.add(target_user)
        await test_db_session.commit()

    result = await test_db_session.exec(  # type: ignore[call-overload]
        text(
            """
            SELECT event_payload
            FROM audit_outbox
            WHERE event_source = 'crud_event'
              AND event_payload->>'event_action' = 'user_update'
              AND event_payload->'structured_data'->>'resource_id' = :resource_id
              AND event_payload->'structured_data'->'changes' ? 'last_login'
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        params={"resource_id": str(target_user.id)},
    )
    row = result.first()
    assert row is not None, "No last_login user_update CRUD outbox row"
    payload = row[0]
    assert payload["actor_id"] == str(target_user.id)
    assert payload["actor_username"] == target_user.username
    assert payload["actor_type"] == "user"
