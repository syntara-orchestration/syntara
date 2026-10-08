"""SSL context builder for Kafka connections.

aiokafka takes a standard :class:`ssl.SSLContext` (unlike Temporal's ``TLSConfig``).
This builds one from a :class:`~syntara.eventstreams.core.connection.TlsMaterial`,
supporting server verification and optional mutual TLS — the same PEM material the
rest of the platform uses for service-to-service TLS.
"""

from __future__ import annotations

import ssl
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from syntara.eventstreams.core.connection import TlsMaterial


def build_kafka_ssl_context(tls: TlsMaterial | None) -> ssl.SSLContext | None:
    """Build an SSL context for an aiokafka producer/consumer.

    Returns ``None`` when no TLS material is supplied (the caller then connects
    without TLS). When ``ca_cert_path`` is set the server is verified; when a
    client ``cert_path`` + ``key_path`` are also set, mutual TLS is used.
    """
    if tls is None or tls.ca_cert_path is None:
        return None

    context = ssl.create_default_context(cafile=tls.ca_cert_path)
    if tls.cert_path is not None and tls.key_path is not None:
        context.load_cert_chain(certfile=tls.cert_path, keyfile=tls.key_path)
    return context
