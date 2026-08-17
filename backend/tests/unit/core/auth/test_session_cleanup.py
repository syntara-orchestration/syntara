"""Tests for the session cleanup worker."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.auth.session.cleanup import cleanup_expired_sessions


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def mock_session_factory(mock_session):
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory


class TestCleanupExpiredSessions:
    """Tests for cleanup_expired_sessions callback."""

    @pytest.mark.asyncio
    async def test_deletes_expired_sessions(self, mock_session_factory, mock_session):
        """Both passes run; first pass finds rows, second pass (revoked) finds none."""
        result_expired = MagicMock(rowcount=5)
        result_expired_done = MagicMock(rowcount=0)
        result_revoked_done = MagicMock(rowcount=0)
        mock_session.exec = AsyncMock(
            side_effect=[result_expired, result_expired_done, result_revoked_done],
        )

        await cleanup_expired_sessions(mock_session_factory)

        assert mock_session.commit.await_count == 1

    @pytest.mark.asyncio
    async def test_no_expired_sessions(self, mock_session_factory, mock_session):
        result = MagicMock(rowcount=0)
        mock_session.exec = AsyncMock(return_value=result)

        await cleanup_expired_sessions(mock_session_factory)

        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_batched_deletion(self, mock_session_factory, mock_session):
        """First pass takes two batches; second pass (revoked) finds none."""
        result_full = MagicMock(rowcount=1000)
        result_partial = MagicMock(rowcount=50)
        result_revoked_done = MagicMock(rowcount=0)

        mock_session.exec = AsyncMock(
            side_effect=[result_full, result_partial, result_revoked_done],
        )

        await cleanup_expired_sessions(mock_session_factory)

        assert mock_session.commit.await_count == 2

    @pytest.mark.asyncio
    async def test_revoked_pass_deletes_independently(self, mock_session_factory, mock_session):
        """Expired pass finds nothing, revoked pass finds rows."""
        result_expired_done = MagicMock(rowcount=0)
        result_revoked = MagicMock(rowcount=3)
        result_revoked_done = MagicMock(rowcount=0)

        mock_session.exec = AsyncMock(
            side_effect=[result_expired_done, result_revoked, result_revoked_done],
        )

        await cleanup_expired_sessions(mock_session_factory)

        assert mock_session.commit.await_count == 1


class TestGetSessionCleanupWorker:
    """Tests for get_session_cleanup_worker factory."""

    def test_creates_worker(self):
        with patch("syntara.auth.session.cleanup.AsyncSessionLocal"):
            from syntara.auth.session.cleanup import get_session_cleanup_worker

            worker = get_session_cleanup_worker()
            assert worker._name == "session-cleanup"
            assert worker._interval_seconds == 3600
            assert worker._coordinate is True
