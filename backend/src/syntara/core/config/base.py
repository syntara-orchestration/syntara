"""Application configuration using Pydantic Settings.

This module provides centralized configuration management using Pydantic Settings,
which offers:
- Type validation
- Environment variable loading with .env file support
- Clear defaults and documentation
- IDE autocomplete support

Usage:
    from syntara.core.config.base import get_settings

    settings = get_settings()
    llm = get_openrouter_llm(api_key="<your-api-key>")
"""

import os
import re
import tempfile
import warnings
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, Self
from urllib.parse import urlparse

from pydantic import Field, HttpUrl, SecretStr, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

from syntara.core.constants import RetrieverServiceDefaults
from syntara.core.exceptions import SafeValueError

# =============================================================================
# LLM Provider Configuration
# =============================================================================


class OpenRouterSettings(BaseSettings):
    """OpenRouter LLM configuration settings.

    OpenRouter provides API gateway to multiple LLMs (Claude, GPT-4, Gemini, etc.).
    Get your API key from: https://openrouter.ai/keys

    Note: This class should not be instantiated directly. Use Settings via get_settings().
    """

    openrouter_model: str = Field(
        default="anthropic/claude-sonnet-4",
        description="Default OpenRouter model to use (e.g., anthropic/claude-sonnet-4, openai/gpt-4o)",
    )

    openrouter_base_url: HttpUrl = Field(  # type: ignore[assignment]
        default="https://openrouter.ai/api/v1",
        description="OpenRouter API base URL",
    )


# =============================================================================
# File Upload Configuration
# =============================================================================


class FileUploadSettings(BaseSettings):
    """File upload configuration settings.

    Settings for file attachment support in invocations.

    Note: This class should not be instantiated directly. Use Settings via get_settings().
    """

    file_upload_max_size_mb: int = Field(
        default=10,
        description="Maximum file size in MB per file",
    )

    file_upload_max_files: int = Field(
        default=10,
        description="Maximum number of files per invocation",
    )

    file_upload_allowed_mime_types: list[str] = Field(
        default=[
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "text/plain",
            "text/markdown",
        ],
        description="Allowed MIME types for file uploads",
    )


# =============================================================================
# Document Conversion Configuration
# =============================================================================


class DocumentConversionSettings(BaseSettings):
    """Document conversion configuration settings.

    Settings specific to document conversion operations.
    Builds upon FileUploadSettings for consistency.

    Note: This class should not be instantiated directly. Use Settings via get_settings().
    """

    document_conversion_temp_dir: str = Field(
        default_factory=tempfile.gettempdir,
        description="Temporary directory for conversion operations",
    )


# =============================================================================
# File Storage Backend Configuration
# =============================================================================


class FileStorageSettings(BaseSettings):
    """S3-compatible file storage configuration.

    S3 credentials are injected via K8s secrets in production.
    If S3 is not configured (s3_endpoint_url is None), file uploads
    are disabled and return 503.

    Note: This class should not be instantiated directly. Use Settings via get_settings().
    """

    s3_endpoint_url: str | None = Field(
        default=None,
        description="S3-compatible endpoint URL (e.g., ODF, AWS, MinIO)",
    )

    s3_bucket_name: str = Field(
        default="orchestrator-files",
        description="S3 bucket for file storage",
    )

    s3_region: str = Field(
        default="us-east-1",
        description="S3 region",
    )

    s3_access_key_id: SecretStr | None = Field(
        default=None,
        description="S3 access key — set via APP_S3_ACCESS_KEY_ID",
    )

    s3_secret_access_key: SecretStr | None = Field(
        default=None,
        description="S3 secret key — set via APP_S3_SECRET_ACCESS_KEY",
    )

    s3_verify_ssl: bool = Field(
        default=True,
        description="Verify TLS certificate for S3 endpoint; disable only for development",
    )

    s3_ca_bundle: str | None = Field(
        default=None,
        description="Path to CA bundle for S3 endpoint TLS verification (e.g. OCP cluster CA)",
    )

    s3_use_path_style: bool = Field(
        default=True,
        description="Use path-style S3 addressing (required for ODF/NooBaa/Ceph)",
    )

    file_multipart_cleanup_threshold_hours: int = Field(
        default=24,
        description="Hours after which incomplete S3 multipart uploads are aborted",
        ge=1,
    )

    file_cleanup_interval_seconds: float = Field(
        default=3600.0,
        description="Seconds between periodic file cleanup cycles",
        gt=0,
    )

    file_cleanup_batch_size: int = Field(
        default=1000,
        description="Maximum number of expired files to process per cleanup batch",
        ge=1,
    )

    @field_validator("s3_endpoint_url", "s3_ca_bundle", mode="before")
    @classmethod
    def _empty_s3_string_to_none(cls, v: str | None) -> str | None:
        if v is not None and v.strip() == "":
            return None
        return v


# =============================================================================
# API Validation Configuration
# =============================================================================


class OpenAPIValidationSettings(BaseSettings):
    """OpenAPI schema validation configuration settings.

    This configuration controls the validation of FastAPI routes against
    OpenAPI schema specifications. This is NOT related to OpenRouter (the LLM service).

    Note: This class should not be instantiated directly. Use Settings via get_settings().
    """

    openapi_validation_enabled: bool = Field(
        default=True,
        description="Enable OpenAPI schema validation at startup",
    )


# =============================================================================
# API Documentation Endpoint Configuration
# =============================================================================


class APIDocsSettings(BaseSettings):
    """API documentation endpoint configuration.

    Controls whether Swagger UI (/docs), ReDoc (/redoc), and the raw
    OpenAPI JSON (/openapi.json) endpoints are served. Disabled by
    default so production deployments do not expose the API schema.

    Note: This class should not be instantiated directly. Use Settings via get_settings().
    """

    enable_api_docs: bool = Field(
        default=False,
        description="Serve OpenAPI documentation endpoints (/docs, /redoc, /openapi.json). "
        "Enable for development environments.",
    )

    enable_try_it_out: bool = Field(
        default=False,
        description="Enable the Swagger UI 'Try it out' button for interactive API execution. "
        "When False, the button is hidden so docs remain browse-only. "
        "Only effective when enable_api_docs is True.",
    )


# =============================================================================
# Router Discovery Configuration
# =============================================================================


class RouterDiscoverySettings(BaseSettings):
    """Router discovery configuration settings.

    Controls automatic router discovery and registration behavior.

    Note: This class should not be instantiated directly. Use Settings via get_settings().
    """

    router_discovery_enabled: bool = Field(
        default=True,
        description="Enable automatic router discovery and registration",
    )

    router_exclude_modules: str = Field(
        default="",
        description="Comma-separated list of module names to exclude from discovery (e.g., 'core,utils,websocket')",
    )


# =============================================================================
# Cache Configuration
# =============================================================================


class CacheSettings(BaseSettings):
    """Cache configuration for event streaming.

    Used for persistent event storage and multi-client synchronization.
    Currently implemented using Redis.
    """

    cache_host: str = Field(
        default="localhost",
        description="Cache server hostname",
    )

    cache_port: int = Field(
        default=6379,
        description="Cache server port",
    )

    cache_db: int = Field(
        default=0,
        description="Cache database number",
    )

    cache_password: SecretStr = Field(
        default=SecretStr("cache"),
        description="Cache server password (if required)",
    )

    cache_stream_ttl_seconds: int = Field(
        default=86400,  # 24 hours
        description="Time-to-live for streaming event streams in seconds",
    )

    cache_connection_pool_size: int = Field(
        default=10,
        description="Maximum number of cache connections in pool",
    )


# =============================================================================
# Database Configuration
# =============================================================================

_VALID_SSL_MODES = frozenset({"disable", "allow", "prefer", "require", "verify-ca", "verify-full"})
_SSL_MODES_REQUIRING_CERTS = frozenset({"require", "verify-ca", "verify-full"})


