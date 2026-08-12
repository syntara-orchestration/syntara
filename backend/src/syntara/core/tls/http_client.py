"""Internal service-to-service HTTP client factory with optional mTLS."""

from __future__ import annotations

import ssl
from functools import lru_cache
from typing import Any, cast

import httpx

from syntara.core.config.base import get_settings


@lru_cache(maxsize=1)
def build_internal_ssl_context() -> ssl.SSLContext | None:
    """Build an SSL context for internal S2S HTTP clients.

    Returns None when S2S TLS is disabled. Returns an SSLContext
    configured with the CA bundle and client certificate when enabled.

    The result is cached since settings and cert files are stable for
    the lifetime of the process.
    """
    settings = get_settings()
    if not settings.s2s_tls_enabled:
        return None

    ctx = ssl.create_default_context(
        ssl.Purpose.SERVER_AUTH,
        cafile=cast("str", settings.s2s_tls_ca_cert_path),
    )
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.load_cert_chain(
        certfile=cast("str", settings.s2s_tls_cert_path),
        keyfile=cast("str", settings.s2s_tls_key_path),
    )
    return ctx


def build_internal_http_client(**kwargs: Any) -> httpx.AsyncClient:  # noqa: ANN401 - passthrough to httpx.AsyncClient
    """Create an httpx.AsyncClient with optional mTLS for internal S2S calls.

    Accepts all the same kwargs as httpx.AsyncClient. When S2S TLS
    is enabled, injects the SSL context via the ``verify`` parameter.
    When disabled, returns a plain client (local development default).
    """
    ssl_context = build_internal_ssl_context()
    if ssl_context is not None:
        kwargs.setdefault("verify", ssl_context)
    return httpx.AsyncClient(**kwargs)
