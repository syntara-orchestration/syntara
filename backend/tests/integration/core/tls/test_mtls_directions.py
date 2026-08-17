"""MTLS-1, MTLS-2, MTLS-3: mTLS communication direction integration tests.

Tests verify that the TLS transport layer works for each service-to-service
communication direction defined in the ANSTRAT-2132 test plan.

These tests start a real HTTPS server (uvicorn) and make real TCP connections
to verify TLS handshakes succeed and data flows through encrypted channels.
"""

from __future__ import annotations

import ssl
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import httpx
import pytest
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.x509 import load_pem_x509_certificate
from temporalio.service import TLSConfig

from syntara.core.tls.http_client import build_internal_http_client
from syntara.core.tls.temporal import build_temporal_tls_config
from tests.fixtures.tls import generate_ca, generate_service_cert

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager
    from pathlib import Path

pytestmark = [pytest.mark.integration]


# ---------------------------------------------------------------------------
# MTLS-1: Backend/Worker → Temporal (gRPC TLS config builder)
# ---------------------------------------------------------------------------


class TestMTLS1TemporalTLSConfig:
    """MTLS-1: Verify the Temporal TLS config builder produces a valid TLSConfig."""

    def test_returns_tls_config_when_enabled(
        self,
        mtls_certs: dict[str, Path],
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        with override_settings(
            s2s_tls_enabled=True,
            s2s_tls_ca_cert_path=str(mtls_certs["ca"]),
            s2s_tls_cert_path=str(mtls_certs["backend_cert"]),
            s2s_tls_key_path=str(mtls_certs["backend_key"]),
        ):
            tls_config = build_temporal_tls_config()

        assert isinstance(tls_config, TLSConfig)

    def test_server_root_ca_matches_ca_file(
        self,
        mtls_certs: dict[str, Path],
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        with override_settings(
            s2s_tls_enabled=True,
            s2s_tls_ca_cert_path=str(mtls_certs["ca"]),
            s2s_tls_cert_path=str(mtls_certs["backend_cert"]),
            s2s_tls_key_path=str(mtls_certs["backend_key"]),
        ):
            tls_config = build_temporal_tls_config()

        assert tls_config is not None
        assert tls_config.server_root_ca_cert == mtls_certs["ca"].read_bytes()

    def test_client_cert_matches_cert_file(
        self,
        mtls_certs: dict[str, Path],
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        with override_settings(
            s2s_tls_enabled=True,
            s2s_tls_ca_cert_path=str(mtls_certs["ca"]),
            s2s_tls_cert_path=str(mtls_certs["backend_cert"]),
            s2s_tls_key_path=str(mtls_certs["backend_key"]),
        ):
            tls_config = build_temporal_tls_config()

        assert tls_config is not None
        assert tls_config.client_cert == mtls_certs["backend_cert"].read_bytes()

    def test_client_private_key_matches_key_file(
        self,
        mtls_certs: dict[str, Path],
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        with override_settings(
            s2s_tls_enabled=True,
            s2s_tls_ca_cert_path=str(mtls_certs["ca"]),
            s2s_tls_cert_path=str(mtls_certs["backend_cert"]),
            s2s_tls_key_path=str(mtls_certs["backend_key"]),
        ):
            tls_config = build_temporal_tls_config()

        assert tls_config is not None
        assert tls_config.client_private_key == mtls_certs["backend_key"].read_bytes()


# ---------------------------------------------------------------------------
# MTLS-2: Worker → Backend (HTTP with mTLS)
# ---------------------------------------------------------------------------


class TestMTLS2WorkerToBackend:
    """MTLS-2: Worker presents its client cert to the Backend HTTPS server."""

    def test_worker_cert_accepted(self, mtls_server: str, mtls_certs: dict[str, Path]) -> None:
        """Worker's client cert is accepted by the backend server."""
        ctx = ssl.create_default_context(cafile=str(mtls_certs["ca"]))
        ctx.load_cert_chain(certfile=str(mtls_certs["worker_cert"]), keyfile=str(mtls_certs["worker_key"]))

        with httpx.Client(verify=ctx) as client:
            resp = client.get(f"{mtls_server}/health")

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_no_client_cert_allowed_for_health(self, mtls_server: str, mtls_certs: dict[str, Path]) -> None:
        """Health probes work without a client cert (CERT_OPTIONAL)."""
        ctx = ssl.create_default_context(cafile=str(mtls_certs["ca"]))

        with httpx.Client(verify=ctx) as client:
            resp = client.get(f"{mtls_server}/health")

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_build_internal_http_client_with_worker_cert(
        self,
        mtls_server: str,
        mtls_certs: dict[str, Path],
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """build_internal_http_client() with worker cert can reach the server."""
        with override_settings(
            s2s_tls_enabled=True,
            s2s_tls_ca_cert_path=str(mtls_certs["ca"]),
            s2s_tls_cert_path=str(mtls_certs["worker_cert"]),
            s2s_tls_key_path=str(mtls_certs["worker_key"]),
        ):
            async with build_internal_http_client(base_url=mtls_server) as client:
                resp = await client.get("/health")

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_wrong_ca_rejected(self, mtls_server: str, mtls_certs: dict[str, Path], tmp_path: Path) -> None:
        """A cert signed by a different CA is rejected by the server."""
        rogue_ca_key, rogue_ca_cert = generate_ca(tmp_path)
        rogue_cert, rogue_key = generate_service_cert(
            tmp_path, rogue_ca_key, rogue_ca_cert, common_name="rogue.svc", filename="rogue"
        )

        ctx = ssl.create_default_context(cafile=str(mtls_certs["ca"]))
        ctx.load_cert_chain(certfile=str(rogue_cert), keyfile=str(rogue_key))

        with (
            pytest.raises((ssl.SSLError, httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError)),
            httpx.Client(
                verify=ctx,
            ) as client,
        ):
            client.get(f"{mtls_server}/health")

    def test_expired_cert_rejected(self, mtls_server: str, mtls_certs: dict[str, Path], tmp_path: Path) -> None:
        """NEG-4: An expired client cert signed by the trusted CA is rejected."""
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

        ca_dir = mtls_certs["ca"].parent
        ca_key = load_pem_private_key((ca_dir / "ca.key").read_bytes(), password=None)
        assert isinstance(ca_key, RSAPrivateKey)
        ca_cert = load_pem_x509_certificate(mtls_certs["ca"].read_bytes())

        expired_cert, expired_key = generate_service_cert(
            tmp_path,
            ca_key,
            ca_cert,
            common_name="expired.orchestrator.svc",
            filename="expired",
            not_valid_before=datetime.now(UTC) - timedelta(hours=1),
            not_valid_after=datetime.now(UTC) - timedelta(seconds=1),
        )

        ctx = ssl.create_default_context(cafile=str(mtls_certs["ca"]))
        ctx.load_cert_chain(certfile=str(expired_cert), keyfile=str(expired_key))

        with (
            pytest.raises((ssl.SSLError, httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError)),
            httpx.Client(
                verify=ctx,
            ) as client,
        ):
            client.get(f"{mtls_server}/health")


# ---------------------------------------------------------------------------
# MTLS-3: Backend → Backend (HTTP with mTLS, self-referencing)
# ---------------------------------------------------------------------------


class TestMTLS3BackendToBackend:
    """MTLS-3: Backend presents its own cert to itself (self-referencing mTLS)."""

    def test_backend_cert_accepted_by_self(self, mtls_server: str, mtls_certs: dict[str, Path]) -> None:
        """Backend's own cert (same as server cert) is accepted as a client cert."""
        ctx = ssl.create_default_context(cafile=str(mtls_certs["ca"]))
        ctx.load_cert_chain(certfile=str(mtls_certs["backend_cert"]), keyfile=str(mtls_certs["backend_key"]))

        with httpx.Client(verify=ctx) as client:
            resp = client.get(f"{mtls_server}/health")

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_build_internal_http_client_with_backend_cert(
        self,
        mtls_server: str,
        mtls_certs: dict[str, Path],
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """build_internal_http_client() with backend cert works end-to-end."""
        with override_settings(
            s2s_tls_enabled=True,
            s2s_tls_ca_cert_path=str(mtls_certs["ca"]),
            s2s_tls_cert_path=str(mtls_certs["backend_cert"]),
            s2s_tls_key_path=str(mtls_certs["backend_key"]),
        ):
            async with build_internal_http_client(base_url=mtls_server) as client:
                resp = await client.get("/health")

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
