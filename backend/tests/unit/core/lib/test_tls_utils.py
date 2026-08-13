"""Tests for TLS utilities (build_integration_httpx_verify)."""

import ssl
import subprocess
import tempfile
from pathlib import Path

import pytest

from syntara.core.lib.tls_utils import build_integration_httpx_verify


@pytest.fixture(scope="module")
def sample_ca_cert() -> str:
    """Generate a valid self-signed CA certificate for testing."""
    with (
        tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as key_f,
        tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as cert_f,
    ):
        subprocess.run(  # noqa: S603
            [  # noqa: S607
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-keyout",
                key_f.name,
                "-out",
                cert_f.name,
                "-days",
                "1",
                "-nodes",
                "-subj",
                "/CN=test-nexus-ca",
            ],
            capture_output=True,
            check=True,
        )
        return Path(cert_f.name).read_text()


class TestBuildIntegrationHttpxVerify:
    """Tests for build_integration_httpx_verify()."""

    def test_defaults_return_true(self) -> None:
        """Default params (no skip, no CA cert) return True for standard verification."""
        result = build_integration_httpx_verify()
        assert result is True

    def test_insecure_skip_returns_false(self) -> None:
        """insecure_skip_tls_verify=True returns False (disable verification)."""
        result = build_integration_httpx_verify(insecure_skip_tls_verify=True)
        assert result is False

    def test_insecure_skip_overrides_ca_certificate(self, sample_ca_cert: str) -> None:
        """insecure_skip_tls_verify takes precedence over ca_certificate."""
        result = build_integration_httpx_verify(
            insecure_skip_tls_verify=True,
            ca_certificate=sample_ca_cert,
        )
        assert result is False

    def test_ca_certificate_returns_ssl_context(self, sample_ca_cert: str) -> None:
        """Custom CA certificate returns an ssl.SSLContext."""
        result = build_integration_httpx_verify(ca_certificate=sample_ca_cert)
        assert isinstance(result, ssl.SSLContext)

    @pytest.mark.parametrize("blank", ["", "   ", "  \n  "])
    def test_whitespace_only_ca_certificate_returns_true(self, blank: str) -> None:
        """Whitespace-only ca_certificate is treated as absent (returns True)."""
        result = build_integration_httpx_verify(ca_certificate=blank)
        assert result is True

    def test_invalid_ca_certificate_raises(self) -> None:
        """Invalid PEM data raises ssl.SSLError."""
        with pytest.raises(ssl.SSLError):
            build_integration_httpx_verify(ca_certificate="not-a-valid-cert")
