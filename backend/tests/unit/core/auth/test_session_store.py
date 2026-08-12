"""Unit tests for SessionStore (PostgreSQL-backed).

Tests cover:
- Session creation with all optional fields
- Session retrieval (active, revoked, expired)
- Session retrieval with token version (JOIN query)
- Single session revocation (active, already-revoked)
- Bulk revocation by user, IDP, and identity
- Token version increment and retrieval
- Listing active sessions for a user
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.auth.session.models import RefreshSession
from syntara.auth.session.session_store import SessionInfo, SessionStore


def _mock_settings() -> MagicMock:
    mock = MagicMock()
    mock.jwt_refresh_token_lifetime_hours = 8
    return mock


def _make_refresh_session(
    *,
    jti: str = "test-jti",
    user_id=None,
    issued_at=None,
    expires_at=None,
    revoked_at=None,
    device: str | None = "test-agent",
    ip_address: str | None = "127.0.0.1",
    amr=None,
    idp: str | None = None,
    idp_id: str | None = None,
    identity_id: str | None = None,
    issuer: str | None = None,
    subject: str | None = None,
    id_token_hint: str | None = None,
    rp_logout_enabled: bool = False,
) -> RefreshSession:
    """Build a RefreshSession row for testing."""
    now = datetime.now(UTC)
    if user_id is None:
        user_id = uuid4()
    if issued_at is None:
        issued_at = now - timedelta(minutes=5)
    if expires_at is None:
        expires_at = now + timedelta(hours=8)
    return RefreshSession(
        jti=jti,
        user_id=user_id,
        issued_at=issued_at,
        expires_at=expires_at,
        revoked_at=revoked_at,
        device=device,
        ip_address=ip_address,
        amr=amr or ["pwd"],
        idp=idp,
        idp_id=idp_id,
        identity_id=identity_id,
        issuer=issuer,
        subject=subject,
        id_token_hint=id_token_hint,
        rp_logout_enabled=rp_logout_enabled,
    )


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def store(mock_db: AsyncMock) -> SessionStore:
    with patch("syntara.auth.session.session_store.get_settings", return_value=_mock_settings()):
        return SessionStore(mock_db)


class TestCreate:
    """Tests for SessionStore.create."""

    @pytest.mark.asyncio
    async def test_creates_session_with_defaults(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should add a RefreshSession to the db and flush."""
        user_id = uuid4()

        await store.create(jti="jti-1", user_id=user_id)

        mock_db.add.assert_called_once()
        session_arg = mock_db.add.call_args[0][0]
        assert isinstance(session_arg, RefreshSession)
        assert session_arg.jti == "jti-1"
        assert session_arg.user_id == user_id
        assert session_arg.revoked_at is None
        mock_db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_creates_session_with_all_fields(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should persist all optional fields."""
        user_id = uuid4()

        await store.create(
            jti="jti-full",
            user_id=user_id,
            device="Firefox",
            ip_address="10.0.0.1",
            ttl_seconds=3600,
            amr=["fed"],
            idp="Azure",
            idp_id="provider-uuid",
            identity_id="identity-uuid",
            issuer="https://login.example.com",
            subject="sub-123",
            id_token_hint="eyJhbGci...",  # noqa: S106
            rp_logout_enabled=True,
        )

        session_arg = mock_db.add.call_args[0][0]
        assert session_arg.device == "Firefox"
        assert session_arg.ip_address == "10.0.0.1"
        assert session_arg.amr == ["fed"]
        assert session_arg.idp == "Azure"
        assert session_arg.idp_id == "provider-uuid"
        assert session_arg.identity_id == "identity-uuid"
        assert session_arg.issuer == "https://login.example.com"
        assert session_arg.subject == "sub-123"
        assert session_arg.id_token_hint == "eyJhbGci..."  # noqa: S105
        assert session_arg.rp_logout_enabled is True

    @pytest.mark.asyncio
    async def test_uses_default_ttl_from_settings(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should compute expires_at from settings when ttl_seconds is None."""
        await store.create(jti="jti-default-ttl", user_id=uuid4())

        session_arg = mock_db.add.call_args[0][0]
        expected_ttl = 8 * 3600  # jwt_refresh_token_lifetime_hours = 8
        actual_ttl = (session_arg.expires_at - session_arg.issued_at).total_seconds()
        assert actual_ttl == pytest.approx(expected_ttl, abs=1)

    @pytest.mark.asyncio
    async def test_uses_custom_ttl(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should use provided ttl_seconds for expires_at."""
        await store.create(jti="jti-custom-ttl", user_id=uuid4(), ttl_seconds=1800)

        session_arg = mock_db.add.call_args[0][0]
        actual_ttl = (session_arg.expires_at - session_arg.issued_at).total_seconds()
        assert actual_ttl == pytest.approx(1800, abs=1)


class TestGet:
    """Tests for SessionStore.get."""

    @pytest.mark.asyncio
    async def test_returns_session_info_when_found(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should return SessionInfo for an active, non-revoked session."""
        row = _make_refresh_session(jti="active-jti", idp="Azure")
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = row
        mock_db.exec.return_value = mock_result

        result = await store.get("active-jti")

        assert result is not None
        assert isinstance(result, SessionInfo)
        assert result.jti == "active-jti"
        assert result.user_id == str(row.user_id)
        assert result.idp == "Azure"
        assert result.ttl > 0
        mock_db.exec.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should return None when no matching session exists."""
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_db.exec.return_value = mock_result

        result = await store.get("missing-jti")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_revoked_session(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should return None because the SQL query filters out revoked sessions."""
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_db.exec.return_value = mock_result

        result = await store.get("revoked-jti")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_expired_session(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should return None because the SQL query filters out expired sessions."""
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_db.exec.return_value = mock_result

        result = await store.get("expired-jti")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_rp_logout_enabled(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should include rp_logout_enabled in returned SessionInfo."""
        row = _make_refresh_session(rp_logout_enabled=True)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = row
        mock_db.exec.return_value = mock_result

        result = await store.get("test-jti")

        assert result is not None
        assert result.rp_logout_enabled is True

    @pytest.mark.asyncio
    async def test_computes_ttl_from_expires_at(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should compute TTL as seconds remaining until expires_at."""
        now = datetime.now(UTC)
        row = _make_refresh_session(expires_at=now + timedelta(seconds=7200))
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = row
        mock_db.exec.return_value = mock_result

        result = await store.get("test-jti")

        assert result is not None
        assert 7100 < result.ttl <= 7200


class TestGetWithTokenVersion:
    """Tests for SessionStore.get_with_token_version."""

    @pytest.mark.asyncio
    async def test_returns_session_and_version(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should return (SessionInfo, token_version) for active session."""
        row = _make_refresh_session(jti="versioned-jti", device="Chrome", ip_address="10.0.0.5", idp="local")
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = (row, 3)
        mock_db.exec.return_value = mock_result

        result = await store.get_with_token_version("versioned-jti")

        assert result is not None
        info, version = result
        assert isinstance(info, SessionInfo)
        assert info.jti == "versioned-jti"
        assert info.user_id == str(row.user_id)
        assert info.device == "Chrome"
        assert version == 3
        mock_db.exec.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should return None when session does not exist or is revoked/expired."""
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_db.exec.return_value = mock_result

        result = await store.get_with_token_version("missing-jti")

        assert result is None

    @pytest.mark.asyncio
    async def test_computes_ttl_correctly(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should compute TTL from expires_at for the returned SessionInfo."""
        now = datetime.now(UTC)
        row = _make_refresh_session(jti="ttl-jti", expires_at=now + timedelta(seconds=5000))
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = (row, 0)
        mock_db.exec.return_value = mock_result

        result = await store.get_with_token_version("ttl-jti")

        assert result is not None
        info, _ = result
        assert 4900 < info.ttl <= 5000


class TestRevoke:
    """Tests for SessionStore.revoke (soft-revoke)."""

    @pytest.mark.asyncio
    async def test_returns_true_when_revoked(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should return True when an active session is soft-revoked."""
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.exec.return_value = mock_result

        result = await store.revoke("active-jti")

        assert result is True
        mock_db.exec.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_already_revoked(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should return False when session was already revoked (rowcount=0)."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.exec.return_value = mock_result

        result = await store.revoke("already-revoked-jti")

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should return False when no session exists with the given JTI."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.exec.return_value = mock_result

        result = await store.revoke("nonexistent-jti")

        assert result is False


class TestRevokeAllForUser:
    """Tests for SessionStore.revoke_all_for_user."""

    @pytest.mark.asyncio
    async def test_returns_count_of_revoked_sessions(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should return the number of sessions revoked."""
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_db.exec.return_value = mock_result

        count = await store.revoke_all_for_user(uuid4())

        assert count == 3

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_sessions(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should return 0 when user has no active sessions."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.exec.return_value = mock_result

        count = await store.revoke_all_for_user(uuid4())

        assert count == 0

    @pytest.mark.asyncio
    async def test_accepts_string_user_id(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should accept user_id as a string and convert to UUID."""
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.exec.return_value = mock_result

        user_id = uuid4()
        count = await store.revoke_all_for_user(str(user_id))

        assert count == 1


class TestRevokeByIdp:
    """Tests for SessionStore.revoke_by_idp."""

    @pytest.mark.asyncio
    async def test_returns_count_of_revoked_sessions(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should return the number of sessions revoked for the IDP."""
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_db.exec.return_value = mock_result

        count = await store.revoke_by_idp("provider-uuid-456")

        assert count == 5

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_sessions(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should return 0 when IDP has no active sessions."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.exec.return_value = mock_result

        count = await store.revoke_by_idp("unknown-provider")

        assert count == 0


class TestRevokeByIdentity:
    """Tests for SessionStore.revoke_by_identity."""

    @pytest.mark.asyncio
    async def test_returns_count_of_revoked_sessions(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should return the number of sessions revoked for the identity."""
        mock_result = MagicMock()
        mock_result.rowcount = 2
        mock_db.exec.return_value = mock_result

        count = await store.revoke_by_identity("identity-uuid-123")

        assert count == 2

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_sessions(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should return 0 when identity has no active sessions."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.exec.return_value = mock_result

        count = await store.revoke_by_identity("unknown-identity")

        assert count == 0

    @pytest.mark.asyncio
    async def test_accepts_uuid_identity_id(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should accept identity_id as a UUID and convert to string."""
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.exec.return_value = mock_result

        count = await store.revoke_by_identity(uuid4())

        assert count == 1


class TestIncrementTokenVersion:
    """Tests for SessionStore.increment_token_version."""

    @pytest.mark.asyncio
    async def test_returns_new_version(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should return the incremented token version."""
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = (4,)
        mock_db.exec.return_value = mock_result

        version = await store.increment_token_version(uuid4())

        assert version == 4
        mock_db.exec.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_zero_when_user_not_found(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should return 0 when user does not exist."""
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_db.exec.return_value = mock_result

        version = await store.increment_token_version(uuid4())

        assert version == 0


class TestGetTokenVersion:
    """Tests for SessionStore.get_token_version."""

    @pytest.mark.asyncio
    async def test_returns_current_version(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should return the current token version for the user."""
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = (7,)
        mock_db.exec.return_value = mock_result

        version = await store.get_token_version(uuid4())

        assert version == 7

    @pytest.mark.asyncio
    async def test_returns_zero_when_user_not_found(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should return 0 when user does not exist."""
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_db.exec.return_value = mock_result

        version = await store.get_token_version(uuid4())

        assert version == 0


class TestListUserSessions:
    """Tests for SessionStore.list_user_sessions."""

    @pytest.mark.asyncio
    async def test_returns_sessions_for_user(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should return a list of SessionInfo for the user's active sessions."""
        user_id = uuid4()
        rows = [
            _make_refresh_session(jti="jti-1", user_id=user_id, device="Chrome"),
            _make_refresh_session(jti="jti-2", user_id=user_id, device="Firefox"),
        ]
        mock_result = MagicMock()
        mock_result.all.return_value = rows
        mock_db.exec.return_value = mock_result

        sessions = await store.list_user_sessions(user_id)

        assert len(sessions) == 2
        assert all(isinstance(s, SessionInfo) for s in sessions)
        assert sessions[0].jti == "jti-1"
        assert sessions[1].jti == "jti-2"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_sessions(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should return empty list when user has no active sessions."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.exec.return_value = mock_result

        sessions = await store.list_user_sessions(uuid4())

        assert sessions == []

    @pytest.mark.asyncio
    async def test_accepts_string_user_id(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should accept user_id as a string."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.exec.return_value = mock_result

        user_id = uuid4()
        sessions = await store.list_user_sessions(str(user_id))

        assert sessions == []
        mock_db.exec.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_session_info_fields_are_populated(self, store: SessionStore, mock_db: AsyncMock) -> None:
        """Should populate all SessionInfo fields from the database row."""
        user_id = uuid4()
        row = _make_refresh_session(
            jti="full-jti",
            user_id=user_id,
            device="Safari",
            ip_address="192.168.1.1",
            amr=["fed", "mfa"],
            idp="Okta",
            idp_id="okta-uuid",
            identity_id="ident-uuid",
            issuer="https://okta.example.com",
            subject="sub-456",
            id_token_hint="hint-token",  # noqa: S106
            rp_logout_enabled=True,
        )
        mock_result = MagicMock()
        mock_result.all.return_value = [row]
        mock_db.exec.return_value = mock_result

        sessions = await store.list_user_sessions(user_id)

        assert len(sessions) == 1
        s = sessions[0]
        assert s.jti == "full-jti"
        assert s.user_id == str(user_id)
        assert s.device == "Safari"
        assert s.ip_address == "192.168.1.1"
        assert s.amr == ["fed", "mfa"]
        assert s.idp == "Okta"
        assert s.idp_id == "okta-uuid"
        assert s.identity_id == "ident-uuid"
        assert s.issuer == "https://okta.example.com"
        assert s.subject == "sub-456"
        assert s.id_token_hint == "hint-token"  # noqa: S105
        assert s.rp_logout_enabled is True
        assert s.ttl > 0
