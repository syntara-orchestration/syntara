"""Unit tests for Temporal TLS configuration builder."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from temporalio.service import TLSConfig

from syntara.core.config.base import Settings
from syntara.core.tls.temporal import build_temporal_tls_config

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager
    from pathlib import Path


class TestBuildTemporalTlsConfig:
    """Tests for build_temporal_tls_config()."""

    def test_disabled_returns_none(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        with override_settings(s2s_tls_enabled=False):
            assert build_temporal_tls_config() is None

    def test_enabled_returns_tls_config(
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
            result = build_temporal_tls_config()

        assert isinstance(result, TLSConfig)
        assert result.server_root_ca_cert == tls_certs["ca"].read_bytes()
        assert result.client_cert == tls_certs["cert"].read_bytes()
        assert result.client_private_key == tls_certs["key"].read_bytes()

    def test_default_is_disabled(self) -> None:
        settings = Settings()
        assert settings.s2s_tls_enabled is False
        assert settings.s2s_tls_ca_cert_path is None
        assert settings.s2s_tls_cert_path is None
        assert settings.s2s_tls_key_path is None


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
