"""Unit tests for SSL/TLS context construction."""

from __future__ import annotations

import ssl
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from syntara.core.database.ssl import build_ssl_connect_args
from tests.fixtures.tls import generate_ca, generate_self_signed_cert


class TestBuildSslConnectArgs:
    """Tests for build_ssl_connect_args utility function."""

    def test_disable_returns_passthrough(self) -> None:
        result = build_ssl_connect_args(ssl_mode="disable")
        assert result == {"ssl": "disable"}

    def test_allow_returns_passthrough(self) -> None:
        result = build_ssl_connect_args(ssl_mode="allow")
        assert result == {"ssl": "allow"}

    def test_prefer_returns_empty(self) -> None:
        result = build_ssl_connect_args(ssl_mode="prefer")
        assert result == {}

    def test_require_without_certs_returns_passthrough(self) -> None:
        result = build_ssl_connect_args(ssl_mode="require")
        assert result == {"ssl": "require"}

    def test_verify_full_returns_ssl_context(self) -> None:
        result = build_ssl_connect_args(ssl_mode="verify-full")
        assert "ssl" in result
        ctx = result["ssl"]
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.check_hostname is True
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert ctx.minimum_version == ssl.TLSVersion.TLSv1_3

    def test_verify_ca_returns_ssl_context(self) -> None:
        result = build_ssl_connect_args(ssl_mode="verify-ca")
        assert "ssl" in result
        ctx = result["ssl"]
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.check_hostname is False
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert ctx.minimum_version == ssl.TLSVersion.TLSv1_3

    def test_verify_full_with_ca_cert(self, tmp_path: Path) -> None:
        generate_ca(tmp_path)
        result = build_ssl_connect_args(ssl_mode="verify-full", ssl_root_cert=str(tmp_path / "ca.pem"))
        ctx = result["ssl"]
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.check_hostname is True
        assert ctx.minimum_version == ssl.TLSVersion.TLSv1_3

    def test_verify_ca_with_ca_cert(self, tmp_path: Path) -> None:
        generate_ca(tmp_path)
        result = build_ssl_connect_args(ssl_mode="verify-ca", ssl_root_cert=str(tmp_path / "ca.pem"))
        ctx = result["ssl"]
        assert ctx.check_hostname is False
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert ctx.minimum_version == ssl.TLSVersion.TLSv1_3

    def test_require_with_client_certs_returns_context(self, tmp_path: Path) -> None:
        cert_path, key_path = generate_self_signed_cert(tmp_path, "Test Client", "client")
        result = build_ssl_connect_args(ssl_mode="require", ssl_cert=str(cert_path), ssl_key=str(key_path))
        assert "ssl" in result
        ctx = result["ssl"]
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.check_hostname is False
        assert ctx.verify_mode == ssl.CERT_NONE
        assert ctx.minimum_version == ssl.TLSVersion.TLSv1_3

    def test_invalid_ca_cert_path_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            build_ssl_connect_args(ssl_mode="verify-full", ssl_root_cert="/nonexistent/ca.pem")

    def test_verify_full_with_client_certs(self, tmp_path: Path) -> None:
        generate_ca(tmp_path)
        cert_path, key_path = generate_self_signed_cert(tmp_path, "Test Client", "client")
        result = build_ssl_connect_args(
            ssl_mode="verify-full",
            ssl_root_cert=str(tmp_path / "ca.pem"),
            ssl_cert=str(cert_path),
            ssl_key=str(key_path),
        )
        ctx = result["ssl"]
        assert ctx.check_hostname is True
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert ctx.minimum_version == ssl.TLSVersion.TLSv1_3

    def test_unknown_mode_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown SSL mode"):
            build_ssl_connect_args(ssl_mode="bogus")
