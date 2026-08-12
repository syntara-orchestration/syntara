"""Unit tests for global token revocation utilities and enforcement."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from syntara.auth.dependencies import get_current_user
from syntara.auth.exceptions import TokenGloballyRevokedError
from syntara.auth.models.global_revocation_timestamp import GlobalRevocationTimestamp
from syntara.auth.services.global_revocation import (
    _CACHE_TTL,
    clear_global_revocation_cache,
    get_global_revocation_timestamp,
    is_token_globally_revoked,
)
from syntara.auth.services.token_service import TokenPayload


def _make_payload(
    *,
    sub: str | None = None,
    iat: datetime | None = None,
) -> TokenPayload:
    now = datetime.now(UTC)
    return TokenPayload(
        sub=sub or str(uuid4()),
        iss="http://localhost:8000",
        iat=iat or now,
        exp=now + timedelta(minutes=15),
        token_type="access",  # noqa: S106
        preferred_username="testuser",
        email="test@example.com",
        groups=["eng"],
        amr=["pwd"],
        idp="local",
    )


def _mock_session(row: GlobalRevocationTimestamp | None) -> AsyncMock:
    """Build a mock AsyncSession that returns the given row from exec()."""
    mock_exec_result = MagicMock()
    mock_exec_result.one_or_none.return_value = row

    mock_session = AsyncMock()
    mock_session.exec = AsyncMock(return_value=mock_exec_result)
    return mock_session


# ---------------------------------------------------------------------------
# get_global_revocation_timestamp
# ---------------------------------------------------------------------------


class TestGetGlobalRevocationTimestamp:
    """Tests for get_global_revocation_timestamp."""

    def setup_method(self) -> None:
        clear_global_revocation_cache()

    @pytest.mark.asyncio
    async def test_returns_none_when_no_row(self) -> None:
        """Should return None when no row exists in the table."""
        result = await get_global_revocation_timestamp(_mock_session(None))
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_revoked_before_is_null(self) -> None:
        """Should return None when the row exists but revoked_before is NULL."""
        row = MagicMock(spec=GlobalRevocationTimestamp)
        row.revoked_before = None

        result = await get_global_revocation_timestamp(_mock_session(row))
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_datetime_when_set(self) -> None:
        """Should return the revocation timestamp when set."""
        ts = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        row = MagicMock(spec=GlobalRevocationTimestamp)
        row.revoked_before = ts

        result = await get_global_revocation_timestamp(_mock_session(row))

        assert result is not None
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 15


# ---------------------------------------------------------------------------
# is_token_globally_revoked
# ---------------------------------------------------------------------------


class TestIsTokenGloballyRevoked:
    """Tests for is_token_globally_revoked."""

    def setup_method(self) -> None:
        clear_global_revocation_cache()

    @pytest.mark.asyncio
    async def test_returns_none_when_iat_is_none(self) -> None:
        """Should return None when iat is None."""
        result = await is_token_globally_revoked(None, _mock_session(None))
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_revocation_timestamp(self) -> None:
        """Should return None when no revocation timestamp is configured."""
        result = await is_token_globally_revoked(datetime.now(UTC), _mock_session(None))
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_revocation_ts_when_iat_before_revocation(self) -> None:
        """Should return revocation timestamp when token was issued before it."""
        revocation_time = datetime.now(UTC)
        token_iat = revocation_time - timedelta(hours=1)

        row = MagicMock(spec=GlobalRevocationTimestamp)
        row.revoked_before = revocation_time

        result = await is_token_globally_revoked(token_iat, _mock_session(row))

        assert result is not None
        assert result == revocation_time

    @pytest.mark.asyncio
    async def test_returns_none_when_iat_after_revocation(self) -> None:
        """Should return None when token was issued after revocation timestamp."""
        revocation_time = datetime.now(UTC) - timedelta(hours=1)
        token_iat = datetime.now(UTC)

        row = MagicMock(spec=GlobalRevocationTimestamp)
        row.revoked_before = revocation_time

        result = await is_token_globally_revoked(token_iat, _mock_session(row))
        assert result is None

    @pytest.mark.asyncio
    async def test_rejects_token_issued_at_revocation_time(self) -> None:
        """Should reject token issued at exactly the revocation timestamp.

        The TTL-adjusted comparison (iat < revocation_ts + TTL) means tokens
        issued at revocation time fall within the staleness window.
        """
        revocation_time = datetime.now(UTC)

        row = MagicMock(spec=GlobalRevocationTimestamp)
        row.revoked_before = revocation_time

        result = await is_token_globally_revoked(revocation_time, _mock_session(row))
        assert result == revocation_time

    @pytest.mark.asyncio
    async def test_rejects_token_issued_within_ttl_window(self) -> None:
        """Should reject token issued within TTL seconds after revocation.

        Compensates for cache staleness: another node might still be serving
        the pre-revocation cached value.
        """
        revocation_time = datetime.now(UTC)
        token_iat = revocation_time + timedelta(seconds=_CACHE_TTL - 1)

        row = MagicMock(spec=GlobalRevocationTimestamp)
        row.revoked_before = revocation_time

        result = await is_token_globally_revoked(token_iat, _mock_session(row))
        assert result == revocation_time

    @pytest.mark.asyncio
    async def test_allows_token_issued_after_ttl_window(self) -> None:
        """Should allow token issued after revocation_ts + TTL."""
        revocation_time = datetime.now(UTC)
        token_iat = revocation_time + timedelta(seconds=_CACHE_TTL + 1)

        row = MagicMock(spec=GlobalRevocationTimestamp)
        row.revoked_before = revocation_time

        result = await is_token_globally_revoked(token_iat, _mock_session(row))
        assert result is None


# ---------------------------------------------------------------------------
# Thundering-herd protection
# ---------------------------------------------------------------------------


class TestThunderingHerdProtection:
    """Tests for asyncio.Lock-based thundering-herd prevention."""

    def setup_method(self) -> None:
        clear_global_revocation_cache()

    @pytest.mark.asyncio
    async def test_concurrent_misses_produce_single_db_query(self) -> None:
        """Multiple concurrent cache misses should result in only one DB query."""
        ts = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
        session = _mock_session(
            MagicMock(spec=GlobalRevocationTimestamp, revoked_before=ts),
        )

        results = await asyncio.gather(*[get_global_revocation_timestamp(session) for _ in range(10)])

        assert all(r == ts for r in results)
        assert session.exec.await_count == 1


# ---------------------------------------------------------------------------
# get_current_user with global revocation
# ---------------------------------------------------------------------------


class TestGetCurrentUserGlobalRevocation:
    """Tests for get_current_user global revocation enforcement."""

    def setup_method(self) -> None:
        clear_global_revocation_cache()

    @pytest.mark.asyncio
    async def test_raises_when_token_globally_revoked(self) -> None:
        """Should raise TokenGloballyRevokedError for pre-revocation tokens."""
        revocation_time = datetime.now(UTC)
        payload = _make_payload(iat=revocation_time - timedelta(hours=1))

        mock_token_service = MagicMock()
        mock_token_service.decode_token.return_value = payload

        row = MagicMock(spec=GlobalRevocationTimestamp)
        row.revoked_before = revocation_time

        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="old-jwt")
        request = MagicMock()
        db = _mock_session(row)

        with (
            patch("syntara.auth.dependencies._get_token_service", return_value=mock_token_service),
            patch("syntara.audit.dispatcher.AuditEventDispatcher.dispatch"),
            pytest.raises(TokenGloballyRevokedError),
        ):
            await get_current_user(request, db=db, credentials=credentials)

    @pytest.mark.asyncio
    async def test_allows_token_after_revocation(self) -> None:
        """Should allow tokens issued after the revocation timestamp."""
        revocation_time = datetime.now(UTC) - timedelta(hours=1)
        payload = _make_payload(iat=datetime.now(UTC))

        mock_token_service = MagicMock()
        mock_token_service.decode_token.return_value = payload

        row = MagicMock(spec=GlobalRevocationTimestamp)
        row.revoked_before = revocation_time

        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="new-jwt")
        request = MagicMock()
        db = _mock_session(row)

        with patch("syntara.auth.dependencies._get_token_service", return_value=mock_token_service):
            user = await get_current_user(request, db=db, credentials=credentials)

        assert user is not None
