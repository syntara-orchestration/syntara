"""Integration tests for PostgreSQL TLS/SSL connections.

Verifies that ``build_ssl_connect_args`` correctly establishes encrypted
connections to a TLS-enabled PostgreSQL instance.

Uses the Docker SDK directly (not ``PostgresContainer``) because we need a
custom entrypoint that copies certificates with correct ownership before
PostgreSQL starts — required for rootless Podman where volume-mounted file
ownership is remapped.  Defaults to ``postgres:15``; override via
``POSTGRES_TLS_IMAGE``.
"""

from __future__ import annotations

import asyncio
import os
import stat
import time
from typing import TYPE_CHECKING

import asyncpg
import pytest
import sqlalchemy
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.core.docker_client import DockerClient

from syntara.core.database.ssl import build_ssl_connect_args
from tests.fixtures.tls import generate_ca, generate_server_cert

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from docker.models.containers import Container  # type: ignore[import-untyped]
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration

_PG_IMAGE = os.getenv("POSTGRES_TLS_IMAGE", "postgres:15")

# Entrypoint script that copies certs with correct ownership before handing
# off to the stock ``docker-entrypoint.sh``.  Required because rootless
# Podman remaps UIDs on volume mounts, making the key unreadable to the
# ``postgres`` user inside the container.
_BOOT_SCRIPT = (
    "cp /certs/server.crt /tmp/server.crt && "
    "cp /certs/server.key /tmp/server.key && "
    "chown postgres:postgres /tmp/server.crt /tmp/server.key && "
    "chmod 600 /tmp/server.key && "
    "chmod 644 /tmp/server.crt && "
    "exec docker-entrypoint.sh postgres "
    "-c ssl=on "
    "-c ssl_cert_file=/tmp/server.crt "
    "-c ssl_key_file=/tmp/server.key"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _wait_for_pg_ready(container: Container, timeout: int = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        container.reload()
        if container.status != "running":
            logs = container.logs().decode(errors="replace")
            msg = f"Container exited unexpectedly.\n{logs[-500:]}"
            raise RuntimeError(msg)
        exit_code, _ = container.exec_run("pg_isready -U test -d testdb")
        if exit_code == 0:
            return
        time.sleep(1)
    logs = container.logs().decode(errors="replace")
    msg = f"PostgreSQL did not become ready in {timeout}s.\n{logs[-500:]}"
    raise TimeoutError(msg)


@pytest.fixture(scope="module")
def tls_certs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate CA and server certificates for PostgreSQL TLS."""
    certs_dir = tmp_path_factory.mktemp("pg_tls_certs")
    ca_key, ca_cert = generate_ca(certs_dir)
    generate_server_cert(certs_dir, ca_key, ca_cert)
    # PostgreSQL refuses to start if the key is group/world-readable
    (certs_dir / "server.key").chmod(stat.S_IRUSR | stat.S_IWUSR)
    return certs_dir


@pytest.fixture(scope="module")
def tls_pg_container(
    tls_certs: Path,
) -> Generator[dict[str, object], None, None]:
    """Start a TLS-enabled PostgreSQL container and yield connection info."""
    dc = DockerClient()
    container = dc.client.containers.run(
        _PG_IMAGE,
        detach=True,
        environment={
            "POSTGRES_USER": "test",
            "POSTGRES_PASSWORD": "test",
            "POSTGRES_DB": "testdb",
        },
        ports={"5432/tcp": None},
        volumes={str(tls_certs): {"bind": "/certs", "mode": "z"}},
        entrypoint="bash",
        command=["-c", _BOOT_SCRIPT],
    )

    try:
        _wait_for_pg_ready(container)
        container.reload()
        port_bindings = container.ports.get("5432/tcp", [])
        if not port_bindings:
            msg = "No port binding found for 5432"
            raise RuntimeError(msg)
        host_port = int(port_bindings[0]["HostPort"])
        yield {
            "host": "localhost",
            "port": host_port,
            "user": "test",
            "password": "test",
            "dbname": "testdb",
            "ca_cert": str(tls_certs / "ca.pem"),
        }
    finally:
        container.stop(timeout=5)
        container.remove(force=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine(
    conn_info: dict[str, object],
    ssl_mode: str,
    ca_cert: str | None = None,
) -> AsyncEngine:
    connect_args = build_ssl_connect_args(
        ssl_mode=ssl_mode,
        ssl_root_cert=ca_cert,
    )
    url = sqlalchemy.engine.URL.create(
        drivername="postgresql+asyncpg",
        username=str(conn_info["user"]),
        password=str(conn_info["password"]),
        host=str(conn_info["host"]),
        port=int(str(conn_info["port"])),
        database=str(conn_info["dbname"]),
    )
    return create_async_engine(url, poolclass=NullPool, connect_args=connect_args)


async def _check_ssl_active(engine: AsyncEngine, retries: int = 5, delay: float = 1.0) -> bool:
    last_err: Exception | None = None
    for _ in range(retries):
        try:
            async with engine.connect() as conn:
                result = await conn.execute(sqlalchemy.text("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()"))
                return bool(result.one()[0])
        except (ConnectionResetError, OSError, asyncpg.CannotConnectNowError) as exc:
            last_err = exc
            await asyncio.sleep(delay)
    raise last_err  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPostgresTLS:
    """Verify SSL connections via ``build_ssl_connect_args`` against a live PostgreSQL."""

    @pytest.mark.asyncio
    async def test_require_uses_ssl(self, tls_pg_container: dict[str, object]) -> None:
        engine = _make_engine(tls_pg_container, ssl_mode="require")
        try:
            assert await _check_ssl_active(engine) is True
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_verify_full_with_ca_cert(self, tls_pg_container: dict[str, object]) -> None:
        engine = _make_engine(
            tls_pg_container,
            ssl_mode="verify-full",
            ca_cert=str(tls_pg_container["ca_cert"]),
        )
        try:
            assert await _check_ssl_active(engine) is True
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_disable_no_ssl(self, tls_pg_container: dict[str, object]) -> None:
        engine = _make_engine(tls_pg_container, ssl_mode="disable")
        try:
            assert await _check_ssl_active(engine) is False
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_verify_full_wrong_ca_rejected(
        self,
        tls_pg_container: dict[str, object],
        tmp_path: Path,
    ) -> None:
        generate_ca(tmp_path)
        wrong_ca = str(tmp_path / "ca.pem")

        engine = _make_engine(
            tls_pg_container,
            ssl_mode="verify-full",
            ca_cert=wrong_ca,
        )
        try:
            with pytest.raises(Exception):  # noqa: B017
                await _check_ssl_active(engine)
        finally:
            await engine.dispose()
