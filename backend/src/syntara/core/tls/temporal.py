"""Temporal gRPC TLS configuration builder."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import cast

from temporalio.service import TLSConfig

from syntara.core.config.base import get_settings


@lru_cache(maxsize=1)
def build_temporal_tls_config() -> TLSConfig | None:
    """Build TLS config for Temporal Client.connect().

    Returns None when S2S TLS is disabled (plaintext gRPC, the default).
    Returns a TLSConfig with mTLS certificates when enabled.

    The result is cached since settings and cert files are stable for
    the lifetime of the process.
    """
    settings = get_settings()
    if not settings.s2s_tls_enabled:
        return None

    return TLSConfig(
        server_root_ca_cert=Path(cast("str", settings.s2s_tls_ca_cert_path)).read_bytes(),
        client_cert=Path(cast("str", settings.s2s_tls_cert_path)).read_bytes(),
        client_private_key=Path(cast("str", settings.s2s_tls_key_path)).read_bytes(),
    )
