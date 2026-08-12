"""SSL/TLS context construction for PostgreSQL database connections.

Builds the ``connect_args`` dictionary required by
:func:`sqlalchemy.ext.asyncio.create_async_engine` to enable TLS when
connecting via *asyncpg*.

.. important::

   The SQLAlchemy asyncpg dialect passes URL query parameters as keyword
   arguments to :func:`asyncpg.connect`, which does **not** accept
   ``sslmode``.  All SSL configuration must therefore go through
   ``connect_args={"ssl": ...}`` rather than the connection URL.

The mapping between PostgreSQL ``sslmode`` values and the ``ssl``
connect-arg:

* ``prefer`` — returns an empty dict; asyncpg defaults to ``prefer``
  when ``ssl`` is not supplied.
* ``disable`` / ``allow`` / ``require`` (without certificates) — the
  mode string is passed directly as ``{"ssl": "<mode>"}``.
* ``require`` (with client certificates) — an :class:`ssl.SSLContext`
  with ``CERT_NONE`` (encrypt only, no server verification).
* ``verify-ca`` — an :class:`ssl.SSLContext` with ``CERT_REQUIRED``
  and ``check_hostname=False``.
* ``verify-full`` — an :class:`ssl.SSLContext` with ``CERT_REQUIRED``
  and ``check_hostname=True``.
"""

from __future__ import annotations

import ssl
from typing import Any

_MODES_NEEDING_CONTEXT = frozenset({"verify-ca", "verify-full"})
_MODES_PASSTHROUGH = frozenset({"disable", "allow", "require"})


def build_ssl_connect_args(
    *,
    ssl_mode: str,
    ssl_root_cert: str | None = None,
    ssl_cert: str | None = None,
    ssl_key: str | None = None,
) -> dict[str, Any]:
    """Build the ``connect_args`` dict for asyncpg SSL connections.

    Returns a (possibly empty) mapping suitable for passing as the
    ``connect_args`` keyword argument to
    :func:`~sqlalchemy.ext.asyncio.create_async_engine`.

    Parameters
    ----------
    ssl_mode:
        PostgreSQL SSL mode (``disable``, ``allow``, ``prefer``,
        ``require``, ``verify-ca``, ``verify-full``).
    ssl_root_cert:
        Optional filesystem path to a PEM-encoded CA certificate bundle
        used for server certificate verification.
    ssl_cert:
        Optional filesystem path to a PEM-encoded client certificate
        (for mutual TLS).
    ssl_key:
        Optional filesystem path to the client private key corresponding
        to *ssl_cert*.

    Raises
    ------
    ValueError
        If *ssl_mode* is not a recognised PostgreSQL SSL mode.

    """
    has_client_certs = ssl_cert is not None

    if ssl_mode == "prefer":
        return {}

    if ssl_mode in _MODES_PASSTHROUGH and not has_client_certs:
        return {"ssl": ssl_mode}

    if ssl_mode in _MODES_NEEDING_CONTEXT or ssl_mode in _MODES_PASSTHROUGH:
        return {"ssl": _build_context(ssl_mode, ssl_root_cert, ssl_cert, ssl_key)}

    msg = f"Unknown SSL mode: {ssl_mode!r}"
    raise ValueError(msg)


def _build_context(
    ssl_mode: str,
    ssl_root_cert: str | None,
    ssl_cert: str | None,
    ssl_key: str | None,
) -> ssl.SSLContext:
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3

    if ssl_mode == "require":
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    elif ssl_mode == "verify-ca":
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_REQUIRED
    elif ssl_mode == "verify-full":
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED

    if ssl_root_cert is not None:
        ctx.load_verify_locations(cafile=ssl_root_cert)

    if ssl_cert is not None:
        ctx.load_cert_chain(certfile=ssl_cert, keyfile=ssl_key)

    return ctx
