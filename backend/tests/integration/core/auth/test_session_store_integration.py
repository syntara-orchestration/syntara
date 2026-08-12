"""Integration tests for SessionStore with real PostgreSQL instance.

These tests require a running PostgreSQL instance (configured via environment variables).
They test real interactions including:
- Session creation with TTL
- Session retrieval with metadata
- Session revocation
- Bulk revocation for a user
- Listing user sessions
- Token version tracking
"""

import asyncio
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth.session.session_store import SessionStore
from syntara.core.models import User

pytestmark = pytest.mark.integration


@pytest.fixture
async def test_user(test_db_session: AsyncSession) -> User:
    """Create a real user in the database for FK-constrained session tests."""
    user = User(
        username=f"test-{uuid4().hex[:8]}",
        first_name="Test",
        last_name="User",
        is_enabled=True,
        password_hash="$argon2id$placeholder",  # noqa: S106
    )
    test_db_session.add(user)
    await test_db_session.flush()
    return user


@pytest.fixture
async def second_user(test_db_session: AsyncSession) -> User:
    """Create a second user for multi-user tests."""
    user = User(
        username=f"test-{uuid4().hex[:8]}",
        first_name="Second",
        last_name="User",
        is_enabled=True,
        password_hash="$argon2id$placeholder",  # noqa: S106
    )
    test_db_session.add(user)
    await test_db_session.flush()
    return user


