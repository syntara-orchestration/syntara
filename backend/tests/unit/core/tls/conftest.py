"""Shared fixtures for TLS unit tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from syntara.core.tls.http_client import build_internal_ssl_context
from syntara.core.tls.temporal import build_temporal_tls_config
from tests.fixtures.tls import generate_ca, generate_service_cert

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _clear_tls_caches() -> None:
    """Clear cached TLS configs between tests to ensure isolation."""
    build_internal_ssl_context.cache_clear()
    build_temporal_tls_config.cache_clear()


@pytest.fixture
def tls_certs(tmp_path: Path) -> dict[str, Path]:
    """Generate a CA and service certificate for testing."""
    ca_key, ca_cert = generate_ca(tmp_path)
    cert_path, key_path = generate_service_cert(tmp_path, ca_key, ca_cert)
    return {
        "ca": tmp_path / "ca.pem",
        "cert": cert_path,
        "key": key_path,
    }
