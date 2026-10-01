"""TLS utilities for integration-facing connections.

Builds the ``verify`` parameter for ``httpx.AsyncClient`` from
per-integration security fields (``insecure_skip_tls_verify``,
``ca_certificate``).
"""

from __future__ import annotations

import ssl


def build_integration_httpx_verify(
    *,
    insecure_skip_tls_verify: bool = False,
    ca_certificate: str | None = None,
) -> bool | ssl.SSLContext:
    """Build the ``verify`` parameter for ``httpx.AsyncClient``.

    Args:
        insecure_skip_tls_verify: Disable TLS certificate verification entirely.
        ca_certificate: PEM-encoded CA certificate to trust instead of the
            system default trust store.  Ignored when
            *insecure_skip_tls_verify* is ``True``.

    Returns:
        ``False`` when verification is disabled, an ``ssl.SSLContext`` when a
        custom CA is provided, or ``True`` for default system verification.

    """
    if insecure_skip_tls_verify:
        return False

    if ca_certificate and ca_certificate.strip():
        ctx = ssl.create_default_context()
        ctx.load_verify_locations(cadata=ca_certificate.strip())
        return ctx

    return True
