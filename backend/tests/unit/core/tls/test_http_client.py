"""Unit tests for internal HTTP client factory with mTLS support."""

from __future__ import annotations

import ssl
from typing import TYPE_CHECKING

import httpx
import pytest

from syntara.core.config.base import Settings
from syntara.core.tls.http_client import build_internal_http_client, build_internal_ssl_context

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager
    from pathlib import Path


class TestBuildInternalSslContext:
    """Tests for build_internal_ssl_context()."""

    def test_disabled_returns_none(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        with override_settings(s2s_tls_enabled=False):
            assert build_internal_ssl_context() is None

    def test_enabled_returns_ssl_context(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
        tls_certs: dict[str, Path],
    ) -> None:
        with override_settings(
            s2s_tls_enabled=True,
            s2s_tls_ca_cert_path=str(tls_certs["ca"]),
            s2s_tls_cert_path=str(tls_certs["cert"]),
            s2s_tls_key_path=str(tls_certs["key"]),
        ):
            ctx = build_internal_ssl_context()

        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert ctx.check_hostname is True
        assert ctx.minimum_version == ssl.TLSVersion.TLSv1_3


class TestBuildInternalHttpClient:
    """Tests for build_internal_http_client()."""

    def test_disabled_returns_plain_client(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        with override_settings(s2s_tls_enabled=False):
            client = build_internal_http_client(timeout=5.0)

        assert isinstance(client, httpx.AsyncClient)

    def test_enabled_returns_client_with_ssl(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
        tls_certs: dict[str, Path],
    ) -> None:
        with override_settings(
            s2s_tls_enabled=True,
            s2s_tls_ca_cert_path=str(tls_certs["ca"]),
            s2s_tls_cert_path=str(tls_certs["cert"]),
            s2s_tls_key_path=str(tls_certs["key"]),
        ):
            client = build_internal_http_client()

        assert isinstance(client, httpx.AsyncClient)

    def test_kwargs_passthrough(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        with override_settings(s2s_tls_enabled=False):
            client = build_internal_http_client(
                base_url="http://localhost:8000",
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
            )

        assert str(client.base_url).rstrip("/") == "http://localhost:8000"
        assert client.timeout == httpx.Timeout(30.0)


class TestS2STlsSettingsValidation:
    """Tests for S2STLSSettings fail-closed validation."""

    def test_enabled_missing_ca_cert(self, monkeypatch: pytest.MonkeyPatch, tls_certs: dict[str, Path]) -> None:
        monkeypatch.setenv("APP_S2S_TLS_ENABLED", "true")
        monkeypatch.setenv("APP_S2S_TLS_CERT_PATH", str(tls_certs["cert"]))
        monkeypatch.setenv("APP_S2S_TLS_KEY_PATH", str(tls_certs["key"]))
        with pytest.raises(ValueError, match="s2s_tls_ca_cert_path"):
            Settings()

    def test_enabled_missing_cert(self, monkeypatch: pytest.MonkeyPatch, tls_certs: dict[str, Path]) -> None:
        monkeypatch.setenv("APP_S2S_TLS_ENABLED", "true")
        monkeypatch.setenv("APP_S2S_TLS_CA_CERT_PATH", str(tls_certs["ca"]))
        monkeypatch.setenv("APP_S2S_TLS_KEY_PATH", str(tls_certs["key"]))
        with pytest.raises(ValueError, match="s2s_tls_cert_path"):
            Settings()

    def test_enabled_missing_key(self, monkeypatch: pytest.MonkeyPatch, tls_certs: dict[str, Path]) -> None:
        monkeypatch.setenv("APP_S2S_TLS_ENABLED", "true")
        monkeypatch.setenv("APP_S2S_TLS_CA_CERT_PATH", str(tls_certs["ca"]))
        monkeypatch.setenv("APP_S2S_TLS_CERT_PATH", str(tls_certs["cert"]))
        with pytest.raises(ValueError, match="s2s_tls_key_path"):
            Settings()

    def test_enabled_all_paths_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_S2S_TLS_ENABLED", "true")
        with pytest.raises(ValueError, match="required paths are not set"):
            Settings()

    def test_enabled_nonexistent_file(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("APP_S2S_TLS_ENABLED", "true")
        monkeypatch.setenv("APP_S2S_TLS_CA_CERT_PATH", str(tmp_path / "nonexistent.pem"))
        monkeypatch.setenv("APP_S2S_TLS_CERT_PATH", str(tmp_path / "nonexistent.crt"))
        monkeypatch.setenv("APP_S2S_TLS_KEY_PATH", str(tmp_path / "nonexistent.key"))
        with pytest.raises(ValueError, match="file not found"):
            Settings()
