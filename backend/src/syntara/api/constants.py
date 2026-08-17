"""Application-wide API constants.

This module contains global constants that don't change based on environment.
For configurable values, use get_settings() from syntara.core.config.base.
"""

# API configuration

API_V1_PATH_PREFIX = "/api/v1"
API_DOCS_V1_PATH_PREFIX = "/api_docs/v1"
API_V1_VERSION = "1.0.0"

# Full doc endpoint paths (concat avoids Sonar treating {PREFIX} in FastAPI
# route decorators as path parameters).
API_DOCS_V1_DOCS_PATH = API_DOCS_V1_PATH_PREFIX + "/docs"
API_DOCS_V1_REDOC_PATH = API_DOCS_V1_PATH_PREFIX + "/redoc"
API_DOCS_V1_OPENAPI_PATH = API_DOCS_V1_PATH_PREFIX + "/openapi.json"

# Full path to the OIDC callback endpoint, used by the auth router and
# referenced by the AAP setup service when registering redirect URIs.
OIDC_CALLBACK_PATH = f"{API_V1_PATH_PREFIX}/auth/oidc/callback"

# Paths excluded from middleware instrumentation (analytics, metrics).
# Health checks, discovery endpoints, and documentation endpoints are
# not business API endpoints and would generate noise in observability
# data.
EXCLUDED_PATHS: frozenset[str] = frozenset(
    {
        "/health",
        "/healthz/live",
        "/healthz/ready",
        "/api",
        "/api/v1",
        "/docs",
        API_DOCS_V1_DOCS_PATH,
        API_DOCS_V1_REDOC_PATH,
        API_DOCS_V1_OPENAPI_PATH,
    }
)

# Prefix for paths that should be excluded via startswith matching
# (handles parameterised routes like /_internal/metrics/kpis/{component}).
# Any path under these prefixes bypasses audit, metrics, cert, and rate-limit middleware.
EXCLUDED_PATH_PREFIXES: tuple[str, ...] = ("/_internal/", "/api_docs/")
