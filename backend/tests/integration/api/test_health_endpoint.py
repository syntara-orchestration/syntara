"""Integration tests for the /health and /healthz/{live,ready} endpoints."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Self

    from httpx import AsyncClient


@pytest.fixture(autouse=True)
def _clear_db_probe_cache() -> Iterator[None]:
    """Reset the probe memo so cached outcomes never leak between tests.

    ``_check_database`` memoises its result process-wide, so without this
    a test that primes the cache with "ok" would mask the next test's
    simulated outage.
    """
    with patch("syntara.api.main._db_probe_cache", None):
        yield


class TestHealthEndpointFileStorage:
    """Verify that /health includes file_storage in its response."""

    @pytest.mark.asyncio
    async def test_includes_file_storage_field_when_unconfigured(
        self,
        base_client: AsyncClient,
    ) -> None:
        """Regression guard: /health must return checks.file_storage.

        The frontend's useFileStorageStatus hook gates the upload UI on this
        field — if absent it fails open and shows upload as available even
        when S3 is not configured.
        """
        mock_fm = MagicMock()
        type(mock_fm).s3_configured = PropertyMock(return_value=False)

        with patch("syntara.files.health.get_file_manager", return_value=mock_fm):
            resp = await base_client.get("/health")

        assert resp.status_code == 200
        body = resp.json()
        assert "file_storage" in body["checks"], "/health response is missing 'file_storage' in checks"
        assert body["checks"]["file_storage"] == "unconfigured"

    @pytest.mark.asyncio
    async def test_includes_file_storage_field_when_configured(
        self,
        base_client: AsyncClient,
    ) -> None:
        mock_fm = MagicMock()
        type(mock_fm).s3_configured = PropertyMock(return_value=True)
        mock_retriever = MagicMock()
        mock_retriever.health_check = AsyncMock(return_value=True)
        mock_fm.get_retriever.return_value = mock_retriever

        with patch("syntara.files.health.get_file_manager", return_value=mock_fm):
            resp = await base_client.get("/health")

        assert resp.status_code == 200
        assert resp.json()["checks"]["file_storage"] == "ok"


class TestLivenessEndpoint:
    """/healthz/live reports process liveness only."""

    @pytest.mark.asyncio
    async def test_reports_alive(self, base_client: AsyncClient) -> None:
        resp = await base_client.get("/healthz/live")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "alive"
        assert "timestamp" in body

    @pytest.mark.asyncio
    async def test_does_not_check_database(self, base_client: AsyncClient) -> None:
        """Regression guard: a database outage must never fail liveness.

        Liveness failures restart the container, so a transient database
        blip would otherwise cascade into a restart storm across replicas.
        """
        with patch("syntara.api.main.AsyncSessionLocal", side_effect=ConnectionError("database is unreachable")):
            resp = await base_client.get("/healthz/live")

        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"

    @pytest.mark.asyncio
    async def test_does_not_report_dependency_checks(self, base_client: AsyncClient) -> None:
        """Liveness carries no dependency detail — that belongs to readiness."""
        resp = await base_client.get("/healthz/live")

        assert "checks" not in resp.json()


class TestReadinessEndpoint:
    """/healthz/ready reports whether the API can serve traffic."""

    @pytest.mark.asyncio
    async def test_reports_ready_with_database_check(self, base_client: AsyncClient) -> None:
        resp = await base_client.get("/healthz/ready")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        assert body["checks"]["database"] == "ok"

    @pytest.mark.asyncio
    async def test_returns_503_when_database_unreachable(self, base_client: AsyncClient) -> None:
        """A database outage must drop the pod out of the Service endpoints."""
        with patch("syntara.api.main.AsyncSessionLocal", side_effect=ConnectionError("database is unreachable")):
            resp = await base_client.get("/healthz/ready")

        assert resp.status_code == 503
        body = resp.json()
        assert body["detail"] == "Database is unreachable"
        assert body["title"] == "Service Unavailable"

    @pytest.mark.asyncio
    async def test_fails_fast_when_database_hangs(self, base_client: AsyncClient) -> None:
        """A slow-but-alive database must not outlive the probe that started it.

        Without a bound the check waits out ``db_pool_timeout_seconds``
        (30s) or hangs indefinitely, long past the kubelet's timeoutSeconds.
        Abandoned checks keep their place in the pool's FIFO queue and
        contend for connections exactly when they are scarcest.
        """

        class _HangingSession:
            """Stands in for a pool checkout that never completes."""

            async def __aenter__(self) -> None:
                await asyncio.sleep(60)

            async def __aexit__(self, *_exc_info: object) -> None:
                return None

        with (
            patch("syntara.api.main.DB_PROBE_TIMEOUT_SECONDS", 0.05),
            patch("syntara.api.main.AsyncSessionLocal", _HangingSession),
        ):
            start = time.monotonic()
            resp = await base_client.get("/healthz/ready")
            elapsed = time.monotonic() - start

        assert resp.status_code == 503
        assert "did not complete" in resp.json()["detail"]
        assert elapsed < 5, f"probe took {elapsed:.1f}s; it must fail fast rather than hang"

    @pytest.mark.asyncio
    async def test_releases_the_connection_on_every_path(self, base_client: AsyncClient) -> None:
        """The probe must hand its pooled connection back deterministically.

        The bound on the probe limits how long it *waits* for a slot; it is
        this release that limits how long it *holds* one. Driving the
        ``get_db()`` yield-dependency with ``async for ... break`` left the
        generator suspended at its ``yield``, so ``session.close()`` never
        ran and the connection stayed checked out until nondeterministic
        asyncgen finalization — on the success path of every probe, i.e.
        every 5s per replica, which is the pool saturation the bound is
        meant to relieve.
        """
        closed = asyncio.Event()

        class _TrackedSession:
            def __init__(self, *, hang: bool) -> None:
                self._hang = hang

            async def __aenter__(self) -> Self:
                return self

            async def __aexit__(self, *_exc_info: object) -> None:
                closed.set()

            async def exec(self, *_args: object, **_kwargs: object) -> MagicMock:
                if self._hang:
                    await asyncio.sleep(60)
                return MagicMock()

        # TTL of 0 disables the memo so both phases really open a session.
        # Success path — where the leak actually was.
        with (
            patch("syntara.api.main.DB_PROBE_CACHE_TTL_SECONDS", 0),
            patch("syntara.api.main.AsyncSessionLocal", lambda: _TrackedSession(hang=False)),
        ):
            resp = await base_client.get("/healthz/ready")

        assert resp.status_code == 200
        assert closed.is_set(), "session was not closed after a successful probe; the connection stayed checked out"

        # Timeout path.
        closed.clear()
        with (
            patch("syntara.api.main.DB_PROBE_CACHE_TTL_SECONDS", 0),
            patch("syntara.api.main.DB_PROBE_TIMEOUT_SECONDS", 0.05),
            patch("syntara.api.main.AsyncSessionLocal", lambda: _TrackedSession(hang=True)),
        ):
            resp = await base_client.get("/healthz/ready")

        assert resp.status_code == 503
        assert closed.is_set(), "session was not closed when the probe timed out; the connection stayed checked out"

    @pytest.mark.asyncio
    async def test_excludes_file_storage(self, base_client: AsyncClient) -> None:
        """Object storage is not a hard dependency, so it must not appear here.

        An unconfigured or degraded S3 backend only disables file uploads;
        reporting it on the readiness probe would invite wiring it into a
        pod's readiness state. It is served by /api/v1/files/storage_status.
        """
        mock_fm = MagicMock()
        type(mock_fm).s3_configured = PropertyMock(return_value=False)

        with patch("syntara.files.health.get_file_manager", return_value=mock_fm):
            resp = await base_client.get("/healthz/ready")

        assert resp.status_code == 200
        assert resp.json()["checks"] == {"database": "ok"}

    @pytest.mark.asyncio
    async def test_stays_ready_when_file_storage_is_unavailable(self, base_client: AsyncClient) -> None:
        """A broken object store must never take a replica out of rotation."""
        with patch("syntara.files.health.get_file_manager", side_effect=RuntimeError("S3 is down")):
            resp = await base_client.get("/healthz/ready")

        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"


class TestReadinessProbeCache:
    """The probe memoises its outcome so bursts collapse into one query."""

    @staticmethod
    def _counting_session_factory(counter: list[int]) -> object:
        class _CountingSession:
            async def __aenter__(self) -> Self:
                counter.append(1)
                return self

            async def __aexit__(self, *_exc_info: object) -> None:
                return None

            async def exec(self, *_args: object, **_kwargs: object) -> MagicMock:
                return MagicMock()

        return _CountingSession

    @pytest.mark.asyncio
    async def test_repeat_probes_within_ttl_query_the_database_once(self, base_client: AsyncClient) -> None:
        """Startup, readiness and /health can fire in the same second.

        Without the memo each opens its own connection, exactly when the
        pool is most contended.
        """
        opened: list[int] = []

        with patch("syntara.api.main.AsyncSessionLocal", self._counting_session_factory(opened)):
            first = await base_client.get("/healthz/ready")
            second = await base_client.get("/healthz/ready")
            third = await base_client.get("/health")

        assert first.status_code == second.status_code == third.status_code == 200
        assert len(opened) == 1, f"expected one database query across three probes, got {len(opened)}"

    @pytest.mark.asyncio
    async def test_probes_query_again_once_the_ttl_expires(self, base_client: AsyncClient) -> None:
        """The memo must not pin a stale answer past its window."""
        opened: list[int] = []

        with (
            patch("syntara.api.main.DB_PROBE_CACHE_TTL_SECONDS", 0.05),
            patch("syntara.api.main.AsyncSessionLocal", self._counting_session_factory(opened)),
        ):
            await base_client.get("/healthz/ready")
            await asyncio.sleep(0.1)
            resp = await base_client.get("/healthz/ready")

        assert resp.status_code == 200
        assert len(opened) == 2, f"expected a fresh query after the TTL lapsed, got {len(opened)}"

    @pytest.mark.asyncio
    async def test_failures_are_cached_too(self, base_client: AsyncClient) -> None:
        """An outage must not turn every probe into another failing query."""
        attempts: list[int] = []

        def _failing_factory() -> object:
            attempts.append(1)
            msg = "database is unreachable"
            raise ConnectionError(msg)

        with patch("syntara.api.main.AsyncSessionLocal", _failing_factory):
            first = await base_client.get("/healthz/ready")
            second = await base_client.get("/healthz/ready")

        assert first.status_code == second.status_code == 503
        assert first.json()["detail"] == second.json()["detail"] == "Database is unreachable"
        assert len(attempts) == 1, f"expected the failure to be cached, got {len(attempts)} attempts"

    @pytest.mark.asyncio
    async def test_recovery_is_seen_within_one_probe_interval(self, base_client: AsyncClient) -> None:
        """A cached failure must clear on its own, without a restart."""
        with patch("syntara.api.main.AsyncSessionLocal", side_effect=ConnectionError("db down")):
            failed = await base_client.get("/healthz/ready")

        assert failed.status_code == 503

        # The cached failure lapses; the next probe reaches a healthy database.
        with patch("syntara.api.main._db_probe_cache", None):
            recovered = await base_client.get("/healthz/ready")

        assert recovered.status_code == 200
        assert recovered.json()["checks"]["database"] == "ok"