def _validate_ssl_mode_value(v: str) -> str:
    lowered = v.lower()
    if lowered not in _VALID_SSL_MODES:
        msg = f"Invalid SSL mode '{v}'. Must be one of: {', '.join(sorted(_VALID_SSL_MODES))}"
        raise ValueError(msg)
    return lowered


def _validate_ssl_fields(
    ssl_mode: str,
    ssl_root_cert: str | None,
    ssl_cert: str | None,
    ssl_key: str | None,
) -> None:
    """Shared validation for SSL field combinations.

    Raises :class:`ValueError` for invalid or incomplete combinations.
    """
    if ssl_key is not None and ssl_cert is None:
        msg = "SSL client key (ssl_key) requires a client certificate (ssl_cert)"
        raise ValueError(msg)

    if (ssl_cert is not None or ssl_key is not None) and ssl_mode not in _SSL_MODES_REQUIRING_CERTS:
        msg = (
            f"Client certificates are only supported with SSL modes "
            f"{', '.join(sorted(_SSL_MODES_REQUIRING_CERTS))}; "
            f"current mode is '{ssl_mode}'"
        )
        raise ValueError(msg)

    for path, label in [(ssl_root_cert, "CA certificate"), (ssl_cert, "client certificate"), (ssl_key, "client key")]:
        if path is not None and not Path(path).is_file():
            msg = f"SSL {label} file not found: {path}"
            raise ValueError(msg)

    if ssl_mode in ("verify-ca", "verify-full") and ssl_root_cert is None:
        msg = f"SSL mode '{ssl_mode}' requires ssl_root_cert (path to CA certificate)"
        raise ValueError(msg)


class DatabaseSettings(BaseSettings):
    """Database connection configuration settings.

    Configures PostgreSQL connection parameters. You can either:
    1. Set individual APP_DB_* variables (user, password, host, port, name)
    2. Set APP_DATABASE_URL to override with a full connection string

    The full URL option supports URL-encoded passwords, alternate drivers,
    and extra query params (e.g., sslmode=require).

    Note: This class should not be instantiated directly. Use Settings via get_settings().
    """

    db_user: str = Field(
        default="admin",
        description="Database username",
    )

    db_password: SecretStr = Field(
        default=SecretStr("admin"),
        description="Database password",
    )

    db_host: str = Field(
        default="localhost",
        description="Database host",
    )

    db_port: int = Field(
        default=5432,
        description="Database port",
        ge=1,
        le=65535,
    )

    db_name: str = Field(
        default="syntara_api",
        description="Database name",
    )

    db_pool_size: int = Field(
        default=10,
        description="Maximum number of persistent database connections in SQLAlchemy pool",
        ge=1,
    )

    db_max_overflow: int = Field(
        default=20,
        description="Maximum number of overflow connections beyond db_pool_size",
        ge=0,
    )

    db_pool_timeout_seconds: float = Field(
        default=30.0,
        description="Seconds to wait for a free connection before pool checkout timeout",
        gt=0,
    )

    db_ssl_mode: str = Field(
        default="prefer",
        description="PostgreSQL SSL mode (disable, allow, prefer, require, verify-ca, verify-full)",
    )

    db_ssl_root_cert: str | None = Field(
        default=None,
        description="Path to CA certificate file for server verification",
    )

    db_ssl_cert: str | None = Field(
        default=None,
        description="Path to client certificate file (for mutual TLS)",
    )

    db_ssl_key: str | None = Field(
        default=None,
        description="Path to client private key file (for mutual TLS)",
    )

    @field_validator("db_ssl_mode")
    @classmethod
    def _validate_ssl_mode(cls, v: str) -> str:
        return _validate_ssl_mode_value(v)

    @model_validator(mode="after")
    def _validate_ssl_fields(self) -> Self:
        _validate_ssl_fields(self.db_ssl_mode, self.db_ssl_root_cert, self.db_ssl_cert, self.db_ssl_key)
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> URL:
        """Get the database URL.

        If ``APP_DATABASE_URL`` is set, it is used verbatim and all
        ``APP_DB_*`` / ``APP_DB_SSL_*`` fields are ignored — the caller
        owns all driver and connection semantics.  Otherwise the URL is
        built from the individual component fields.

        TLS is **not** configured via the URL; it is passed separately
        through ``connect_args`` (see :mod:`syntara.core.database.ssl`).
        """
        override = os.environ.get("APP_DATABASE_URL")
        if override:
            return make_url(override)
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )


# =============================================================================
# Audit Database Configuration
# =============================================================================


class AuditSettings(BaseSettings):
    """Core audit system configuration settings.

    Note: This class should not be instantiated directly. Use Settings via get_settings().
    """

    # Global Audit flag
    audit_enabled: bool = Field(
        default=True,
        description="Enable auditing",
    )

    # Audit outbox worker configuration
    audit_outbox_poll_interval_seconds: float = Field(
        default=5.0,
        description="Seconds between audit outbox worker cycles (publishes events to OTEL collector)",
        gt=0,
    )

    audit_outbox_batch_size: int = Field(
        default=100,
        description="Maximum number of audit events to process per outbox worker cycle",
        gt=0,
        le=1000,
    )

    audit_outbox_max_dispatch_attempts: int = Field(
        default=5,
        description="Maximum OTEL export attempts before an outbox record is permanently dropped",
        gt=0,
        le=10,
    )

    # Audit worker connection pool settings (separate from main pool)
    # See: backend/docs/audit-performance-optimization.md (Option 1)
    audit_worker_pool_size: int = Field(
        default=5,
        description="Connection pool size for audit worker (independent of main application pool)",
        ge=1,
    )

    audit_worker_max_overflow: int = Field(
        default=2,
        description="Max overflow connections for audit worker pool",
        ge=0,
    )


# =============================================================================
# Audit Writer Configuration
# =============================================================================


class AuditWriterSettings(BaseSettings):
    """Audit event writer configuration settings.

    Configures the fire-and-forget audit writer's concurrency limits and retry
    behavior for resilient audit event persistence.

    Note: This class should not be instantiated directly. Use Settings via get_settings().
    """

    audit_writer_max_concurrent_writes: int = Field(
        default=100,
        description="Maximum number of concurrent audit database writes",
        ge=1,
        le=1000,
    )

    audit_writer_max_retries: int = Field(
        default=3,
        description="Maximum retry attempts for transient database errors",
        ge=0,
        le=10,
    )

    audit_writer_base_delay_seconds: float = Field(
        default=0.1,
        description="Base delay in seconds for exponential backoff (e.g., 0.1s, 0.2s, 0.4s)",
        gt=0,
        le=5.0,
    )


# =============================================================================
# Server Configuration
# =============================================================================


