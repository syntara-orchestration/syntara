"""Unit tests for application configuration."""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

import pytest
from pydantic import HttpUrl, ValidationError

from syntara.core.config.base import Settings

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager
    from pathlib import Path


def test_settings_requires_app_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that settings only reads environment variables with APP_ prefix."""
    monkeypatch.setenv("APP_OPENROUTER_MODEL", "prefixed-model")

    settings = Settings()

    assert settings.openrouter_model == "prefixed-model"


# =============================================================================
# DatabaseSettings Tests
# =============================================================================


class TestDatabaseSettings:
    """Tests for DatabaseSettings configuration."""

    def test_database_defaults(self) -> None:
        """Test default database configuration values."""
        settings = Settings()
        assert settings.db_user == "admin"
        assert settings.db_password.get_secret_value() == "admin"
        assert settings.db_host == "localhost"
        assert settings.db_port == 5432
        assert settings.db_name == "syntara_api"
        assert settings.db_pool_size == 10
        assert settings.db_max_overflow == 20
        assert settings.db_pool_timeout_seconds == 30.0

    def test_database_url_computed_field(self) -> None:
        """Test that database_url is correctly computed from components."""
        settings = Settings()
        url = settings.database_url
        assert url.drivername == "postgresql+asyncpg"
        assert url.username == "admin"
        assert url.host == "localhost"
        assert url.port == 5432
        assert url.database == "syntara_api"

    def test_database_url_with_custom_values(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test database_url with custom configuration values."""
        from pydantic import SecretStr

        from syntara.core.config.base import get_settings

        with override_settings(
            db_user="testuser",
            db_password=SecretStr("testpass"),
            db_host="dbserver",
            db_port=5433,
            db_name="testdb",
        ):
            url = get_settings().database_url
            assert url.drivername == "postgresql+asyncpg"
            assert url.username == "testuser"
            assert url.host == "dbserver"
            assert url.port == 5433
            assert url.database == "testdb"

    def test_database_port_validation_too_low(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that database port validates within valid range."""
        monkeypatch.setenv("APP_DB_PORT", "0")
        with pytest.raises(ValueError, match="greater than or equal to 1"):
            Settings()

    def test_database_port_validation_too_high(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that database port validates within valid range."""
        monkeypatch.setenv("APP_DB_PORT", "70000")
        with pytest.raises(ValueError, match="less than or equal to 65535"):
            Settings()

    def test_database_url_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that APP_DATABASE_URL overrides component-based URL."""
        override_url = "postgresql+asyncpg://prod:s3cret@db.example.com:5432/proddb"
        monkeypatch.setenv("APP_DATABASE_URL", override_url)
        settings = Settings()
        url = settings.database_url
        assert url.drivername == "postgresql+asyncpg"
        assert url.username == "prod"
        assert url.host == "db.example.com"
        assert url.database == "proddb"

    def test_database_pool_settings_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test database pool settings can be configured via environment."""
        monkeypatch.setenv("APP_DB_POOL_SIZE", "25")
        monkeypatch.setenv("APP_DB_MAX_OVERFLOW", "10")
        monkeypatch.setenv("APP_DB_POOL_TIMEOUT_SECONDS", "45")
        settings = Settings()
        assert settings.db_pool_size == 25
        assert settings.db_max_overflow == 10
        assert settings.db_pool_timeout_seconds == 45

    def test_database_pool_size_validation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that database pool size must be at least 1."""
        monkeypatch.setenv("APP_DB_POOL_SIZE", "0")
        with pytest.raises(ValueError, match="greater than or equal to 1"):
            Settings()

    def test_database_max_overflow_validation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that database max overflow cannot be negative."""
        monkeypatch.setenv("APP_DB_MAX_OVERFLOW", "-1")
        with pytest.raises(ValueError, match="greater than or equal to 0"):
            Settings()

    def test_database_pool_timeout_validation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that database pool timeout must be positive."""
        monkeypatch.setenv("APP_DB_POOL_TIMEOUT_SECONDS", "0")
        with pytest.raises(ValueError, match="greater than 0"):
            Settings()


# =============================================================================
# DatabaseSettings SSL Tests
# =============================================================================


class TestDatabaseSSLSettings:
    """Tests for DatabaseSettings SSL configuration."""

    def test_ssl_defaults(self) -> None:
        settings = Settings()
        assert settings.db_ssl_mode == "prefer"
        assert settings.db_ssl_root_cert is None
        assert settings.db_ssl_cert is None
        assert settings.db_ssl_key is None

    def test_ssl_mode_from_env(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        cert_file = tmp_path / "ca.pem"
        cert_file.write_text("fake cert")
        monkeypatch.setenv("APP_DB_SSL_MODE", "verify-full")
        monkeypatch.setenv("APP_DB_SSL_ROOT_CERT", str(cert_file))
        settings = Settings()
        assert settings.db_ssl_mode == "verify-full"

    def test_ssl_mode_case_insensitive(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        cert_file = tmp_path / "ca.pem"
        cert_file.write_text("fake cert")
        monkeypatch.setenv("APP_DB_SSL_MODE", "VERIFY-FULL")
        monkeypatch.setenv("APP_DB_SSL_ROOT_CERT", str(cert_file))
        settings = Settings()
        assert settings.db_ssl_mode == "verify-full"

    @pytest.mark.parametrize("mode", ["disable", "allow", "prefer", "require"])
    def test_ssl_mode_valid_values(self, monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
        monkeypatch.setenv("APP_DB_SSL_MODE", mode)
        settings = Settings()
        assert settings.db_ssl_mode == mode

    @pytest.mark.parametrize("mode", ["verify-ca", "verify-full"])
    def test_ssl_mode_verify_with_root_cert(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mode: str) -> None:
        cert_file = tmp_path / "ca.pem"
        cert_file.write_text("fake cert")
        monkeypatch.setenv("APP_DB_SSL_MODE", mode)
        monkeypatch.setenv("APP_DB_SSL_ROOT_CERT", str(cert_file))
        settings = Settings()
        assert settings.db_ssl_mode == mode

    def test_ssl_mode_invalid_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_DB_SSL_MODE", "invalid")
        with pytest.raises(ValidationError, match="Invalid SSL mode"):
            Settings()

    def test_ssl_root_cert_from_env(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        cert_file = tmp_path / "ca.pem"
        cert_file.write_text("fake cert")
        monkeypatch.setenv("APP_DB_SSL_ROOT_CERT", str(cert_file))
        monkeypatch.setenv("APP_DB_SSL_MODE", "verify-full")
        settings = Settings()
        assert settings.db_ssl_root_cert == str(cert_file)

    def test_ssl_client_cert_and_key_from_env(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        cert_file = tmp_path / "client.pem"
        key_file = tmp_path / "client.key"
        cert_file.write_text("fake cert")
        key_file.write_text("fake key")
        monkeypatch.setenv("APP_DB_SSL_CERT", str(cert_file))
        monkeypatch.setenv("APP_DB_SSL_KEY", str(key_file))
        monkeypatch.setenv("APP_DB_SSL_MODE", "require")
        settings = Settings()
        assert settings.db_ssl_cert == str(cert_file)
        assert settings.db_ssl_key == str(key_file)

    def test_ssl_cert_path_validation_nonexistent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_DB_SSL_ROOT_CERT", "/nonexistent/ca.pem")
        monkeypatch.setenv("APP_DB_SSL_MODE", "verify-full")
        with pytest.raises(ValidationError, match=r"SSL .* file not found"):
            Settings()

    def test_database_url_override_takes_precedence(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        cert_file = tmp_path / "ca.pem"
        cert_file.write_text("fake cert")
        override_url = "postgresql+asyncpg://u:p@h:5432/d"
        monkeypatch.setenv("APP_DATABASE_URL", override_url)
        monkeypatch.setenv("APP_DB_SSL_MODE", "verify-full")
        monkeypatch.setenv("APP_DB_SSL_ROOT_CERT", str(cert_file))
        settings = Settings()
        url = settings.database_url
        assert url.host == "h"
        assert url.database == "d"

    def test_ssl_key_without_cert_rejected(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        key_file = tmp_path / "client.key"
        key_file.write_text("fake key")
        monkeypatch.setenv("APP_DB_SSL_KEY", str(key_file))
        monkeypatch.setenv("APP_DB_SSL_MODE", "require")
        with pytest.raises(ValidationError, match="requires a client certificate"):
            Settings()

    def test_ssl_client_certs_with_disable_rejected(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        cert_file = tmp_path / "client.pem"
        key_file = tmp_path / "client.key"
        cert_file.write_text("fake cert")
        key_file.write_text("fake key")
        monkeypatch.setenv("APP_DB_SSL_MODE", "disable")
        monkeypatch.setenv("APP_DB_SSL_CERT", str(cert_file))
        monkeypatch.setenv("APP_DB_SSL_KEY", str(key_file))
        with pytest.raises(ValidationError, match="only supported with"):
            Settings()

    def test_ssl_client_certs_with_prefer_rejected(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        cert_file = tmp_path / "client.pem"
        key_file = tmp_path / "client.key"
        cert_file.write_text("fake cert")
        key_file.write_text("fake key")
        monkeypatch.setenv("APP_DB_SSL_MODE", "prefer")
        monkeypatch.setenv("APP_DB_SSL_CERT", str(cert_file))
        monkeypatch.setenv("APP_DB_SSL_KEY", str(key_file))
        with pytest.raises(ValidationError, match="only supported with"):
            Settings()

    def test_ssl_verify_full_without_root_cert_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_DB_SSL_MODE", "verify-full")
        with pytest.raises(ValidationError, match="requires ssl_root_cert"):
            Settings()


# =============================================================================
# CacheSettings Tests
# =============================================================================


class TestCacheSettings:
    """Tests for CacheSettings (Redis) configuration."""

    def test_cache_defaults(self) -> None:
        """Default pool size is 50 — large enough for concurrent workflow workers."""
        settings = Settings()
        assert settings.cache_host == "localhost"
        assert settings.cache_port == 6379
        assert settings.cache_connection_pool_size == 50

    def test_cache_connection_pool_size_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_CACHE_CONNECTION_POOL_SIZE", "100")
        settings = Settings()
        assert settings.cache_connection_pool_size == 100

    @pytest.mark.parametrize("pool_size", ["0", "-1", "-50"])
    def test_cache_connection_pool_size_rejects_non_positive(
        self, monkeypatch: pytest.MonkeyPatch, pool_size: str
    ) -> None:
        monkeypatch.setenv("APP_CACHE_CONNECTION_POOL_SIZE", pool_size)
        with pytest.raises(ValidationError, match="must be at least 1"):
            Settings()

    def test_cache_connection_pool_size_accepts_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_CACHE_CONNECTION_POOL_SIZE", "1")
        settings = Settings()
        assert settings.cache_connection_pool_size == 1


# =============================================================================
# AuditDatabaseSettings SSL Tests
# =============================================================================


# =============================================================================
# ServerSettings Tests
# =============================================================================


class TestServerSettings:
    """Tests for ServerSettings configuration."""

    def test_server_defaults(self) -> None:
        """Test default server configuration values."""
        settings = Settings()
        assert settings.server_host == "0.0.0.0"  # noqa: S104
        assert settings.server_port == 8000
        assert settings.server_reload is False

    def test_product_name_defaults_to_community(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Upstream/community build: product_name is 'Syntara' when APP_PRODUCT_NAME is unset."""
        monkeypatch.delenv("APP_PRODUCT_NAME", raising=False)
        settings = Settings(_env_file=None)
        assert settings.product_name == "Syntara"

    def test_product_name_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Product build: product_name uses APP_PRODUCT_NAME when set."""
        monkeypatch.setenv("APP_PRODUCT_NAME", "Custom Product")
        settings = Settings(_env_file=None)
        assert settings.product_name == "Custom Product"

    def test_product_name_rejects_invalid_characters(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Product name must match the alphanumeric+space pattern."""
        monkeypatch.setenv("APP_PRODUCT_NAME", "Bad<Name>!")
        with pytest.raises(ValidationError, match="pattern"):
            Settings(_env_file=None)

    def test_server_settings_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test server settings can be configured via environment."""
        monkeypatch.setenv("APP_SERVER_HOST", "127.0.0.1")
        monkeypatch.setenv("APP_SERVER_PORT", "9000")
        monkeypatch.setenv("APP_SERVER_RELOAD", "true")
        settings = Settings()
        assert settings.server_host == "127.0.0.1"
        assert settings.server_port == 9000
        assert settings.server_reload is True

    def test_cors_settings_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test CORS settings can be configured via environment."""
        monkeypatch.setenv("APP_CORS_ALLOW_ORIGINS", '["http://localhost:3000", "http://example.com"]')
        monkeypatch.setenv("APP_CORS_ALLOW_CREDENTIALS", "false")
        settings = Settings()
        assert settings.cors_allow_origins == ["http://localhost:3000", "http://example.com"]
        assert settings.cors_allow_credentials is False

    def test_server_port_validation_too_low(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that server port validates within valid range."""
        monkeypatch.setenv("APP_SERVER_PORT", "0")
        with pytest.raises(ValueError, match="greater than or equal to 1"):
            Settings()

    def test_server_port_validation_too_high(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that server port validates within valid range."""
        monkeypatch.setenv("APP_SERVER_PORT", "70000")
        with pytest.raises(ValueError, match="less than or equal to 65535"):
            Settings()

    def test_server_public_url_default_is_none(self) -> None:
        """Test that server_public_url defaults to None."""
        settings = Settings()
        assert settings.server_public_url is None

    def test_jwt_issuer_uses_server_public_url(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that jwt_issuer returns server_public_url when set."""
        with override_settings(
            server_public_url=HttpUrl("https://example.com:8000"),
        ):
            from syntara.core.config.base import get_settings

            assert get_settings().jwt_issuer == "https://example.com:8000"

    def test_jwt_issuer_strips_trailing_slash(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that jwt_issuer strips trailing slash from server_public_url."""
        with override_settings(
            server_public_url=HttpUrl("https://example.com/"),
        ):
            from syntara.core.config.base import get_settings

            assert get_settings().jwt_issuer == "https://example.com"

    def test_jwt_issuer_falls_back_to_constructed_url(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that jwt_issuer uses server_scheme://server_host:server_port when no public URL."""
        with override_settings(
            server_public_url=None,
            server_scheme="http",
            server_host="localhost",
            server_port=9000,
        ):
            from syntara.core.config.base import get_settings

            assert get_settings().jwt_issuer == "http://localhost:9000"

    def test_post_logout_redirect_uri_priority(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test post_logout_redirect_uri priority: explicit > public URL > constructed."""
        with override_settings(
            server_public_url=HttpUrl("https://example.com"),
            oidc_post_logout_redirect_uri="https://custom.example.com",
        ):
            from syntara.core.config.base import get_settings

            assert get_settings().post_logout_redirect_uri == "https://custom.example.com"

    def test_post_logout_redirect_uri_uses_public_url(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test post_logout_redirect_uri uses server_public_url when explicit URI is not set."""
        with override_settings(
            server_public_url=HttpUrl("https://example.com"),
        ):
            from syntara.core.config.base import get_settings

            assert get_settings().post_logout_redirect_uri == "https://example.com"

    def test_server_public_url_empty_string_treated_as_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that empty string APP_SERVER_PUBLIC_URL is treated as None."""
        monkeypatch.setenv("APP_SERVER_PUBLIC_URL", "")
        settings = Settings()
        assert settings.server_public_url is None


# =============================================================================
# LoggingSettings Tests
# =============================================================================


class TestLoggingSettings:
    """Tests for LoggingSettings configuration."""

    def test_logging_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test default logging configuration values."""
        from syntara.core.config.base import get_settings

        # Clear env vars to test pure defaults
        monkeypatch.delenv("APP_FALLBACK_LOG_LEVEL", raising=False)
        monkeypatch.delenv("APP_NAME", raising=False)
        monkeypatch.delenv("APP_LOG_OUTPUT_FORMAT", raising=False)
        get_settings.cache_clear()

        try:
            # _env_file=None skips .env file loading (pydantic-settings feature)
            settings = Settings(_env_file=None)
            assert settings.fallback_log_level == "INFO"
        finally:
            get_settings.cache_clear()

    def test_fallback_log_level_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test fallback log level can be configured via environment."""
        monkeypatch.setenv("APP_FALLBACK_LOG_LEVEL", "DEBUG")
        settings = Settings()
        assert settings.fallback_log_level == "DEBUG"

    def test_fallback_log_level_rejects_invalid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that invalid log levels are rejected at config time."""
        monkeypatch.setenv("APP_FALLBACK_LOG_LEVEL", "TRACE")
        with pytest.raises(ValidationError):
            Settings()


# =============================================================================
# TemporalSettings Tests
# =============================================================================


class TestTemporalSettings:
    """Tests for TemporalSettings configuration."""

    def test_temporal_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test default Temporal configuration values."""
        from syntara.core.config.base import get_settings

        # Clear env vars to test pure defaults
        monkeypatch.delenv("APP_TASK_QUEUE", raising=False)
        monkeypatch.delenv("APP_TEMPORAL_ADDRESS", raising=False)
        monkeypatch.delenv("APP_TEMPORAL_NAMESPACE", raising=False)
        monkeypatch.delenv("APP_MAX_LOOP_ITERATIONS", raising=False)
        monkeypatch.delenv("APP_NAME", raising=False)
        get_settings.cache_clear()

        try:
            # _env_file=None skips .env file loading (pydantic-settings feature)
            settings = Settings(_env_file=None)
            assert settings.temporal_address == "localhost:7233"
            assert settings.temporal_namespace == "default"
            assert settings.task_queue == "orchestrator-workflow-queue"
            assert settings.max_cached_workflows == 20
            assert settings.max_concurrent_workflow_tasks == 50
            assert settings.max_concurrent_activities == 50
            assert settings.background_worker_max_concurrent_activities == 10
        finally:
            get_settings.cache_clear()

    def test_temporal_settings_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test Temporal settings can be configured via environment."""
        monkeypatch.setenv("APP_TEMPORAL_ADDRESS", "temporal.example.com:7233")
        monkeypatch.setenv("APP_TEMPORAL_NAMESPACE", "production")
        monkeypatch.setenv("APP_TASK_QUEUE", "prod-queue")
        monkeypatch.setenv("APP_MAX_CACHED_WORKFLOWS", "100")
        monkeypatch.setenv("APP_MAX_CONCURRENT_WORKFLOW_TASKS", "75")
        monkeypatch.setenv("APP_MAX_CONCURRENT_ACTIVITIES", "25")
        monkeypatch.setenv("APP_BACKGROUND_WORKER_MAX_CONCURRENT_ACTIVITIES", "8")
        settings = Settings()
        assert settings.temporal_address == "temporal.example.com:7233"
        assert settings.temporal_namespace == "production"
        assert settings.task_queue == "prod-queue"
        assert settings.max_cached_workflows == 100
        assert settings.max_concurrent_workflow_tasks == 75
        assert settings.max_concurrent_activities == 25
        assert settings.background_worker_max_concurrent_activities == 8

    def test_temporal_concurrency_rejects_zero(self) -> None:
        """Test that concurrency controls reject values less than 1."""
        with pytest.raises(ValidationError):
            Settings(_env_file=None, max_cached_workflows=0)
        with pytest.raises(ValidationError):
            Settings(_env_file=None, max_concurrent_workflow_tasks=0)
        with pytest.raises(ValidationError):
            Settings(_env_file=None, max_concurrent_activities=0)
        with pytest.raises(ValidationError):
            Settings(_env_file=None, background_worker_max_concurrent_activities=0)


# =============================================================================
# ServiceIdentitySettings Tests
# =============================================================================


class TestServiceIdentitySettings:
    """Tests for service_identity computed property."""

    def test_service_identity_raises_when_tls_disabled(self) -> None:
        """Test that service_identity raises RuntimeError when S2S TLS is disabled."""
        settings = Settings(_env_file=None, s2s_tls_enabled=False)
        with pytest.raises(RuntimeError, match="service_identity requires S2S TLS"):
            _ = settings.service_identity


# =============================================================================
# WorkflowEngineSettings Tests
# =============================================================================


class TestWorkflowEngineSettings:
    """Tests for WorkflowEngineSettings configuration."""

    def test_workflow_engine_defaults(self) -> None:
        """Test default workflow engine configuration values."""
        settings = Settings()
        assert settings.script_cleanup_terminate_timeout == pytest.approx(1.0)
        assert settings.script_cleanup_kill_timeout == pytest.approx(0.5)
        assert settings.max_env_var_length == 32768
        assert str(settings.agent_orchestrator_base_url) == "http://localhost:8000/api/v1"

    def test_workflow_engine_settings_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test workflow engine settings can be configured via environment."""
        monkeypatch.setenv("APP_AGENT_ORCHESTRATOR_BASE_URL", "http://agent.example.com/api/v1")
        settings = Settings()
        assert str(settings.agent_orchestrator_base_url) == "http://agent.example.com/api/v1"


# =============================================================================
# RetrieverServiceSettings Tests
# =============================================================================


class TestRetrieverServiceSettings:
    """Tests for RetrieverServiceSettings configuration."""

    def test_keyword_ranking_weights_sum_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test successful validation when keyword ranking weights sum to valid value."""
        settings = Settings()
        assert settings.retriever_keyword_ranking_term_frequency == pytest.approx(0.4)
        assert settings.retriever_keyword_ranking_filename_match == pytest.approx(0.25)
        assert settings.retriever_keyword_ranking_content_density == pytest.approx(0.15)
        assert settings.retriever_keyword_ranking_proximity_bonus == pytest.approx(0.05)
        assert settings.retriever_keyword_ranking_exact_match_bonus == pytest.approx(0.1)
        assert settings.retriever_keyword_ranking_fuzzy_match_bonus == pytest.approx(0.05)

        monkeypatch.setenv("APP_RETRIEVER_KEYWORD_RANKING_TERM_FREQUENCY", "0.3")
        monkeypatch.setenv("APP_RETRIEVER_KEYWORD_RANKING_FILENAME_MATCH", "0.2")
        monkeypatch.setenv("APP_RETRIEVER_KEYWORD_RANKING_CONTENT_DENSITY", "0.15")
        monkeypatch.setenv("APP_RETRIEVER_KEYWORD_RANKING_PROXIMITY_BONUS", "0.1")
        monkeypatch.setenv("APP_RETRIEVER_KEYWORD_RANKING_EXACT_MATCH_BONUS", "0.04")
        monkeypatch.setenv("APP_RETRIEVER_KEYWORD_RANKING_FUZZY_MATCH_BONUS", "0.01")
        settings = Settings()
        assert settings.retriever_keyword_ranking_term_frequency == pytest.approx(0.3)
        assert settings.retriever_keyword_ranking_filename_match == pytest.approx(0.2)
        assert settings.retriever_keyword_ranking_content_density == pytest.approx(0.15)
        assert settings.retriever_keyword_ranking_proximity_bonus == pytest.approx(0.1)
        assert settings.retriever_keyword_ranking_exact_match_bonus == pytest.approx(0.04)
        assert settings.retriever_keyword_ranking_fuzzy_match_bonus == pytest.approx(0.01)

    def test_keyword_ranking_weights_sum_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test validation failure when keyword ranking weights sum exceeds valid range."""
        monkeypatch.setenv("APP_RETRIEVER_KEYWORD_RANKING_TERM_FREQUENCY", "0.5")
        monkeypatch.setenv("APP_RETRIEVER_KEYWORD_RANKING_FILENAME_MATCH", "0.4")
        monkeypatch.setenv("APP_RETRIEVER_KEYWORD_RANKING_CONTENT_DENSITY", "0.3")
        monkeypatch.setenv("APP_RETRIEVER_KEYWORD_RANKING_PROXIMITY_BONUS", "0.2")
        monkeypatch.setenv("APP_RETRIEVER_KEYWORD_RANKING_EXACT_MATCH_BONUS", "0.1")
        monkeypatch.setenv("APP_RETRIEVER_KEYWORD_RANKING_FUZZY_MATCH_BONUS", "0.05")

        with pytest.raises(ValueError) as exc_info:
            Settings()

        error_msg = str(exc_info.value)
        assert "Keyword ranking weights must sum to between 0.0 and 1.0" in error_msg
        assert "but sum to 1.550" in error_msg
        assert "retriever_keyword_ranking_term_frequency" in error_msg
        assert "retriever_keyword_ranking_filename_match" in error_msg
        assert "retriever_keyword_ranking_content_density" in error_msg
        assert "retriever_keyword_ranking_proximity_bonus" in error_msg
        assert "retriever_keyword_ranking_exact_match_bonus" in error_msg
        assert "retriever_keyword_ranking_fuzzy_match_bonus" in error_msg


# =============================================================================
# AdapterRetrySettings Tests
# =============================================================================


class TestAdapterRetrySettings:
    """Tests for AdapterRetrySettings configuration."""

    def test_adapter_backoff_relationship_validation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that max_backoff must be >= initial_backoff."""
        monkeypatch.setenv("APP_ADAPTER_INITIAL_BACKOFF_SECONDS", "10.0")
        monkeypatch.setenv("APP_ADAPTER_MAX_BACKOFF_SECONDS", "2.0")

        with pytest.raises(ValueError, match="adapter_max_backoff_seconds"):
            Settings()


# =============================================================================
# CORS Production Validation Tests (AAP-71274)
# =============================================================================


class TestCorsProductionValidation:
    """Tests for CORS origin validation in production mode."""

    def test_warns_when_cors_origins_empty_in_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should warn when server_scheme=https but cors_allow_origins is empty."""
        monkeypatch.setenv("APP_SERVER_SCHEME", "https")
        monkeypatch.setenv("APP_CORS_ALLOW_ORIGINS", "[]")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Settings()

        cors_warnings = [x for x in w if "cors_allow_origins is empty" in str(x.message)]
        assert len(cors_warnings) == 1

    def test_no_warning_when_cors_origins_set_in_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should not warn when server_scheme=https and cors_allow_origins is configured."""
        monkeypatch.setenv("APP_SERVER_SCHEME", "https")
        monkeypatch.setenv("APP_CORS_ALLOW_ORIGINS", '["https://app.example.com"]')

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Settings()

        cors_warnings = [x for x in w if "cors_allow_origins is empty" in str(x.message)]
        assert len(cors_warnings) == 0

    def test_no_warning_when_server_scheme_http(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should not warn when server_scheme=http (local dev mode)."""
        monkeypatch.setenv("APP_SERVER_SCHEME", "http")
        monkeypatch.setenv("APP_CORS_ALLOW_ORIGINS", "[]")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Settings()

        cors_warnings = [x for x in w if "cors_allow_origins is empty" in str(x.message)]
        assert len(cors_warnings) == 0

    def test_cookie_secure_derived_from_https(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """cookie_secure should be True when server_scheme is https."""
        monkeypatch.setenv("APP_SERVER_SCHEME", "https")
        settings = Settings()
        assert settings.cookie_secure is True

    def test_cookie_secure_derived_from_http(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """cookie_secure should be False when server_scheme is http."""
        monkeypatch.setenv("APP_SERVER_SCHEME", "http")
        settings = Settings()
        assert settings.cookie_secure is False


# =============================================================================
# FileStorageSettings Tests
# =============================================================================


class TestFileStorageSettings:
    """Tests for FileStorageSettings configuration."""

    def test_file_storage_defaults(self) -> None:
        """Test default file storage configuration values."""
        settings = Settings()
        assert settings.s3_endpoint_url is None
        assert settings.s3_bucket_name == "orchestrator-files"
        assert settings.s3_region == "us-east-1"
        assert settings.s3_access_key_id is None
        assert settings.s3_secret_access_key is None
        assert settings.s3_use_path_style is True

    def test_file_storage_s3_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test S3 configuration via environment variables."""
        monkeypatch.setenv("APP_S3_ENDPOINT_URL", "https://s3.openshift-storage.svc")
        monkeypatch.setenv("APP_S3_BUCKET_NAME", "my-bucket")
        monkeypatch.setenv("APP_S3_REGION", "eu-west-1")
        monkeypatch.setenv("APP_S3_ACCESS_KEY_ID", "AKIAIOSFODNN7EXAMPLE")
        monkeypatch.setenv("APP_S3_SECRET_ACCESS_KEY", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY")
        monkeypatch.setenv("APP_S3_USE_PATH_STYLE", "false")

        settings = Settings()
        assert settings.s3_endpoint_url == "https://s3.openshift-storage.svc"
        assert settings.s3_bucket_name == "my-bucket"
        assert settings.s3_region == "eu-west-1"
        assert settings.s3_access_key_id is not None
        assert settings.s3_access_key_id.get_secret_value() == "AKIAIOSFODNN7EXAMPLE"
        assert settings.s3_secret_access_key is not None
        assert settings.s3_secret_access_key.get_secret_value() == "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        assert settings.s3_use_path_style is False

    def test_s3_endpoint_url_empty_string_treated_as_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that empty string APP_S3_ENDPOINT_URL is treated as None."""
        monkeypatch.setenv("APP_S3_ENDPOINT_URL", "")
        settings = Settings()
        assert settings.s3_endpoint_url is None

    def test_s3_endpoint_url_whitespace_treated_as_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that whitespace-only APP_S3_ENDPOINT_URL is treated as None."""
        monkeypatch.setenv("APP_S3_ENDPOINT_URL", "  ")
        settings = Settings()
        assert settings.s3_endpoint_url is None

    def test_s3_ca_bundle_empty_string_treated_as_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that empty string APP_S3_CA_BUNDLE is treated as None."""
        monkeypatch.setenv("APP_S3_CA_BUNDLE", "")
        settings = Settings()
        assert settings.s3_ca_bundle is None
