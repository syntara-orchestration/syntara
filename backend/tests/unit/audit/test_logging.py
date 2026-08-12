"""Unit tests for audit logging configuration.

Tests cover:
- Audit logger emits to stdout regardless of root logger level
- No propagation to root logger (prevents duplicate output)
- OTLP endpoint security validation
"""

import logging
from collections.abc import Generator
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from syntara.audit.logging import AUDIT_LOGGER_NAME, configure_audit_logging

MOCK_SECRET_ENCRYPTION_KEY = SecretStr("1" * 64)


@pytest.fixture(autouse=True)
def _reset_audit_logger() -> Generator[None, None, None]:
    """Reset audit logger handlers between tests to ensure isolation."""
    audit_logger = logging.getLogger(AUDIT_LOGGER_NAME)
    for handler in audit_logger.handlers[:]:
        audit_logger.removeHandler(handler)
    audit_logger.disabled = False

    yield

    for handler in audit_logger.handlers[:]:
        audit_logger.removeHandler(handler)
    audit_logger.disabled = False


class TestConfigureAuditLogging:
    """Tests for configure_audit_logging function."""

    def test_adds_stdout_handler(self) -> None:
        """configure_audit_logging adds a single stdout StreamHandler."""
        configure_audit_logging()

        audit_log = logging.getLogger(AUDIT_LOGGER_NAME)
        assert len(audit_log.handlers) == 1
        assert isinstance(audit_log.handlers[0], logging.StreamHandler)

    def test_no_propagation(self) -> None:
        """Audit logger does not propagate to root logger."""
        configure_audit_logging()

        audit_log = logging.getLogger(AUDIT_LOGGER_NAME)
        assert audit_log.propagate is False

    def test_emits_at_all_levels(self) -> None:
        """Audit events emit regardless of root logger level."""
        import io

        root_logger = logging.getLogger()
        original_level = root_logger.level

        try:
            root_logger.setLevel(logging.CRITICAL)

            with patch("sys.stderr", new=io.StringIO()) as mock_stderr:
                configure_audit_logging()

                audit_log = logging.getLogger(AUDIT_LOGGER_NAME)
                record = logging.LogRecord(
                    name=AUDIT_LOGGER_NAME,
                    level=logging.DEBUG,
                    pathname="test",
                    lineno=1,
                    msg="audit_event_debug",
                    args=(),
                    exc_info=None,
                )
                audit_log.handle(record)

                output = mock_stderr.getvalue()
                assert "audit_event_debug" in output
        finally:
            root_logger.setLevel(original_level)