class ServerSettings(BaseSettings):
    """Server and CORS configuration settings.

    Configures uvicorn server parameters and CORS middleware.

    Note: This class should not be instantiated directly. Use Settings via get_settings().
    """

    product_name: str = Field(
        default="Syntara",
        description="User-facing product display name (env: APP_PRODUCT_NAME)",
        max_length=64,
        pattern=r"^[a-zA-Z0-9 \-_]+$",
    )

    server_scheme: str = Field(
        default="https",
        description="Server URL scheme (https or http). Defaults to https for security. "
        "Set to http for local development without TLS.",
    )

    server_host: str = Field(
        default="0.0.0.0",  # noqa: S104
        description="Server bind host",
    )

    server_port: int = Field(
        default=8000,
        description="Server bind port",
        ge=1,
        le=65535,
    )

    server_public_url: HttpUrl | None = Field(
        default=None,
        description="Public base URL for this Nexus instance (e.g., 'https://example.com:8000'). "
        "Used as the JWT issuer, post-logout redirect, and frontend origin fallback. "
        "If not set, falls back to server_scheme://server_host:server_port. "
        "Required when server_host is a bind address like 0.0.0.0.",
    )

    @field_validator("server_public_url", mode="before")
    @classmethod
    def _empty_string_to_none(cls, v: str | None) -> str | None:
        if v is not None and v.strip() == "":
            return None
        return v

    server_reload: bool = Field(
        default=False,
        description="Enable hot reload (development only)",
    )

    workflow_base_url: str | None = Field(
        default=None,
        description=(
            "Workflow API base URL for callback URL generation (e.g., 'http://nexus:8000/api/v1'). "
            "If not set, will be constructed from server_host and server_port. "
            "Used by workflow activities to generate callback URLs for external services."
        ),
    )

    # CORS configuration
    cors_allow_origins: list[str] = Field(
        default_factory=list,
        description="Allowed origins for CORS (explicit list required when using credential cookies)",
    )

    cors_allow_credentials: bool = Field(
        default=True,
        description="Allow credentials in CORS requests",
    )

    cors_allow_methods: list[str] = Field(
        default=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        description="Allowed HTTP methods for CORS",
    )

    cors_allow_headers: list[str] = Field(
        default=["Authorization", "Content-Type", "Accept"],
        description="Allowed headers for CORS",
    )

    # OIDC security
    oidc_allow_private_networks: bool = Field(
        default=False,
        description="Allow OIDC identity providers on private/internal networks. "
        "Enable for environments with internal IdPs (e.g., corporate Keycloak on a private network). "
        "When disabled, OIDC issuer URLs that resolve to private, loopback, or link-local IPs are rejected.",
    )

    # Credential security
    credential_allow_http_host: bool = Field(
        default=False,
        description="Allow HTTP scheme for credential host URLs. "
        "Enable for development environments connecting to local services (e.g., http://localhost:44927). "
        "When disabled, credential host URLs must use HTTPS.",
    )

    # OIDC logout configuration
    oidc_post_logout_redirect_uri: str | None = Field(
        default=None,
        description="Global post-logout redirect URI for RP-initiated logout. "
        "This is the URL where users are redirected after logging out from their IdP. "
        "If not set, will be constructed from server_scheme://server_host:server_port. "
        "Must be an allowed CORS origin for security.",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def post_logout_redirect_uri(self) -> str:
        """Get the post-logout redirect URI.

        Priority: oidc_post_logout_redirect_uri > server_public_url > constructed URL.
        """
        if self.oidc_post_logout_redirect_uri:
            return self.oidc_post_logout_redirect_uri
        if self.server_public_url:
            return str(self.server_public_url).rstrip("/")
        return f"{self.server_scheme}://{self.server_host}:{self.server_port}"

    @model_validator(mode="after")
    def _validate_cors(self) -> "ServerSettings":
        """Reject wildcard origins when credentials are enabled.

        Per the CORS specification, ``Access-Control-Allow-Origin: *`` is
        incompatible with ``Access-Control-Allow-Credentials: true``.
        """
        if self.cors_allow_credentials and "*" in self.cors_allow_origins:
            msg = "CORS: cors_allow_origins cannot contain '*' when cors_allow_credentials is True"
            raise ValueError(msg)
        return self

    workflow_http_request_allowed_hosts: list[str] = Field(
        default_factory=list,
        description="Hostnames that workflow HTTP request nodes are permitted to target "
        "despite resolving to private IPs. Set via APP_WORKFLOW_HTTP_REQUEST_ALLOWED_HOSTS "
        "as a JSON array.",
    )

    integration_url_allowed_hosts: list[str] = Field(
        default_factory=list,
        description="Hostnames that integration base_url fields are permitted to use "
        "despite resolving to private or loopback IPs (e.g. add 'localhost' to allow a "
        "local MCP server). Cloud metadata endpoints are always blocked regardless of "
        "this allowlist. Set via APP_INTEGRATION_URL_ALLOWED_HOSTS as a JSON array.",
    )


# =============================================================================
# Retriever Service Configuration
# =============================================================================


class RetrieverServiceSettings(BaseSettings):
    """RetrieverService configuration settings.

    Configuration settings for the RetrieverService framework for document
    retrieval and relevancy checking.
    """

    # LLM Relevancy Checker Configuration
    retriever_llm_temperature: float = Field(
        default=RetrieverServiceDefaults.LLM_TEMPERATURE,
        description="Temperature for LLM relevancy checking",
        ge=0.0,
        le=2.0,
    )

    retriever_llm_max_tokens: int = Field(
        default=RetrieverServiceDefaults.LLM_MAX_TOKENS,
        description="Maximum tokens for LLM relevancy responses",
        ge=1,
        le=4000,
    )

    retriever_llm_similarity_threshold: float = Field(
        default=RetrieverServiceDefaults.LLM_SIMILARITY_THRESHOLD,
        description="Similarity threshold for LLM relevancy filtering",
        ge=0.0,
        le=1.0,
    )

    retriever_llm_max_results: int = Field(
        default=RetrieverServiceDefaults.LLM_MAX_RESULTS,
        description="Maximum results returned by LLM relevancy checking",
        ge=1,
        le=1000,
    )

    # Keyword Relevancy Checker Configuration
    retriever_keyword_similarity_threshold: float = Field(
        default=RetrieverServiceDefaults.KEYWORD_SIMILARITY_THRESHOLD,
        description="Similarity threshold for keyword relevancy filtering",
        ge=0.0,
        le=1.0,
    )

    retriever_keyword_max_results: int = Field(
        default=RetrieverServiceDefaults.KEYWORD_MAX_RESULTS,
        description="Maximum results returned by keyword relevancy checking",
        ge=1,
        le=1000,
    )

    retriever_keyword_case_sensitive: bool = Field(
        default=RetrieverServiceDefaults.KEYWORD_CASE_SENSITIVE,
        description="Whether keyword matching is case sensitive",
    )

    retriever_keyword_stem_words: bool = Field(
        default=RetrieverServiceDefaults.KEYWORD_STEM_WORDS,
        description="Whether to apply word stemming in keyword matching",
    )

    retriever_keyword_remove_stopwords: bool = Field(
        default=RetrieverServiceDefaults.KEYWORD_REMOVE_STOPWORDS,
        description="Whether to remove stopwords in keyword processing",
    )

    retriever_keyword_phrase_bonus_multiplier: float = Field(
        default=RetrieverServiceDefaults.KEYWORD_PHRASE_BONUS_MULTIPLIER,
        description="Multiplier bonus for exact phrase matches",
        ge=0.1,
        le=10.0,
    )

    # General Retriever Configuration
    retriever_context_window_size: int = Field(
        default=RetrieverServiceDefaults.CONTEXT_WINDOW_SIZE,
        description="Maximum characters for document content excerpt",
        ge=100,
        le=10000,
    )

    # LLM Relevancy Configuration Defaults
    retriever_llm_ranking_content_similarity: float = Field(
        default=RetrieverServiceDefaults.LLM_RANKING_CONTENT_SIMILARITY,
        description="Weight for content similarity in LLM relevancy ranking",
        ge=0.0,
        le=1.0,
    )

    retriever_llm_ranking_file_metadata_relevance: float = Field(
        default=RetrieverServiceDefaults.LLM_RANKING_FILE_METADATA_RELEVANCE,
        description="Weight for file metadata relevance in LLM relevancy ranking",
        ge=0.0,
        le=1.0,
    )

    retriever_llm_ranking_recency: float = Field(
        default=RetrieverServiceDefaults.LLM_RANKING_RECENCY,
        description="Weight for recency in LLM relevancy ranking",
        ge=0.0,
        le=1.0,
    )

    retriever_llm_system_prompt: str = Field(
        default=RetrieverServiceDefaults.LLM_SYSTEM_PROMPT,
        description="System prompt for LLM relevancy checking",
    )

    retriever_llm_include_file_metadata: bool = Field(
        default=RetrieverServiceDefaults.LLM_INCLUDE_FILE_METADATA,
        description="Whether to include file metadata in LLM grounding",
    )

    retriever_llm_use_title_weighting: bool = Field(
        default=RetrieverServiceDefaults.LLM_USE_TITLE_WEIGHTING,
        description="Whether to use title weighting in LLM grounding",
    )

    retriever_llm_recency_weight: float = Field(
        default=RetrieverServiceDefaults.LLM_RECENCY_WEIGHT,
        description="Recency weight for LLM relevancy configuration",
        ge=0.0,
        le=1.0,
    )

    retriever_llm_mmr_lambda_param: float = Field(
        default=RetrieverServiceDefaults.LLM_MMR_LAMBDA_PARAM,
        description="Lambda parameter for LLM MMR (Maximal Marginal Relevance)",
        ge=0.0,
        le=1.0,
    )

    retriever_llm_mmr_enabled: bool = Field(
        default=RetrieverServiceDefaults.LLM_MMR_ENABLED,
        description="Whether to enable MMR for LLM relevancy",
    )

    # Keyword Relevancy Configuration Defaults
    retriever_keyword_ranking_term_frequency: float = Field(
        default=RetrieverServiceDefaults.KEYWORD_RANKING_TERM_FREQUENCY,
        description="Weight for term frequency in keyword relevancy ranking",
        ge=0.0,
        le=1.0,
    )

    retriever_keyword_ranking_filename_match: float = Field(
        default=RetrieverServiceDefaults.KEYWORD_RANKING_FILENAME_MATCH,
        description="Weight for filename match in keyword relevancy ranking",
        ge=0.0,
        le=1.0,
    )

    retriever_keyword_ranking_content_density: float = Field(
        default=RetrieverServiceDefaults.KEYWORD_RANKING_CONTENT_DENSITY,
        description="Weight for content density in keyword relevancy ranking",
        ge=0.0,
        le=1.0,
    )

    retriever_keyword_ranking_proximity_bonus: float = Field(
        default=RetrieverServiceDefaults.KEYWORD_RANKING_PROXIMITY_BONUS,
        description="Weight for proximity bonus in keyword relevancy ranking",
        ge=0.0,
        le=1.0,
    )

    retriever_keyword_ranking_exact_match_bonus: float = Field(
        default=RetrieverServiceDefaults.KEYWORD_RANKING_EXACT_MATCH_BONUS,
        description="Weight for exact match bonus in keyword relevancy ranking",
        ge=0.0,
        le=1.0,
    )

    retriever_keyword_ranking_fuzzy_match_bonus: float = Field(
        default=RetrieverServiceDefaults.KEYWORD_RANKING_FUZZY_MATCH_BONUS,
        description="Weight for fuzzy match bonus in keyword relevancy ranking",
        ge=0.0,
        le=1.0,
    )

    retriever_keyword_proximity_scoring: bool = Field(
        default=RetrieverServiceDefaults.KEYWORD_PROXIMITY_SCORING,
        description="Whether to enable proximity scoring in keyword matching",
    )

    retriever_keyword_fuzzy_matching: bool = Field(
        default=RetrieverServiceDefaults.KEYWORD_FUZZY_MATCHING,
        description="Whether to enable fuzzy matching in keyword relevancy",
    )

    retriever_keyword_boost_title_matches: bool = Field(
        default=RetrieverServiceDefaults.KEYWORD_BOOST_TITLE_MATCHES,
        description="Whether to boost title matches in keyword grounding",
    )

    retriever_keyword_boost_filename_matches: bool = Field(
        default=RetrieverServiceDefaults.KEYWORD_BOOST_FILENAME_MATCHES,
        description="Whether to boost filename matches in keyword grounding",
    )

    retriever_keyword_penalty_for_short_documents: bool = Field(
        default=RetrieverServiceDefaults.KEYWORD_PENALTY_FOR_SHORT_DOCUMENTS,
        description="Whether to apply penalty for short documents in keyword grounding",
    )

    retriever_keyword_recency_weight: float = Field(
        default=RetrieverServiceDefaults.KEYWORD_RECENCY_WEIGHT,
        description="Recency weight for keyword relevancy configuration",
        ge=0.0,
        le=1.0,
    )

    retriever_keyword_mmr_lambda_param: float = Field(
        default=RetrieverServiceDefaults.KEYWORD_MMR_LAMBDA_PARAM,
        description="Lambda parameter for keyword MMR (Maximal Marginal Relevance)",
        ge=0.0,
        le=1.0,
    )

    retriever_keyword_mmr_enabled: bool = Field(
        default=RetrieverServiceDefaults.KEYWORD_MMR_ENABLED,
        description="Whether to enable MMR for keyword relevancy",
    )

    @model_validator(mode="after")
    def validate_keyword_ranking_weights_sum(self) -> Self:
        """Validate that all keyword ranking weights sum to between 0.0 and 1.0.

        This validator runs after all fields are processed and checks that the
        sum of all keyword ranking weights is within the valid range.
        """
        # Get all keyword ranking weight values from the model instance
        weights = [
            self.retriever_keyword_ranking_term_frequency,
            self.retriever_keyword_ranking_filename_match,
            self.retriever_keyword_ranking_content_density,
            self.retriever_keyword_ranking_proximity_bonus,
            self.retriever_keyword_ranking_exact_match_bonus,
            self.retriever_keyword_ranking_fuzzy_match_bonus,
        ]

        total = sum(weights)
        if not (0.0 <= total <= 1.0):
            field_names = [
                "retriever_keyword_ranking_term_frequency",
                "retriever_keyword_ranking_filename_match",
                "retriever_keyword_ranking_content_density",
                "retriever_keyword_ranking_proximity_bonus",
                "retriever_keyword_ranking_exact_match_bonus",
                "retriever_keyword_ranking_fuzzy_match_bonus",
            ]
            msg = (
                f"Keyword ranking weights must sum to between 0.0 and 1.0, "
                f"but sum to {total:.3f}. Affected fields: {', '.join(field_names)}"
            )
            raise SafeValueError(msg)

        return self


# =============================================================================
# LLM Adapter Retry Configuration
# =============================================================================


class AdapterRetrySettings(BaseSettings):
    """LLM adapter retry and recovery configuration settings.

    Configures retry behavior for LLM adapter operations to handle transient
    failures (network issues, rate limiting, temporary service outages).

    Note: This class should not be instantiated directly. Use Settings via get_settings().
    """

    adapter_max_retries: int = Field(
        default=3,
        description="Maximum number of retry attempts (0 disables retries)",
        ge=0,
    )

    adapter_initial_backoff_seconds: float = Field(
        default=1.0,
        description="Initial delay before first retry in seconds",
        gt=0,
    )

    adapter_backoff_growth_factor: float = Field(
        default=2.0,
        description="Exponential growth factor for backoff delays (1.0 = fixed, >1.0 = exponential)",
        ge=1.0,
    )

    adapter_max_backoff_seconds: float = Field(
        default=10.0,
        description="Maximum cap for backoff delay in seconds",
        gt=0,
    )

    adapter_request_timeout_seconds: float = Field(
        default=30.0,
        description="Per-attempt timeout to prevent unbounded wait times (applies to initial + all retries)",
        gt=0,
    )

    @model_validator(mode="after")
    def validate_backoff_relationship(self) -> "AdapterRetrySettings":
        """Validate that max_backoff >= initial_backoff.

        This ensures exponential backoff works as intended. If max < initial,
        all retry attempts would be immediately capped to max, defeating the
        purpose of exponential growth.
        """
        if self.adapter_max_backoff_seconds < self.adapter_initial_backoff_seconds:
            msg = (
                f"adapter_max_backoff_seconds ({self.adapter_max_backoff_seconds}) "
                f"must be >= adapter_initial_backoff_seconds ({self.adapter_initial_backoff_seconds})"
            )
            raise SafeValueError(msg)
        return self


# =============================================================================
# Logging Configuration
# =============================================================================


class LogLevel(StrEnum):
    """Standard Python logging levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LoggingSettings(BaseSettings):
    """Logging configuration settings.

    Note: This class should not be instantiated directly. Use Settings via get_settings().
    """

    fallback_log_level: LogLevel = Field(
        default=LogLevel.INFO,
        description="Fallback logging level used before runtime settings are available. "
        "Once the database is ready, the runtime setting logging.log_level takes precedence.",
    )

    log_output_format: str = Field(
        default="json",
        description="Log output format (json, text)",
    )


# Matches Kubernetes cluster-internal service DNS: <service>.<namespace>.svc[.cluster.local]
# Requires exactly two DNS labels before the .svc suffix to prevent single-label matches.
# Labels must start and end with alphanumeric characters (RFC 1123 — no trailing hyphens).
_SVC_DNS_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?[.][a-z0-9]([a-z0-9-]*[a-z0-9])?\.svc(\.cluster\.local)?$")


class OpenTelemetrySettings(BaseSettings):
    """OpenTelemetry configuration settings.

    Configures OpenTelemetry exporters for logs, traces, and metrics.

    Note: This class should not be instantiated directly. Use Settings via get_settings().
    """

    otel_enabled: bool = Field(
        default=False,
        description="Enable OpenTelemetry exporters",
    )

    otel_service_name: str = Field(
        default="syntara",
        description="Service name for OpenTelemetry resource attributes",
    )

    otel_endpoint: str = Field(
        default="http://localhost:4318/v1/logs",
        description=(
            "OTLP HTTP endpoint for logs. Use http://<service>.<namespace>.svc.cluster.local:4318/v1/logs "
            "for cluster-internal collectors, or https://collector.example.com:4318/v1/logs for TLS."
        ),
    )

    otel_api_key: SecretStr | None = Field(
        default=None,
        description="API key for OTLP endpoint authentication (sent as Bearer token)",
    )

    otel_auth_header_name: str = Field(
        default="Authorization",
        description="HTTP header name for API key authentication",
    )

    otel_client_cert_file: str | None = Field(
        default=None,
        description="Path to client certificate file for mTLS authentication",
    )

    otel_client_key_file: str | None = Field(
        default=None,
        description="Path to client private key file for mTLS authentication",
    )

    otel_ca_cert_file: str | None = Field(
        default=None,
        description="Path to CA certificate file for server verification",
    )

    @field_validator("otel_endpoint")
    @classmethod
    def validate_otel_endpoint_security(cls, v: str) -> str:
        """Validate that remote OTLP endpoints use HTTPS to prevent plaintext transmission of audit logs.

        HTTP is allowed for:
        - Loopback addresses (localhost, 127.0.0.1, ::1) — local development
        - Kubernetes cluster-internal service DNS (<service>.<namespace>.svc[.cluster.local]) — in-cluster collectors

        All other HTTP endpoints are rejected. Remote endpoints must use HTTPS.

        Security: Uses URL parsing to prevent bypass attacks. The K8s service DNS check requires
        exactly two labels before .svc (e.g. service.namespace.svc) to prevent single-label
        matches or loopback-lookalike patterns like "127.0.0.1.ns.svc".
        """
        parsed = urlparse(v)

        # HTTPS is always allowed
        if parsed.scheme == "https":
            return v

        # HTTP is allowed for loopback and cluster-internal addresses
        if parsed.scheme == "http":
            hostname = parsed.hostname or ""

            # Loopback addresses (local development)
            # Note: parsed.hostname strips brackets from IPv6 literals; "::1" is the actual returned form
            if hostname in ("localhost", "127.0.0.1", "::1"):
                return v

            # cluster-internal service DNS names (<service>.<namespace>.svc[.cluster.local])
            if _SVC_DNS_RE.match(hostname):
                return v

            # Reject all other HTTP endpoints
            msg = (
                "Remote OTLP endpoints must use HTTPS to prevent plaintext transmission of audit logs. "
                f"Invalid endpoint: {v}. Use https:// for remote endpoints, "
                "http://localhost / http://127.0.0.1 / http://[::1] for local development, or "
                "http://<service>.<namespace>.svc.cluster.local for cluster-internal collectors."
            )
            raise ValueError(msg)

        # Reject unsupported schemes
        msg = (
            f"Unsupported URL scheme '{parsed.scheme}' in OTLP endpoint: {v}. "
            "Use https:// for remote endpoints or http:// for local/cluster-internal endpoints."
        )
        raise ValueError(msg)


# =============================================================================
# Temporal Configuration
# =============================================================================

TEMPORAL_DEFAULT_TASK_QUEUE = "orchestrator-workflow-queue"
TEMPORAL_DEFAULT_BACKGROUND_TASK_QUEUE = "orchestrator-background-queue"


class TemporalSettings(BaseSettings):
    """Temporal workflow engine configuration settings.

    Configures connection to Temporal server for workflow orchestration.

    Note: This class should not be instantiated directly. Use Settings via get_settings().
    """

    temporal_address: str = Field(
        default="localhost:7233",
        description="Temporal server address (host:port)",
    )

    temporal_namespace: str = Field(
        default="default",
        description="Temporal namespace for workflow isolation",
    )

    task_queue: str = Field(
        default=TEMPORAL_DEFAULT_TASK_QUEUE,
        description="Temporal task queue name for workflow routing",
    )

    background_task_queue: str = Field(
        default=TEMPORAL_DEFAULT_BACKGROUND_TASK_QUEUE,
        description=(
            "Temporal task queue name for builtin/background workflow executions. "
            "Built-in workflows (Document Conversion, Agent Execution) are always "
            "routed to this queue. Override APP_BACKGROUND_TASK_QUEUE to change the name."
        ),
    )

    max_cached_workflows: int = Field(
        default=20,
        ge=1,
        description=(
            "Maximum number of workflow states cached in memory per worker for replay efficiency. "
            "Each worker pod caches up to this many workflow states; multiply by pod count for the "
            "aggregate ceiling. Lower values reduce Temporal server GetHistory memory pressure under "
            "concurrent load. Set via APP_MAX_CACHED_WORKFLOWS."
        ),
    )

    max_concurrent_workflow_tasks: int = Field(
        default=50,
        ge=1,
        description="Maximum concurrent workflow task executions (also caps thread pool size)",
    )

    max_concurrent_activities: int = Field(
        default=50,
        ge=1,
        description="Maximum concurrent activity executions",
    )

    max_concurrent_workflows: int = Field(
        default=0,
        ge=0,
        description=(
            "Application-level cap on the number of non-terminal workflow executions allowed "
            "simultaneously. New workflow starts are rejected with HTTP 429 when this limit is "
            "reached, preventing unbounded Temporal server memory growth. "
            "Set to 0 (default) to disable the limit. "
            "Set via APP_MAX_CONCURRENT_WORKFLOWS. "
            "Tune this value based on benchmarking against the Temporal server memory budget."
        ),
    )

    schedule_reconciliation_interval_seconds: float = Field(
        default=60.0,
        description="Seconds between schedule reconciliation cycles",
        gt=0,
    )


@lru_cache(maxsize=4)
def _read_cert_cn(cert_path: str) -> str:
    """Read the Common Name from a PEM certificate file (cached)."""
    from cryptography import x509  # noqa: PLC0415

    cert_pem = Path(cert_path).read_bytes()
    cert = x509.load_pem_x509_certificate(cert_pem)
    cn = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
    if not cn:
        msg = f"S2S TLS certificate at {cert_path} has no Common Name"
        raise RuntimeError(msg)
    return str(cn[0].value)


def _validate_tls_cert_paths(
    paths: list[tuple[str | None, str]],
    context: str,
) -> None:
    """Shared validation for TLS certificate path fields.

    Raises :class:`ValueError` when required paths are missing or files do not exist.
    """
    missing = [name for value, name in paths if value is None]
    if missing:
        msg = f"{context} is enabled but required paths are not set: {', '.join(missing)}"
        raise ValueError(msg)

    for path, name in paths:
        if path is not None and not Path(path).is_file():
            msg = f"{context} file not found for {name}: {path}"
            raise ValueError(msg)


class S2STLSSettings(BaseSettings):
    """TLS configuration for internal service-to-service communication.

    When enabled, mTLS is active for all internal communication: the backend
    serves HTTPS, internal HTTP clients present client certificates, and
    Temporal gRPC connections use TLS. The same certificate is used for
    serving, client auth, and Temporal — each service certificate includes
    both serverAuth and clientAuth EKUs.

    Disabled by default for local development.

    Note: This class should not be instantiated directly. Use Settings via get_settings().
    """

    s2s_tls_enabled: bool = Field(
        default=False,
        description="Enable mTLS for all internal service-to-service communication",
    )

    s2s_tls_ca_cert_path: str | None = Field(
        default=None,
        description="Path to CA certificate for verifying peer certificates",
    )

    s2s_tls_cert_path: str | None = Field(
        default=None,
        description="Path to this service's certificate (serving HTTPS, client auth, and Temporal)",
    )

    s2s_tls_key_path: str | None = Field(
        default=None,
        description="Path to this service's private key",
    )

    s2s_tls_cn_allowlist: list[str] | None = Field(
        default=None,
        description="Allowed client certificate Common Names. "
        "When set, only certificates with a CN in this list are accepted. "
        "When None, any CA-signed certificate is accepted.",
    )

    s2s_tls_crl_path: str | None = Field(
        default=None,
        description="Path to a PEM-encoded Certificate Revocation List (CRL). "
        "When set, certificates whose serial number appears in the CRL are rejected.",
    )

    @model_validator(mode="after")
    def _validate_s2s_tls_fields(self) -> Self:
        if not self.s2s_tls_enabled:
            return self
        _validate_tls_cert_paths(
            [
                (self.s2s_tls_ca_cert_path, "s2s_tls_ca_cert_path"),
                (self.s2s_tls_cert_path, "s2s_tls_cert_path"),
                (self.s2s_tls_key_path, "s2s_tls_key_path"),
            ],
            context="S2S TLS",
        )
        if self.s2s_tls_crl_path is not None and not Path(self.s2s_tls_crl_path).is_file():
            msg = f"S2S TLS CRL file not found: {self.s2s_tls_crl_path}"
            raise ValueError(msg)
        return self


# =============================================================================
# Telemetry Configuration
# =============================================================================


class TelemetrySettings(BaseSettings):
    """Telemetry configuration settings for Segment.com integration.

    Configures the Segment Analytics SDK for workflow runtime telemetry.
    Telemetry is always enabled per specification (FR-014).

    Note: This class should not be instantiated directly. Use Settings via get_settings().
    """

    segment_write_key: SecretStr = Field(
        default=SecretStr(""),
        description="Segment write API key for telemetry transmission",
        exclude=True,
    )

    segment_endpoint: HttpUrl = Field(  # type: ignore[assignment]
        default="https://api.segment.io",
        description="Segment API endpoint URL",
        exclude=True,
    )

    segment_max_retries: int = Field(
        default=10,
        description="Maximum number of retries for Segment batch uploads",
        exclude=True,
    )

    segment_timeout: int = Field(
        default=30,
        description="HTTP timeout in seconds for Segment batch uploads",
        exclude=True,
    )

    entitlement_id: str = Field(
        default="",
        description="Unique Nexus installation identifier for anonymized telemetry tracking",
        exclude=True,
    )

    collection_interval_seconds: int = Field(
        default=3600,
        description="Interval in seconds between periodic analytics collection cycles",
        exclude=True,
    )

    container_image_version: str = Field(
        default="",
        description="Container image version/tag, injected at build time via APP_CONTAINER_IMAGE_VERSION",
        exclude=True,
    )

    segment_high_volume_events_enabled: bool = Field(
        default=False,
        description=(
            "Enable high-volume Segment events (api_call, user_login)."
            " Disabled by default to reduce event volume at scale."
        ),
        exclude=True,
    )


# =============================================================================
# Workflow Engine Configuration
# =============================================================================


class WorkflowEngineSettings(BaseSettings):
    """Workflow execution settings and configuration.

    Provides configuration for workflow execution timeouts, limits, and validation.

    Note: This class should not be instantiated directly. Use Settings via get_settings().
    """

    # Script execution settings
    script_cleanup_terminate_timeout: float = Field(
        default=1.0,
        description="Timeout in seconds for graceful process termination",
        ge=0.1,
    )

    script_cleanup_kill_timeout: float = Field(
        default=0.5,
        description="Timeout in seconds for forceful process kill",
        ge=0.1,
    )

    max_env_var_length: int = Field(
        default=32768,
        description="Maximum length per environment variable in bytes (32KB)",
        ge=1024,
    )

    agent_orchestrator_base_url: HttpUrl = Field(  # type: ignore[assignment]
        default="http://localhost:8000/api/v1",
        description="Base URL for Agent Orchestrator API",
    )

    approvals_api_base_url: HttpUrl = Field(  # type: ignore[assignment]
        default="http://localhost:8000/api/v1",
        description="Base URL for Approvals API",
    )

    # AAP (Ansible Automation Platform) settings
    # NOTE: These settings may be deprecated when AAP Tool integration is added.
    aap_base_url: str | None = Field(
        default=None,
        description="AAP Controller base URL (e.g., https://aap.example.com)",
    )

    aap_public_url: str | None = Field(
        default=None,
        description=(
            "Public-facing AAP Controller URL for browser links (e.g., https://aap.example.com). "
            "Defaults to aap_base_url. Set this when aap_base_url is an internal/cluster URL "
            "that should not be exposed to end users."
        ),
    )

    aap_username: str | None = Field(
        default=None,
        description="AAP username for basic authentication (optional if using token)",
    )

    aap_password: SecretStr | None = Field(
        default=None,
        description="AAP password for basic authentication (optional if using token)",
    )

    aap_token: SecretStr | None = Field(
        default=None,
        description="AAP API token for token authentication (preferred over username/password)",
    )

    aap_timeout_seconds: int = Field(
        default=3600,
        description="Default timeout for AAP job template activities in seconds (1 hour)",
        ge=1,
    )

    aap_proxy_timeout_seconds: int = Field(
        default=30,
        description="Timeout for AAP proxy (BFF) requests in seconds — list/detail API calls, not job execution",
        ge=1,
    )

    aap_poll_interval_seconds: float = Field(
        default=5.0,
        description="AAP job status polling interval in seconds (AAP recommendation: 5 seconds)",
        ge=1.0,
    )

    aap_verify_ssl: bool = Field(
        default=True,
        description="Verify SSL certificates for AAP connections (set to False for self-signed certs in dev/test)",
    )


# =============================================================================
# Tool Manager Configuration
# =============================================================================


# =============================================================================
# JWT Authentication Configuration
# =============================================================================


class JWTSettings(BaseSettings):
    """JWT authentication configuration settings.

    Configures JWT token creation, validation, and key management for
    authentication. Uses ES256 (ECDSA P-256) algorithm for signing.

    Note: This class should not be instantiated directly. Use Settings via get_settings().
    """

    # JWT Token Configuration
    jwt_access_token_lifetime_minutes: int = Field(
        default=15,
        description="Access token lifetime in minutes",
        ge=1,
        le=60,
    )

    jwt_sa_access_token_lifetime_minutes: int = Field(
        default=15,
        description="Service account access token lifetime in minutes",
        ge=1,
        le=60,
    )

    jwt_refresh_token_lifetime_hours: int = Field(
        default=8,
        description="Refresh token lifetime in hours",
        ge=1,
        le=720,  # 30 days max
    )

    # Key Management
    jwt_private_key_path: str | None = Field(
        default=None,
        description="Path to ES256 private key PEM file (if not set, generates ephemeral key)",
    )

    jwt_private_key_base64: SecretStr | None = Field(
        default=None,
        description="Base64-encoded ES256 private key PEM (alternative to file path)",
    )

    jwt_key_id: str = Field(
        default="orchestrator-primary",
        description="Key ID (kid) for JWT header",
    )

    # Backup Keys for Key Rotation (verification only)
    jwt_backup_keys: list[dict[str, str]] | None = Field(
        default=None,
        description=(
            "List of backup keys for verification during key rotation. "
            "Each entry must have 'key_id' and either 'key_path' or 'key_base64'. "
            "Example: [{'key_id': 'orchestrator-2024-01', 'key_base64': '...'}]"
        ),
    )

    # Refresh-token cookie settings
    cookie_domain: str | None = Field(
        default=None,
        description="Domain attribute for the refresh-token cookie (None = host-only)",
    )

    # Bootstrap Admin
    admin_password_path: str | None = Field(
        default=None,
        description="Path to file containing the bootstrap admin password (e.g., /run/secrets/admin-password)",
    )


class ToolManagerSettings(BaseSettings):
    """Tool Manager client configuration settings.

    Configures the HTTP client for Tool Manager REST API integration.

    Note: This class should not be instantiated directly. Use Settings via get_settings().
    """

    tool_manager_base_url: HttpUrl = Field(  # type: ignore[assignment]
        default="http://localhost:8000/api/v1",
        description="Tool Manager API base URL",
    )

    tool_manager_timeout_seconds: float = Field(
        default=30.0,
        description="Request timeout in seconds",
        gt=0,
    )

    tool_manager_max_connections: int = Field(
        default=10,
        description="Maximum number of connections to maintain",
        ge=1,
    )

    tool_manager_max_keepalive_connections: int = Field(
        default=5,
        description="Maximum number of keepalive connections",
        ge=0,
    )

    @model_validator(mode="after")
    def validate_keepalive_connections(self) -> Self:
        """Validate that keepalive connections don't exceed max connections."""
        if self.tool_manager_max_keepalive_connections > self.tool_manager_max_connections:
            msg = (
                f"tool_manager_max_keepalive_connections ({self.tool_manager_max_keepalive_connections}) "
                f"cannot exceed tool_manager_max_connections ({self.tool_manager_max_connections})"
            )
            raise SafeValueError(msg)
        return self


# =============================================================================
# Metrics Configuration
# =============================================================================


class MetricsSettings(BaseSettings):
    """Performance metrics subsystem configuration.

    Controls recording and retention of raw performance metrics exposed via
    REST API and Prometheus endpoints.

    Note: This class should not be instantiated directly. Use Settings via get_settings().
    """

    metrics_retention_seconds: int = Field(
        default=3600,
        description="How long to retain raw metrics in memory (NFR-003)",
        ge=0,
    )

    metrics_max_records: int = Field(
        default=100_000,
        description="Maximum number of raw metrics to store in memory",
        ge=1,
    )

    metrics_enabled: bool = Field(
        default=True,
        description="Enable/disable metrics collection globally",
    )

    metrics_openmetrics_enabled: bool = Field(
        default=True,
        description="Enable OpenMetrics scrape endpoint (GET /metrics)",
    )

    metrics_poller_interval_seconds: float = Field(
        default=15.0,
        description="Seconds between completion-poller cycles",
        gt=0,
    )

    metrics_poller_lookback_seconds: float = Field(
        default=120.0,
        description="How far back the completion poller queries for finished executions",
        gt=0,
    )

    metrics_poller_max_dedup_size: int = Field(
        default=50_000,
        description="Maximum size of the in-memory dedup set for emitted executions",
        ge=1,
    )

    metrics_cleanup_interval_seconds: float = Field(
        default=30.0,
        description="Seconds between periodic in-memory metrics store cleanup and malloc_trim cycles",
        gt=0,
    )

    metrics_worker_port: int = Field(
        default=9090,
        description=(
            "TCP port on which Temporal workers expose a Prometheus metrics HTTP endpoint. "
            "Set via APP_METRICS_WORKER_PORT. Used by both orchestrator-workflow-worker and "
            "orchestrator-background-worker so Prometheus can scrape worker-side metrics."
        ),
        ge=1,
        le=65535,
    )


# =============================================================================
# Workflow Client Configuration
# =============================================================================


class WorkflowClientSettings(BaseSettings):
    """Workflow API client configuration settings.

    Configures the HTTP client for sending approval signals to workflow engine.

    Note: This class should not be instantiated directly. Use Settings via get_settings().
    """

    workflow_client_max_retries: int = Field(
        default=5,
        description="Maximum number of retry attempts (0 disables retries)",
        ge=0,
    )

    workflow_client_initial_backoff_seconds: float = Field(
        default=1.0,
        description="Initial delay before first retry in seconds",
        gt=0,
    )

    workflow_client_backoff_growth_factor: float = Field(
        default=2.0,
        description="Exponential growth factor for backoff delays (1.0 = fixed, >1.0 = exponential)",
        ge=1.0,
    )

    workflow_client_max_backoff_seconds: float = Field(
        default=10.0,
        description="Maximum cap for backoff delay in seconds",
        gt=0,
    )

    workflow_client_request_timeout_seconds: float = Field(
        default=30.0,
        description="Per-attempt timeout to prevent unbounded wait times (applies to initial + all retries)",
        gt=0,
    )

    @model_validator(mode="after")
    def validate_backoff_relationship(self) -> "WorkflowClientSettings":
        """Validate that max_backoff >= initial_backoff.

        This ensures exponential backoff works as intended. If max < initial,
        all retry attempts would be immediately capped to max, defeating the
        purpose of exponential growth.
        """
        if self.workflow_client_max_backoff_seconds < self.workflow_client_initial_backoff_seconds:
            msg = (
                f"workflow_client_max_backoff_seconds ({self.workflow_client_max_backoff_seconds}) "
                f"must be >= workflow_client_initial_backoff_seconds ({self.workflow_client_initial_backoff_seconds})"
            )
            raise SafeValueError(msg)
        return self


# =============================================================================
# Credential Encryption Settings
# =============================================================================


class CredentialEncryptionSettings(BaseSettings):
    """Credential encryption configuration.

    Controls encryption of credential field values at rest using AES-256-GCM.

    Provide the key via one of:
      - APP_SECRET_ENCRYPTION_KEY: 64-character hex string (32 bytes) directly
      - APP_SECRET_ENCRYPTION_KEY_PATH: path to a file containing the hex key

    When both are set, the file path takes precedence.

    Note: This class should not be instantiated directly. Use Settings via get_settings().
    """

    secret_encryption_key: SecretStr | None = Field(
        default=None,
        description="64-character hex string (32 bytes) for AES-256-GCM secret encryption.",
    )

    secret_encryption_key_path: str | None = Field(
        default=None,
        description="Path to a file containing the 64-character hex encryption key. "
        "Takes precedence over secret_encryption_key when both are set.",
    )

    @model_validator(mode="before")
    @classmethod
    def resolve_encryption_key(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Resolve the encryption key from path or direct value; reject if neither is set."""
        path = data.get("secret_encryption_key_path")
        if path is not None:
            key_file = Path(path)
            if not key_file.is_file():
                msg = f"secret_encryption_key_path points to a file that does not exist: {path}"
                raise SafeValueError(msg)
            try:
                data["secret_encryption_key"] = key_file.read_text().strip()
            except OSError as e:
                msg = f"Failed to read secret_encryption_key_path {path}: {e}"
                raise SafeValueError(msg) from e
        return data

    @field_validator("secret_encryption_key")
    @classmethod
    def validate_encryption_key(cls, v: SecretStr | None) -> SecretStr | None:
        """Validate the encryption key format when provided."""
        if v is None:
            return None
        key_value = v.get_secret_value()
        expected_hex_length = 64  # 32 bytes = 64 hex chars
        if len(key_value) != expected_hex_length:
            msg = f"secret_encryption_key must be exactly 64 hex characters (32 bytes), got {len(key_value)}"
            raise SafeValueError(msg)
        try:
            bytes.fromhex(key_value)
        except ValueError as e:
            msg = "secret_encryption_key must be a valid hex string"
            raise SafeValueError(msg) from e
        if key_value == "0" * expected_hex_length:
            msg = (
                "secret_encryption_key cannot be the all-zeros default. "
                "Generate a secure key with:\n"
                "  openssl rand -hex 32\n"
                '  python -c "import secrets; print(secrets.token_hex(32))"'
            )
            raise SafeValueError(msg)
        return v


# =============================================================================
# Authorization Configuration
# =============================================================================


class AuthzSettings(BaseSettings):
    """Authorization configuration settings."""

    authz_default_project: str = Field(
        default="default",
        description="Default project name for resources without a project",
    )

    authz_cache_enabled: bool = Field(
        default=True,
        description="Enable in-process TTL cache for authorization evaluation results",
    )

    authz_cache_ttl_seconds: int = Field(
        default=300,
        ge=1,
        description="TTL in seconds for the authorization result cache",
    )

    authz_cache_maxsize: int = Field(
        default=2048,
        ge=1,
        description="Maximum number of entries in the authorization result cache (LRU eviction)",
    )


_SA_CREDENTIAL_MAX_LIFETIME_UPPER = 730


class ServiceAccountSettings(BaseSettings):
    """Service account credential configuration."""

    sa_credential_max_lifetime_days: int = Field(
        default=180,
        description=(
            "Maximum lifetime for service account credentials in days. "
            f"-1 = unlimited (no automatic expiry), 1-{_SA_CREDENTIAL_MAX_LIFETIME_UPPER} = enforced limit."
        ),
    )

    @field_validator("sa_credential_max_lifetime_days")
    @classmethod
    def _validate_sa_credential_max_lifetime(cls, v: int) -> int:
        if v != -1 and not (1 <= v <= _SA_CREDENTIAL_MAX_LIFETIME_UPPER):
            msg = f"Must be -1 (unlimited) or between 1 and {_SA_CREDENTIAL_MAX_LIFETIME_UPPER}"
            raise ValueError(msg)
        return v


# =============================================================================
# Main Settings
# =============================================================================


def _get_env_file() -> str:
    """Get an optional custom .env file path."""
    return os.getenv("APP_ENV_FILE_PATH", ".env")


class Settings(
    ServiceAccountSettings,
    CredentialEncryptionSettings,
    OpenRouterSettings,
    FileUploadSettings,
    DocumentConversionSettings,
    FileStorageSettings,
    OpenAPIValidationSettings,
    APIDocsSettings,
    RouterDiscoverySettings,
    CacheSettings,
    DatabaseSettings,
    AuditSettings,
    AuditWriterSettings,
    ServerSettings,
    RetrieverServiceSettings,
    AdapterRetrySettings,
    LoggingSettings,
    TemporalSettings,
    S2STLSSettings,
    WorkflowEngineSettings,
    JWTSettings,
    ToolManagerSettings,
    WorkflowClientSettings,
    TelemetrySettings,
    MetricsSettings,
    AuthzSettings,
    OpenTelemetrySettings,
):
    """Application-wide settings.

    Combines all configuration sections into a single settings object.
    Defines the configuration for loading settings from environment variables and .env files.
    Additional settings can be added by inheriting from more BaseSettings classes.
    """

    model_config = SettingsConfigDict(
        env_file=_get_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="APP_",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cookie_secure(self) -> bool:
        """Derive the Secure flag for the refresh-token cookie from server_scheme.

        HTTPS → Secure=True (browser only sends the cookie over TLS).
        HTTP  → Secure=False (local development without TLS).
        """
        return self.server_scheme == "https"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def service_identity(self) -> str:
        """Derive service identity from the mTLS certificate CN.

        Raises RuntimeError if S2S TLS is not configured with a valid certificate.
        """
        if not self.s2s_tls_enabled or not self.s2s_tls_cert_path:
            msg = (
                "service_identity requires S2S TLS to be enabled with a valid certificate. "
                "Ensure certificates exist and APP_S2S_TLS_CERT_PATH points to the service certificate."
            )
            raise RuntimeError(msg)
        return _read_cert_cn(self.s2s_tls_cert_path)

    @model_validator(mode="after")
    def _derive_otel_service_name(self) -> "Settings":
        """Derive otel_service_name from product_name when not explicitly set."""
        if self.otel_service_name == type(self).model_fields["otel_service_name"].default:
            self.otel_service_name = self.product_name.lower().replace(" ", "-")
        return self

    @model_validator(mode="after")
    def _validate_cors_production(self) -> "Settings":
        """Warn when CORS origins are empty in production mode (AAP-71274).

        An empty ``cors_allow_origins`` with ``server_scheme=https`` means all
        cross-origin requests carrying cookies will be blocked, which breaks
        the frontend.  This is a warning rather than an error because CORS
        origins may eventually be a runtime setting.
        """
        if self.cookie_secure and not self.cors_allow_origins:
            warnings.warn(
                "CORS: cors_allow_origins is empty while server_scheme is https (production mode). "
                "Cross-origin requests with credentials will be blocked. "
                "Set APP_CORS_ALLOW_ORIGINS to the frontend origin(s).",
                UserWarning,
                stacklevel=1,
            )
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def jwt_issuer(self) -> str:
        """JWT issuer claim (iss) identifying this Nexus instance.

        Uses server_public_url when set, otherwise falls back to
        server_scheme://server_host:server_port.
        """
        if self.server_public_url:
            return str(self.server_public_url).rstrip("/")
        return f"{self.server_scheme}://{self.server_host}:{self.server_port}"


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings.

    Returns:
        Settings: Application configuration object

    Note:
        Settings are cached using lru_cache to avoid repeated .env file reads.
        Clear cache in tests if needed: get_settings.cache_clear()

    """
    return Settings()


def validate_encryption_key_at_startup() -> None:
    """Validate that a valid encryption key is configured.

    Must be called during app/worker startup, before serving requests.
    Raises RuntimeError if the key is missing or invalid.
    """
    settings = get_settings()
    if settings.secret_encryption_key is None:
        msg = (
            "APP_SECRET_ENCRYPTION_KEY (or APP_SECRET_ENCRYPTION_KEY_PATH) is required. "
            "Generate a key with:\n"
            "  openssl rand -hex 32\n"
            '  python -c "import secrets; print(secrets.token_hex(32))"'
        )
        raise RuntimeError(msg)


def get_encryption_key() -> SecretStr:
    """Get the encryption key, raising if not configured.

    Callers that need the encryption key should use this instead of
    accessing settings.secret_encryption_key directly to satisfy
    type narrowing (the field is Optional to allow import without secrets).
    """
    key = get_settings().secret_encryption_key
    if key is None:
        msg = "secret_encryption_key is not configured — was validate_encryption_key_at_startup() called?"
        raise RuntimeError(msg)
    return key
