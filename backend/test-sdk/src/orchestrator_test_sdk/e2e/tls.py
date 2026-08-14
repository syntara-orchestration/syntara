"""TLS helpers for E2E tests."""

from __future__ import annotations

import os
import ssl
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def e2e_ssl_context() -> ssl.SSLContext | bool:
    """Build an SSL context for E2E tests.

    When APP_S2S_TLS_CA_CERT_PATH is set, returns an SSLContext that
    trusts that CA (for verifying self-signed ingress certificates).

    When APP_S2S_TLS_CERT_PATH and APP_S2S_TLS_KEY_PATH are also set,
    loads the client certificate and key for mutual TLS (mTLS).

    When APP_HTTP_CLIENT_VERIFY_SSL is explicitly "false", disables
    server certificate verification entirely.

    Otherwise returns False to skip server verification.
    """
    ca = os.environ.get("APP_S2S_TLS_CA_CERT_PATH")
    cert = os.environ.get("APP_S2S_TLS_CERT_PATH")
    key = os.environ.get("APP_S2S_TLS_KEY_PATH")
    verify_ssl = os.environ.get("APP_HTTP_CLIENT_VERIFY_SSL", "true").lower()

    if not (ca and Path(ca).exists()) and verify_ssl == "false":
        return False

    if not (ca and Path(ca).exists()):
        return False

    ctx = ssl.create_default_context(cafile=ca)
    ctx.check_hostname = False

    if verify_ssl == "false":
        ctx.verify_mode = ssl.CERT_NONE

    if cert and key and Path(cert).exists() and Path(key).exists():
        ctx.load_cert_chain(certfile=cert, keyfile=key)

    return ctx