class TestSessionCreate:
    """Tests for session creation."""

    @pytest.mark.asyncio
    async def test_create_stores_session(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Creating a session should store it in PostgreSQL."""
        jti = f"test-{uuid4()}"

        store = SessionStore(test_db_session)
        await store.create(
            jti=jti,
            user_id=test_user.id,
            device="pytest-agent",
            ip_address="127.0.0.1",
        )
        session = await store.get(jti)

        assert session is not None
        assert session.jti == jti
        assert session.user_id == str(test_user.id)
        assert session.device == "pytest-agent"
        assert session.ip_address == "127.0.0.1"

    @pytest.mark.asyncio
    async def test_create_with_custom_ttl(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Session should respect custom TTL."""
        jti = f"test-{uuid4()}"

        store = SessionStore(test_db_session)
        await store.create(
            jti=jti,
            user_id=test_user.id,
            ttl_seconds=60,
        )
        session = await store.get(jti)

        assert session is not None
        assert 0 < session.ttl <= 60

    @pytest.mark.asyncio
    async def test_create_without_optional_fields(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Session can be created without device and ip_address."""
        jti = f"test-{uuid4()}"

        store = SessionStore(test_db_session)
        await store.create(jti=jti, user_id=test_user.id)
        session = await store.get(jti)

        assert session is not None
        assert session.device is None
        assert session.ip_address is None


class TestSessionGet:
    """Tests for session retrieval."""

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, test_db_session: AsyncSession) -> None:
        """Getting a nonexistent session should return None."""
        store = SessionStore(test_db_session)
        session = await store.get("nonexistent-jti")

        assert session is None

    @pytest.mark.asyncio
    async def test_get_returns_correct_metadata(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Retrieved session should contain all stored metadata."""
        jti = f"test-{uuid4()}"

        store = SessionStore(test_db_session)
        await store.create(
            jti=jti,
            user_id=test_user.id,
            device="Chrome/120",
            ip_address="10.0.0.1",
            ttl_seconds=3600,
        )
        session = await store.get(jti)

        assert session is not None
        assert session.jti == jti
        assert session.user_id == str(test_user.id)
        assert session.device == "Chrome/120"
        assert session.ip_address == "10.0.0.1"
        assert session.issued_at is not None
        assert session.ttl > 0

    @pytest.mark.asyncio
    async def test_get_expired_session_returns_none(self, test_db_session: AsyncSession, test_user: User) -> None:
        """A session with a very short TTL should expire and return None."""
        jti = f"test-{uuid4()}"

        store = SessionStore(test_db_session)
        await store.create(jti=jti, user_id=test_user.id, ttl_seconds=1)
        await asyncio.sleep(1.5)
        session = await store.get(jti)

        assert session is None


class TestSessionRevoke:
    """Tests for session revocation."""

    @pytest.mark.asyncio
    async def test_revoke_existing_returns_true(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Revoking an existing session should return True."""
        jti = f"test-{uuid4()}"

        store = SessionStore(test_db_session)
        await store.create(jti=jti, user_id=test_user.id, ttl_seconds=300)
        result = await store.revoke(jti)

        assert result is True

    @pytest.mark.asyncio
    async def test_revoke_removes_session(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Revoked session should no longer be retrievable."""
        jti = f"test-{uuid4()}"

        store = SessionStore(test_db_session)
        await store.create(jti=jti, user_id=test_user.id, ttl_seconds=300)
        await store.revoke(jti)
        session = await store.get(jti)

        assert session is None

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_returns_false(self, test_db_session: AsyncSession) -> None:
        """Revoking a nonexistent session should return False."""
        store = SessionStore(test_db_session)
        result = await store.revoke("nonexistent-jti")

        assert result is False

    @pytest.mark.asyncio
    async def test_revoke_idempotent(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Revoking the same session twice should return False the second time."""
        jti = f"test-{uuid4()}"

        store = SessionStore(test_db_session)
        await store.create(jti=jti, user_id=test_user.id, ttl_seconds=300)
        first = await store.revoke(jti)
        second = await store.revoke(jti)

        assert first is True
        assert second is False


class TestRevokeAllForUser:
    """Tests for bulk user session revocation."""

    @pytest.mark.asyncio
    async def test_revokes_all_sessions_for_user(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Should revoke all sessions belonging to a specific user."""
        store = SessionStore(test_db_session)
        await store.create(jti=f"test-{uuid4()}", user_id=test_user.id, ttl_seconds=300)
        await store.create(jti=f"test-{uuid4()}", user_id=test_user.id, ttl_seconds=300)
        await store.create(jti=f"test-{uuid4()}", user_id=test_user.id, ttl_seconds=300)

        count = await store.revoke_all_for_user(test_user.id)

        assert count == 3

    @pytest.mark.asyncio
    async def test_does_not_revoke_other_users_sessions(
        self, test_db_session: AsyncSession, test_user: User, second_user: User
    ) -> None:
        """Should not revoke sessions belonging to other users."""
        jti_b = f"test-{uuid4()}"

        store = SessionStore(test_db_session)
        await store.create(jti=f"test-{uuid4()}", user_id=test_user.id, ttl_seconds=300)
        await store.create(jti=jti_b, user_id=second_user.id, ttl_seconds=300)

        await store.revoke_all_for_user(test_user.id)

        session_b = await store.get(jti_b)

        assert session_b is not None
        assert session_b.user_id == str(second_user.id)

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_sessions(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Should return 0 when user has no sessions."""
        store = SessionStore(test_db_session)
        count = await store.revoke_all_for_user(test_user.id)

        assert count == 0


class TestListUserSessions:
    """Tests for listing user sessions."""

    @pytest.mark.asyncio
    async def test_lists_all_sessions_for_user(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Should return all active sessions for a user."""
        store = SessionStore(test_db_session)
        await store.create(jti=f"test-{uuid4()}", user_id=test_user.id, device="Chrome", ttl_seconds=300)
        await store.create(jti=f"test-{uuid4()}", user_id=test_user.id, device="Firefox", ttl_seconds=300)

        sessions = await store.list_user_sessions(test_user.id)

        assert len(sessions) == 2
        devices = {s.device for s in sessions}
        assert devices == {"Chrome", "Firefox"}

    @pytest.mark.asyncio
    async def test_does_not_include_other_users(
        self, test_db_session: AsyncSession, test_user: User, second_user: User
    ) -> None:
        """Should only return sessions for the requested user."""
        store = SessionStore(test_db_session)
        await store.create(jti=f"test-{uuid4()}", user_id=test_user.id, ttl_seconds=300)
        await store.create(jti=f"test-{uuid4()}", user_id=second_user.id, ttl_seconds=300)

        sessions = await store.list_user_sessions(test_user.id)

        assert len(sessions) == 1
        assert sessions[0].user_id == str(test_user.id)

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_sessions(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Should return empty list when user has no sessions."""
        store = SessionStore(test_db_session)
        sessions = await store.list_user_sessions(test_user.id)

        assert sessions == []


class TestGetWithTokenVersion:
    """Tests for get_with_token_version JOIN query."""

    @pytest.mark.asyncio
    async def test_returns_session_and_version(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Should return session info and token version in a single query."""
        jti = f"test-{uuid4()}"
        store = SessionStore(test_db_session)
        await store.create(jti=jti, user_id=test_user.id, device="Chrome", ttl_seconds=300)
        await store.increment_token_version(test_user.id)
        await store.increment_token_version(test_user.id)

        result = await store.get_with_token_version(jti)

        assert result is not None
        session_info, version = result
        assert session_info.jti == jti
        assert session_info.user_id == str(test_user.id)
        assert session_info.device == "Chrome"
        assert version == 2

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent(self, test_db_session: AsyncSession) -> None:
        """Should return None for a nonexistent session."""
        store = SessionStore(test_db_session)
        result = await store.get_with_token_version("nonexistent-jti")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_revoked(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Should return None for a revoked session."""
        jti = f"test-{uuid4()}"
        store = SessionStore(test_db_session)
        await store.create(jti=jti, user_id=test_user.id, ttl_seconds=300)
        await store.revoke(jti)

        result = await store.get_with_token_version(jti)

        assert result is None


class TestTokenVersion:
    """Tests for token version tracking."""

    @pytest.mark.asyncio
    async def test_increment_returns_increasing_values(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Each increment should return a higher version number."""
        store = SessionStore(test_db_session)
        v1 = await store.increment_token_version(test_user.id)
        v2 = await store.increment_token_version(test_user.id)
        v3 = await store.increment_token_version(test_user.id)

        assert v1 == 1
        assert v2 == 2
        assert v3 == 3

    @pytest.mark.asyncio
    async def test_get_version_returns_current(self, test_db_session: AsyncSession, test_user: User) -> None:
        """get_token_version should return the current version."""
        store = SessionStore(test_db_session)
        await store.increment_token_version(test_user.id)
        await store.increment_token_version(test_user.id)

        version = await store.get_token_version(test_user.id)

        assert version == 2

    @pytest.mark.asyncio
    async def test_get_version_returns_zero_for_new_user(self, test_db_session: AsyncSession, test_user: User) -> None:
        """get_token_version should return 0 for a user with no increments."""
        store = SessionStore(test_db_session)
        version = await store.get_token_version(test_user.id)

        assert version == 0


class TestSessionStoreInstantiation:
    """Tests for SessionStore instantiation."""

    def test_instantiation_with_db_session(self, test_db_session: AsyncSession) -> None:
        """SessionStore should accept a database session."""
        store = SessionStore(test_db_session)
        assert store._db is test_db_session

    @pytest.mark.asyncio
    async def test_operations_work_across_store_reuse(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Multiple SessionStore instances with same session should see same data."""
        jti = f"test-{uuid4()}"

        store1 = SessionStore(test_db_session)
        await store1.create(jti=jti, user_id=test_user.id, ttl_seconds=300)

        store2 = SessionStore(test_db_session)
        session = await store2.get(jti)

        assert session is not None
        assert session.user_id == str(test_user.id)
