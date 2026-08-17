"""Tests for ClientCertAuthMiddleware — mTLS client certificate authentication."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

import pytest

from syntara.auth.cert_middleware import (
    CertificateValidationError,
    ClientCertAuthMiddleware,
    _extract_cn,
    _load_revoked_serials,
    _validate_client_cert,
)


def _make_scope(
    *,
    path: str = "/api/v1/workflows",
    peercert: dict[str, Any] | None = None,
    headers: list[tuple[bytes, bytes]] | None = None,
) -> dict[str, Any]:
    scope: dict[str, Any] = {
        "type": "http",
        "path": path,
        "headers": headers or [],
        "state": {},
    }
    if peercert is not None:
        scope["extensions"] = {"tls": {"peercert": peercert}}
    return scope


def _make_peercert(cn: str = "worker.ao.svc", serial: str = "01") -> dict[str, Any]:
    return {"subject": ((("commonName", cn),),), "serialNumber": serial}


class TestExtractCn:
    """Tests for _extract_cn helper."""

    def test_extracts_cn(self) -> None:
        assert _extract_cn(_make_peercert("backend.ao.svc")) == "backend.ao.svc"

    def test_returns_none_for_empty_subject(self) -> None:
        assert _extract_cn({"subject": ()}) is None

    def test_returns_none_for_no_cn(self) -> None:
        assert _extract_cn({"subject": ((("organizationName", "Syntara"),),)}) is None


class TestValidateClientCert:
    """Tests for _validate_client_cert pure function."""

    def test_valid_cert_returns_cn(self) -> None:
        cn = _validate_client_cert(
            _make_peercert("backend.ao.svc"),
            revoked_serials=None,
        )
        assert cn == "backend.ao.svc"

    def test_revoked_serial_rejected(self) -> None:
        cert = _make_peercert(serial="0A")
        with pytest.raises(CertificateValidationError, match="revoked") as exc_info:
            _validate_client_cert(cert, revoked_serials=frozenset({0x0A}))
        assert exc_info.value.reason == "certificate_revoked"

    def test_non_revoked_serial_accepted(self) -> None:
        cn = _validate_client_cert(
            _make_peercert(serial="0B"),
            revoked_serials=frozenset({0x0A}),
        )
        assert cn == "worker.ao.svc"

    def test_none_revoked_serials_skips_check(self) -> None:
        cn = _validate_client_cert(
            _make_peercert(serial="0A"),
            revoked_serials=None,
        )
        assert cn == "worker.ao.svc"

    def test_revoked_cert_rejected_regardless_of_cn(self) -> None:
        cert = _make_peercert("backend.ao.svc", serial="0A")
        with pytest.raises(CertificateValidationError) as exc_info:
            _validate_client_cert(cert, revoked_serials=frozenset({0x0A}))
        assert exc_info.value.reason == "certificate_revoked"

    def test_no_cn_in_peercert_raises(self) -> None:
        peercert = {"subject": ((("organizationName", "Syntara"),),), "serialNumber": "01"}
        with pytest.raises(CertificateValidationError) as exc_info:
            _validate_client_cert(
                peercert,
                revoked_serials=None,
            )
        assert exc_info.value.reason == "missing_cn"


class TestLoadRevokedSerials:
    """Tests for _load_revoked_serials using generate_crl helper."""

    def test_loads_empty_crl(self, tmp_path: Path) -> None:
        from tests.fixtures.tls import generate_ca, generate_crl

        ca_key, ca_cert = generate_ca(tmp_path)
        crl_path = generate_crl(tmp_path, ca_key, ca_cert)
        serials = _load_revoked_serials(str(crl_path))
        assert serials == frozenset()

    def test_loads_revoked_serials(self, tmp_path: Path) -> None:
        from tests.fixtures.tls import generate_ca, generate_crl, generate_service_cert

        ca_key, ca_cert = generate_ca(tmp_path)
        cert_path, _ = generate_service_cert(tmp_path, ca_key, ca_cert, common_name="revoked.svc")

        from cryptography import x509 as x509_mod

        revoked_cert = x509_mod.load_pem_x509_certificate(cert_path.read_bytes())

        crl_path = generate_crl(tmp_path, ca_key, ca_cert, revoked_certs=[revoked_cert])
        serials = _load_revoked_serials(str(crl_path))
        assert revoked_cert.serial_number in serials
        assert len(serials) == 1


class TestClientCertAuthMiddleware:
    """Tests for the ASGI middleware."""

    @pytest.fixture
    def _tls_enabled(self) -> Generator[None]:
        with patch("syntara.auth.cert_middleware.get_settings") as mock:
            mock.return_value.s2s_tls_enabled = True
            mock.return_value.s2s_tls_cn_allowlist = None
            mock.return_value.s2s_tls_crl_path = None
            yield

    @pytest.fixture
    def _tls_disabled(self) -> Generator[None]:
        with patch("syntara.auth.cert_middleware.get_settings") as mock:
            mock.return_value.s2s_tls_enabled = False
            mock.return_value.s2s_tls_cn_allowlist = None
            mock.return_value.s2s_tls_crl_path = None
            yield

    @pytest.fixture
    def _tls_with_allowlist(self) -> Generator[None]:
        with patch("syntara.auth.cert_middleware.get_settings") as mock:
            mock.return_value.s2s_tls_enabled = True
            mock.return_value.s2s_tls_cn_allowlist = ["worker.ao.svc", "backend.ao.svc"]
            mock.return_value.s2s_tls_crl_path = None
            yield

    @pytest.fixture
    def _tls_with_revocation(self, tmp_path: Path) -> Generator[None]:
        from tests.fixtures.tls import generate_ca, generate_crl, generate_service_cert

        ca_key, ca_cert = generate_ca(tmp_path)
        cert_path, _ = generate_service_cert(tmp_path, ca_key, ca_cert, common_name="revoked.svc")

        from cryptography import x509 as x509_mod

        revoked_cert = x509_mod.load_pem_x509_certificate(cert_path.read_bytes())
        crl_path = generate_crl(tmp_path, ca_key, ca_cert, revoked_certs=[revoked_cert])
        self._revoked_serial = f"{revoked_cert.serial_number:X}"

        with patch("syntara.auth.cert_middleware.get_settings") as mock:
            mock.return_value.s2s_tls_enabled = True
            mock.return_value.s2s_tls_cn_allowlist = None
            mock.return_value.s2s_tls_crl_path = str(crl_path)
            yield

    @pytest.mark.usefixtures("_tls_with_allowlist")
    @pytest.mark.asyncio
    async def test_cert_on_allowlist_sets_service_identity(self) -> None:
        """Valid client cert on allowlist sets is_cert_authenticated and cert_cn."""
        app = AsyncMock()
        middleware = ClientCertAuthMiddleware(app)
        scope = _make_scope(peercert=_make_peercert("worker.ao.svc"))

        await middleware(scope, AsyncMock(), AsyncMock())

        assert scope["state"]["is_cert_authenticated"] is True
        assert scope["state"]["cert_cn"] == "worker.ao.svc"
        app.assert_called_once()

    @pytest.mark.usefixtures("_tls_enabled")
    @pytest.mark.asyncio
    async def test_cert_without_allowlist_gets_no_service_identity(self) -> None:
        """Valid cert with no allowlist configured: no service identity (fail closed)."""
        app = AsyncMock()
        middleware = ClientCertAuthMiddleware(app)
        scope = _make_scope(peercert=_make_peercert("worker.ao.svc"))

        await middleware(scope, AsyncMock(), AsyncMock())

        assert scope["state"]["is_cert_authenticated"] is False
        assert scope["state"]["cert_cn"] is None
        app.assert_called_once()

    @pytest.mark.usefixtures("_tls_enabled")
    @pytest.mark.asyncio
    async def test_no_cert_passes_through(self) -> None:
        """No client cert: is_cert_authenticated=False, request continues."""
        app = AsyncMock()
        middleware = ClientCertAuthMiddleware(app)
        scope = _make_scope()

        await middleware(scope, AsyncMock(), AsyncMock())

        assert scope["state"]["is_cert_authenticated"] is False
        assert scope["state"]["cert_cn"] is None
        app.assert_called_once()

    @pytest.mark.usefixtures("_tls_with_allowlist")
    @pytest.mark.asyncio
    async def test_on_behalf_of_trusted_with_cert(self) -> None:
        """X-On-Behalf-Of header is preserved when cert-authenticated."""
        app = AsyncMock()
        middleware = ClientCertAuthMiddleware(app)
        headers = [(b"x-on-behalf-of", b"user@example.com")]
        scope = _make_scope(peercert=_make_peercert("worker.ao.svc"), headers=headers)

        await middleware(scope, AsyncMock(), AsyncMock())

        header_names = [k for k, v in scope["headers"]]
        assert b"x-on-behalf-of" in header_names

    @pytest.mark.usefixtures("_tls_enabled")
    @pytest.mark.asyncio
    async def test_on_behalf_of_stripped_without_cert(self) -> None:
        """X-On-Behalf-Of header is stripped when NOT cert-authenticated."""
        app = AsyncMock()
        middleware = ClientCertAuthMiddleware(app)
        headers = [(b"x-on-behalf-of", b"user@example.com"), (b"content-type", b"application/json")]
        scope = _make_scope(headers=headers)

        await middleware(scope, AsyncMock(), AsyncMock())

        header_names = [k for k, v in scope["headers"]]
        assert b"x-on-behalf-of" not in header_names
        assert b"content-type" in header_names

    @pytest.mark.usefixtures("_tls_enabled")
    @pytest.mark.asyncio
    async def test_health_route_bypassed(self) -> None:
        """Health routes skip cert processing entirely."""
        app = AsyncMock()
        middleware = ClientCertAuthMiddleware(app)
        scope = _make_scope(path="/health")

        await middleware(scope, AsyncMock(), AsyncMock())

        assert "is_cert_authenticated" not in scope.get("state", {})
        app.assert_called_once()

    @pytest.mark.usefixtures("_tls_disabled")
    @pytest.mark.asyncio
    async def test_tls_disabled_noop(self) -> None:
        """When S2S TLS is disabled, middleware is a no-op."""
        app = AsyncMock()
        middleware = ClientCertAuthMiddleware(app)
        headers = [(b"x-on-behalf-of", b"spoofed@evil.com")]
        scope = _make_scope(headers=headers)

        await middleware(scope, AsyncMock(), AsyncMock())

        assert "is_cert_authenticated" not in scope.get("state", {})
        header_names = [k for k, v in scope["headers"]]
        assert b"x-on-behalf-of" in header_names
        app.assert_called_once()

    @pytest.mark.usefixtures("_tls_enabled")
    @pytest.mark.asyncio
    async def test_non_http_passthrough(self) -> None:
        """Non-HTTP scopes (websocket, lifespan) pass through."""
        app = AsyncMock()
        middleware = ClientCertAuthMiddleware(app)
        scope: dict[str, Any] = {"type": "websocket", "path": "/ws"}

        await middleware(scope, AsyncMock(), AsyncMock())

        app.assert_called_once()

    @pytest.mark.usefixtures("_tls_with_allowlist")
    @pytest.mark.asyncio
    async def test_cn_not_in_allowlist_passes_without_service_identity(self) -> None:
        """CN not in allowlist passes through but without service identity."""
        app = AsyncMock()
        middleware = ClientCertAuthMiddleware(app)
        scope = _make_scope(peercert=_make_peercert("ui.ao.svc"))

        await middleware(scope, AsyncMock(), AsyncMock())

        assert scope["state"]["is_cert_authenticated"] is False
        assert scope["state"]["cert_cn"] is None
        app.assert_called_once()

    @pytest.mark.usefixtures("_tls_with_allowlist")
    @pytest.mark.asyncio
    async def test_cn_not_in_allowlist_strips_on_behalf_of(self) -> None:
        """X-On-Behalf-Of is stripped for CNs not in allowlist."""
        app = AsyncMock()
        middleware = ClientCertAuthMiddleware(app)
        headers = [(b"x-on-behalf-of", b"user@example.com"), (b"content-type", b"application/json")]
        scope = _make_scope(peercert=_make_peercert("ui.ao.svc"), headers=headers)

        await middleware(scope, AsyncMock(), AsyncMock())

        header_names = [k for k, v in scope["headers"]]
        assert b"x-on-behalf-of" not in header_names
        assert b"content-type" in header_names

    @pytest.mark.usefixtures("_tls_with_allowlist")
    @pytest.mark.asyncio
    async def test_cn_in_allowlist_passes(self) -> None:
        """CN in allowlist is accepted with service identity."""
        app = AsyncMock()
        middleware = ClientCertAuthMiddleware(app)
        scope = _make_scope(peercert=_make_peercert("worker.ao.svc"))

        await middleware(scope, AsyncMock(), AsyncMock())

        assert scope["state"]["is_cert_authenticated"] is True
        assert scope["state"]["cert_cn"] == "worker.ao.svc"
        app.assert_called_once()

    @pytest.mark.usefixtures("_tls_with_revocation")
    @pytest.mark.asyncio
    async def test_revoked_serial_returns_403(self) -> None:
        """Revoked certificate serial returns 403."""
        app = AsyncMock()
        middleware = ClientCertAuthMiddleware(app)
        scope = _make_scope(peercert=_make_peercert("revoked.svc", serial=self._revoked_serial))
        send = AsyncMock()

        await middleware(scope, AsyncMock(), send)

        app.assert_not_called()
        start_call = send.call_args_list[0]
        assert start_call[0][0]["status"] == 403

    @pytest.mark.usefixtures("_tls_with_revocation")
    @pytest.mark.asyncio
    async def test_403_body_is_valid_problem_json(self) -> None:
        """403 response body is valid RFC 9457 problem+json."""
        app = AsyncMock()
        middleware = ClientCertAuthMiddleware(app)
        scope = _make_scope(peercert=_make_peercert("revoked.svc", serial=self._revoked_serial))
        send = AsyncMock()

        await middleware(scope, AsyncMock(), send)

        start_call = send.call_args_list[0][0][0]
        body_call = send.call_args_list[1][0][0]
        headers_dict = dict(start_call["headers"])
        assert headers_dict[b"content-type"] == b"application/problem+json"
        body = json.loads(body_call["body"])
        assert body["status"] == 403
        assert body["type"].startswith("https://api.example.com/errors/")
        assert "title" in body
        assert "detail" in body

    @pytest.mark.usefixtures("_tls_with_allowlist")
    @pytest.mark.asyncio
    async def test_no_cert_passes_through_with_allowlist(self) -> None:
        """No cert still passes through even when allowlist is set."""
        app = AsyncMock()
        middleware = ClientCertAuthMiddleware(app)
        scope = _make_scope()

        await middleware(scope, AsyncMock(), AsyncMock())

        assert scope["state"]["is_cert_authenticated"] is False
        assert scope["state"]["cert_cn"] is None
        app.assert_called_once()


class TestUserFromCert:
    """Tests for _user_from_cert service user construction."""

    @staticmethod
    def _make_request(on_behalf_of: str | None = None) -> MagicMock:
        request = MagicMock()
        request.headers = {"x-on-behalf-of": on_behalf_of} if on_behalf_of else {}
        return request

    def test_fallback_uses_service_principal_id(self) -> None:
        """Without X-On-Behalf-Of, uses service_principal_id derived from CN."""
        from syntara.auth.dependencies import _user_from_cert
        from syntara.core.models.principal import service_principal_id

        request = self._make_request()
        user = _user_from_cert(request, "backend.ao.svc")
        assert user.id == service_principal_id("backend.ao.svc")

    def test_on_behalf_of_uses_header_uuid(self) -> None:
        """With valid X-On-Behalf-Of header, uses that UUID."""
        from uuid import UUID

        from syntara.auth.dependencies import _user_from_cert

        user_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        request = self._make_request(on_behalf_of=user_id)
        user = _user_from_cert(request, "backend.ao.svc")
        assert user.id == UUID(user_id)

    def test_invalid_on_behalf_of_falls_back(self) -> None:
        """With invalid X-On-Behalf-Of, falls back to service_principal_id."""
        from syntara.auth.dependencies import _user_from_cert
        from syntara.core.models.principal import service_principal_id

        request = self._make_request(on_behalf_of="not-a-uuid")
        user = _user_from_cert(request, "backend.ao.svc")
        assert user.id == service_principal_id("backend.ao.svc")

    def test_user_fields_populated(self) -> None:
        """Username, email, and first_name are populated from CN."""
        from syntara.auth.dependencies import _user_from_cert

        request = self._make_request()
        user = _user_from_cert(request, "backend.ao.svc")
        assert user.username == "backend.ao.svc"
        assert user.email == "backend.ao.svc@internal"
        assert user.first_name == "backend.ao.svc"
        assert user.is_enabled is True


class TestAllowlistDriftWarning:
    """Tests for startup warning when KNOWN_SERVICE_CNS ⊄ allowlist."""

    def test_warns_when_known_cns_missing_from_allowlist(self) -> None:
        with (
            patch("syntara.auth.cert_middleware.get_settings") as mock,
            patch("syntara.auth.cert_middleware.logger") as mock_logger,
        ):
            mock.return_value.s2s_tls_enabled = True
            mock.return_value.s2s_tls_cn_allowlist = ["worker.ao.svc"]
            mock.return_value.s2s_tls_crl_path = None
            ClientCertAuthMiddleware(AsyncMock())
        mock_logger.warning.assert_called_once()
        assert "KNOWN_SERVICE_CNS entries missing" in mock_logger.warning.call_args[0][0]

    def test_no_warning_when_all_known_cns_in_allowlist(self) -> None:
        from syntara.core.models.principal import KNOWN_SERVICE_CNS

        with (
            patch("syntara.auth.cert_middleware.get_settings") as mock,
            patch("syntara.auth.cert_middleware.logger") as mock_logger,
        ):
            mock.return_value.s2s_tls_enabled = True
            mock.return_value.s2s_tls_cn_allowlist = list(KNOWN_SERVICE_CNS)
            mock.return_value.s2s_tls_crl_path = None
            ClientCertAuthMiddleware(AsyncMock())
        mock_logger.warning.assert_not_called()
