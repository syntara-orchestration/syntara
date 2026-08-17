"""NEG-1, NEG-3: Certificate rejection integration tests.

NEG-1: A certificate with an unrecognized CN (signed by the trusted CA)
       passes the TLS handshake but is rejected by the application middleware.
NEG-3: Requests without a client certificate are allowed on health probes
       but require Bearer-token auth on non-health endpoints.

These tests exercise both the TLS transport layer (via a real HTTPS server
with the custom TLS protocol) and the ``ClientCertAuthMiddleware`` together.
"""

from __future__ import annotations

import ssl
import threading
import time
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import httpx
import pytest
import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from syntara.auth.cert_middleware import ClientCertAuthMiddleware, _validate_client_cert
from syntara.core.tls.protocol import TLSH11Protocol
from tests.fixtures.tls import generate_ca, generate_service_cert
from tests.integration.core.tls.conftest import _health

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from starlette.requests import Request

pytestmark = [pytest.mark.integration]

_ALLOWED_CNS = frozenset({"backend.orchestrator.svc", "worker.orchestrator.svc"})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def neg_certs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Generate CA, valid service cert, and rogue-CN cert for negative tests."""
    certs_dir = tmp_path_factory.mktemp("neg_certs")
    ca_key, ca_cert = generate_ca(certs_dir)

    backend_cert, backend_key = generate_service_cert(
        certs_dir, ca_key, ca_cert, common_name="backend.orchestrator.svc", filename="backend"
    )
    rogue_cert, rogue_key = generate_service_cert(
        certs_dir, ca_key, ca_cert, common_name="rogue-service", filename="rogue"
    )

    return {
        "ca": certs_dir / "ca.pem",
        "backend_cert": backend_cert,
        "backend_key": backend_key,
        "rogue_cert": rogue_cert,
        "rogue_key": rogue_key,
    }


def _protected(request: Request) -> JSONResponse:
    if getattr(request.state, "is_cert_authenticated", False):
        return JSONResponse({"status": "ok", "cn": request.state.cert_cn})
    return JSONResponse({"error": "authentication required"}, status_code=401)


@pytest.fixture(scope="module")
def neg_server(neg_certs: dict[str, Path]) -> Generator[str, None, None]:
    """Start a uvicorn HTTPS server with TLS protocol + ClientCertAuthMiddleware.

    Uses TLSH11Protocol to inject peercert into ASGI scope, and
    ClientCertAuthMiddleware with a CN allowlist for application-layer validation.
    """
    inner_app = Starlette(
        routes=[
            Route("/health", _health),
            Route("/api/v1/test", _protected),
        ],
    )

    mock_settings = MagicMock()
    mock_settings.s2s_tls_enabled = True
    mock_settings.s2s_tls_cn_allowlist = list(_ALLOWED_CNS)
    mock_settings.s2s_tls_crl_path = None

    with patch("syntara.auth.cert_middleware.get_settings", return_value=mock_settings):
        app = ClientCertAuthMiddleware(inner_app)

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=0,
        log_level="warning",
        ssl_certfile=str(neg_certs["backend_cert"]),
        ssl_keyfile=str(neg_certs["backend_key"]),
        ssl_ca_certs=str(neg_certs["ca"]),
        ssl_cert_reqs=ssl.CERT_OPTIONAL,
        http=TLSH11Protocol,
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    else:
        msg = "Negative-test mTLS server did not start within 10s"
        raise TimeoutError(msg)

    actual_port = server.servers[0].sockets[0].getsockname()[1]
    base_url = f"https://127.0.0.1:{actual_port}"

    yield base_url

    server.should_exit = True
    thread.join(timeout=5)


# ---------------------------------------------------------------------------
# NEG-1: Certificate Rejection — Wrong CN
# ---------------------------------------------------------------------------


class TestNEG1WrongCN:
    """NEG-1: A cert with an unrecognized CN gets no service identity (soft fallthrough)."""

    def test_wrong_cn_gets_no_service_identity(self, neg_server: str, neg_certs: dict[str, Path]) -> None:
        """TLS handshake succeeds but non-allowlisted CN gets 401 (no service identity, no JWT)."""
        ctx = ssl.create_default_context(cafile=str(neg_certs["ca"]))
        ctx.load_cert_chain(certfile=str(neg_certs["rogue_cert"]), keyfile=str(neg_certs["rogue_key"]))

        with httpx.Client(verify=ctx) as client:
            resp = client.get(f"{neg_server}/api/v1/test")

        assert resp.status_code == 401

    def test_valid_cn_accepted(self, neg_server: str, neg_certs: dict[str, Path]) -> None:
        """Control: a cert with an allowed CN passes the middleware."""
        ctx = ssl.create_default_context(cafile=str(neg_certs["ca"]))
        ctx.load_cert_chain(certfile=str(neg_certs["backend_cert"]), keyfile=str(neg_certs["backend_key"]))

        with httpx.Client(verify=ctx) as client:
            resp = client.get(f"{neg_server}/api/v1/test")

        assert resp.status_code == 200
        body = resp.json()
        assert body["cn"] == "backend.orchestrator.svc"

    def test_validate_client_cert_extracts_cn_without_allowlist_check(self) -> None:
        """Unit-level: _validate_client_cert returns CN (allowlist is checked by middleware)."""
        peercert: dict[str, object] = {
            "subject": ((("commonName", "rogue-service"),),),
            "serialNumber": "01",
        }
        cn = _validate_client_cert(
            peercert,
            revoked_serials=None,
        )
        assert cn == "rogue-service"


# ---------------------------------------------------------------------------
# NEG-3: Certificate Rejection — No Certificate
# ---------------------------------------------------------------------------


class TestNEG3NoCertificate:
    """NEG-3: Requests without a client certificate handled by endpoint type."""

    def test_health_without_cert_succeeds(self, neg_server: str, neg_certs: dict[str, Path]) -> None:
        """Health probes respond 200 without a client cert."""
        ctx = ssl.create_default_context(cafile=str(neg_certs["ca"]))

        with httpx.Client(verify=ctx) as client:
            resp = client.get(f"{neg_server}/health")

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_non_health_without_cert_or_bearer_rejected(self, neg_server: str, neg_certs: dict[str, Path]) -> None:
        """Non-health endpoint without cert or Bearer token returns 401."""
        ctx = ssl.create_default_context(cafile=str(neg_certs["ca"]))

        with httpx.Client(verify=ctx) as client:
            resp = client.get(f"{neg_server}/api/v1/test")

        assert resp.status_code == 401

    def test_middleware_sets_unauthenticated_state_for_no_cert(self) -> None:
        """Middleware sets is_cert_authenticated=False when no cert is presented."""
        import asyncio

        captured_state: dict[str, object] = {}

        async def capture_app(scope: dict[str, object], _receive: object, _send: object) -> None:
            state = scope.get("state", {})
            if isinstance(state, dict):
                captured_state.update(state)

        mock_settings = MagicMock()
        mock_settings.s2s_tls_enabled = True
        mock_settings.s2s_tls_cn_allowlist = list(_ALLOWED_CNS)
        mock_settings.s2s_tls_crl_path = None

        with patch("syntara.auth.cert_middleware.get_settings", return_value=mock_settings):
            middleware = ClientCertAuthMiddleware(capture_app)

        scope: dict[str, object] = {
            "type": "http",
            "path": "/api/v1/test",
            "extensions": {},
            "state": {},
            "headers": [],
        }

        asyncio.get_event_loop().run_until_complete(
            middleware(scope, lambda: {"type": "http.request"}, lambda _msg: None)
        )

        assert captured_state["is_cert_authenticated"] is False
        assert captured_state["cert_cn"] is None
