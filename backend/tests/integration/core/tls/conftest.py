"""Shared fixtures for mTLS integration tests.

Provides certificate generation, an HTTPS server backed by uvicorn,
and LRU-cache clearing between tests.
"""

from __future__ import annotations

import ssl
import threading
import time
from typing import TYPE_CHECKING

import pytest
import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from syntara.core.tls.http_client import build_internal_ssl_context
from syntara.core.tls.temporal import build_temporal_tls_config
from tests.fixtures.tls import generate_ca, generate_service_cert

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from starlette.requests import Request


@pytest.fixture(autouse=True)
def _clear_tls_caches() -> None:
    """Clear cached TLS configs between tests to ensure isolation."""
    build_internal_ssl_context.cache_clear()
    build_temporal_tls_config.cache_clear()


@pytest.fixture(scope="module")
def mtls_certs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Generate CA + two service certs with distinct CNs for mTLS testing."""
    certs_dir = tmp_path_factory.mktemp("mtls_certs")
    ca_key, ca_cert = generate_ca(certs_dir)

    backend_cert, backend_key = generate_service_cert(
        certs_dir, ca_key, ca_cert, common_name="backend.nexus.svc", filename="backend"
    )
    worker_cert, worker_key = generate_service_cert(
        certs_dir, ca_key, ca_cert, common_name="worker.nexus.svc", filename="worker"
    )

    return {
        "ca": certs_dir / "ca.pem",
        "backend_cert": backend_cert,
        "backend_key": backend_key,
        "worker_cert": worker_cert,
        "worker_key": worker_key,
    }


def _health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


@pytest.fixture(scope="module")
def mtls_server(mtls_certs: dict[str, Path]) -> Generator[str, None, None]:
    """Start a uvicorn HTTPS server with mTLS (CERT_OPTIONAL) in a background thread.

    Yields the ``https://127.0.0.1:{port}`` base URL.
    """
    app = Starlette(routes=[Route("/health", _health)])

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=0,
        log_level="warning",
        ssl_certfile=str(mtls_certs["backend_cert"]),
        ssl_keyfile=str(mtls_certs["backend_key"]),
        ssl_ca_certs=str(mtls_certs["ca"]),
        ssl_cert_reqs=ssl.CERT_OPTIONAL,
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for the server socket to bind
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    else:
        msg = "mTLS test server did not start within 10s"
        raise TimeoutError(msg)

    actual_port = server.servers[0].sockets[0].getsockname()[1]
    base_url = f"https://127.0.0.1:{actual_port}"

    yield base_url

    server.should_exit = True
    thread.join(timeout=5)