class TestOtelEndpointValidation:
    """Tests for OTLP endpoint security validation."""

    def test_localhost_http_endpoint_allowed(self, monkeypatch) -> None:
        """HTTP endpoints are allowed for localhost."""
        from syntara.core.config.base import Settings

        monkeypatch.setenv("APP_OTEL_ENDPOINT", "http://localhost:4318/v1/logs")
        settings = Settings(secret_encryption_key=MOCK_SECRET_ENCRYPTION_KEY)
        assert settings.otel_endpoint == "http://localhost:4318/v1/logs"

    def test_localhost_ip_http_endpoint_allowed(self, monkeypatch) -> None:
        """HTTP endpoints are allowed for 127.0.0.1."""
        from syntara.core.config.base import Settings

        monkeypatch.setenv("APP_OTEL_ENDPOINT", "http://127.0.0.1:4318/v1/logs")
        settings = Settings(secret_encryption_key=MOCK_SECRET_ENCRYPTION_KEY)
        assert settings.otel_endpoint == "http://127.0.0.1:4318/v1/logs"

    def test_ipv6_localhost_http_endpoint_allowed(self, monkeypatch) -> None:
        """HTTP endpoints are allowed for IPv6 localhost (::1)."""
        from syntara.core.config.base import Settings

        monkeypatch.setenv("APP_OTEL_ENDPOINT", "http://[::1]:4318/v1/logs")
        settings = Settings(secret_encryption_key=MOCK_SECRET_ENCRYPTION_KEY)
        assert settings.otel_endpoint == "http://[::1]:4318/v1/logs"

    def test_cluster_internal_svc_http_endpoint_allowed(self, monkeypatch) -> None:
        """HTTP endpoints are allowed for Kubernetes *.svc.cluster.local service DNS names."""
        from syntara.core.config.base import Settings

        monkeypatch.setenv(
            "APP_OTEL_ENDPOINT",
            "http://ao-otel-collector.automation-orchestrator.svc.cluster.local:4318/v1/logs",
        )
        settings = Settings(secret_encryption_key=MOCK_SECRET_ENCRYPTION_KEY)
        assert "ao-otel-collector" in settings.otel_endpoint

    def test_cluster_internal_short_svc_http_endpoint_allowed(self, monkeypatch) -> None:
        """HTTP endpoints are allowed for short Kubernetes *.svc service DNS names."""
        from syntara.core.config.base import Settings

        monkeypatch.setenv(
            "APP_OTEL_ENDPOINT",
            "http://ao-otel-collector.automation-orchestrator.svc:4318/v1/logs",
        )
        settings = Settings(secret_encryption_key=MOCK_SECRET_ENCRYPTION_KEY)
        assert "ao-otel-collector" in settings.otel_endpoint

    def test_remote_https_endpoint_allowed(self, monkeypatch) -> None:
        """HTTPS endpoints are allowed for remote endpoints."""
        from syntara.core.config.base import Settings

        monkeypatch.setenv("APP_OTEL_ENDPOINT", "https://otlp.example.com:4318/v1/logs")
        settings = Settings(secret_encryption_key=MOCK_SECRET_ENCRYPTION_KEY)
        assert settings.otel_endpoint == "https://otlp.example.com:4318/v1/logs"

    def test_remote_http_endpoint_rejected(self, monkeypatch) -> None:
        """HTTP endpoints are rejected for remote endpoints."""
        import pytest
        from pydantic import ValidationError

        from syntara.core.config.base import Settings

        monkeypatch.setenv("APP_OTEL_ENDPOINT", "http://otlp.example.com:4318/v1/logs")
        with pytest.raises(ValidationError, match="Remote OTLP endpoints must use HTTPS"):
            Settings(secret_encryption_key=MOCK_SECRET_ENCRYPTION_KEY)

    def test_remote_http_ip_endpoint_rejected(self, monkeypatch) -> None:
        """HTTP endpoints are rejected for all non-loopback IP addresses, including public IPs."""
        import pytest
        from pydantic import ValidationError

        from syntara.core.config.base import Settings

        monkeypatch.setenv("APP_OTEL_ENDPOINT", "http://203.0.113.10:4318/v1/logs")
        with pytest.raises(ValidationError, match="Remote OTLP endpoints must use HTTPS"):
            Settings(secret_encryption_key=MOCK_SECRET_ENCRYPTION_KEY)

    def test_private_ip_http_endpoint_rejected(self, monkeypatch) -> None:
        """HTTP endpoints are rejected for RFC 1918 private IP addresses (not cluster-internal DNS)."""
        import pytest
        from pydantic import ValidationError

        from syntara.core.config.base import Settings

        monkeypatch.setenv("APP_OTEL_ENDPOINT", "http://192.168.1.100:4318/v1/logs")
        with pytest.raises(ValidationError, match="Remote OTLP endpoints must use HTTPS"):
            Settings(secret_encryption_key=MOCK_SECRET_ENCRYPTION_KEY)

    def test_localhost_bypass_with_subdomain_rejected(self, monkeypatch) -> None:
        """HTTP endpoint with localhost as subdomain is rejected (prevents bypass)."""
        import pytest
        from pydantic import ValidationError

        from syntara.core.config.base import Settings

        monkeypatch.setenv("APP_OTEL_ENDPOINT", "http://localhost.evil.com:4318/v1/logs")
        with pytest.raises(ValidationError, match="Remote OTLP endpoints must use HTTPS"):
            Settings(secret_encryption_key=MOCK_SECRET_ENCRYPTION_KEY)

    def test_single_label_svc_rejected(self, monkeypatch) -> None:
        """HTTP endpoint with single-label .svc hostname is rejected (not valid K8s service DNS)."""
        import pytest
        from pydantic import ValidationError

        from syntara.core.config.base import Settings

        monkeypatch.setenv("APP_OTEL_ENDPOINT", "http://evil.svc:4318/v1/logs")
        with pytest.raises(ValidationError, match="Remote OTLP endpoints must use HTTPS"):
            Settings(secret_encryption_key=MOCK_SECRET_ENCRYPTION_KEY)

    def test_loopback_lookalike_svc_rejected(self, monkeypatch) -> None:
        """HTTP endpoint with loopback-lookalike .svc hostname is rejected."""
        import pytest
        from pydantic import ValidationError

        from syntara.core.config.base import Settings

        monkeypatch.setenv("APP_OTEL_ENDPOINT", "http://127.0.0.1.namespace.svc:4318/v1/logs")
        with pytest.raises(ValidationError, match="Remote OTLP endpoints must use HTTPS"):
            Settings(secret_encryption_key=MOCK_SECRET_ENCRYPTION_KEY)

    def test_trailing_hyphen_svc_rejected(self, monkeypatch) -> None:
        """HTTP endpoint with trailing-hyphen label is rejected (violates RFC 1123)."""
        import pytest
        from pydantic import ValidationError

        from syntara.core.config.base import Settings

        monkeypatch.setenv("APP_OTEL_ENDPOINT", "http://service-.namespace.svc:4318/v1/logs")
        with pytest.raises(ValidationError, match="Remote OTLP endpoints must use HTTPS"):
            Settings(secret_encryption_key=MOCK_SECRET_ENCRYPTION_KEY)

    def test_unsupported_scheme_rejected(self, monkeypatch) -> None:
        """Endpoints with unsupported schemes are rejected."""
        import pytest
        from pydantic import ValidationError

        from syntara.core.config.base import Settings

        monkeypatch.setenv("APP_OTEL_ENDPOINT", "ftp://localhost:4318/v1/logs")
        with pytest.raises(ValidationError, match="Unsupported URL scheme"):
            Settings(secret_encryption_key=MOCK_SECRET_ENCRYPTION_KEY)
