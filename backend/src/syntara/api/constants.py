"""Application-wide API constants.

This module contains global constants that don't change based on environment.
For configurable values, use get_settings() from syntara.core.config.base.
"""

# API configuration

API_V1_PATH_PREFIX = "/api/v1"
API_V1_VERSION = "0.1.0"

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
        f"{API_V1_PATH_PREFIX}/docs",
        f"{API_V1_PATH_PREFIX}/redoc",
        f"{API_V1_PATH_PREFIX}/openapi.json",
    }
)

# Prefix for paths that should be excluded via startswith matching
# (handles parameterised routes like /_internal/metrics/kpis/{component}).
EXCLUDED_PATH_PREFIXES: tuple[str, ...] = ("/_internal/",)
