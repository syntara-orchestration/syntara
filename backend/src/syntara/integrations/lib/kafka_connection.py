"""Short-lived Kafka health connections with address pinning.

Only this connection's event-loop view changes. The real loop and aiokafka's
module globals are never patched. aiokafka remains responsible for Kafka framing,
version negotiation, SASL, and TLS; the socket boundary enforces our SSRF policy.
"""

from __future__ import annotations

import asyncio
import inspect
import socket
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    import ssl
    from collections.abc import Callable

from aiokafka.conn import AIOKafkaConnection, collect_hosts
from aiokafka.errors import KafkaConnectionError, KafkaError
from aiokafka.protocol.metadata import MetadataRequest

from syntara.core.config.base import get_settings
from syntara.core.lib.url_validation import validate_url_no_ssrf
from syntara.integrations.lib.url_validation import validate_integration_url_no_ssrf
from syntara.integrations.models.integration_configuration import parse_bootstrap_server


def _broker_url(host: str, port: int) -> str:
    address = f"[{host}]" if ":" in host else host
    return f"https://{parse_bootstrap_server(f'{address}:{port}')}"


async def approved_broker_addresses(host: str, port: int) -> list[str]:
    """Resolve a broker, validate every answer, and return approved numeric IPs.

    The second resolution is deliberately checked independently: if DNS changes
    after the hostname policy check, the actual addresses selected for the socket
    still must pass policy. Cloud metadata remains blocked even when allowlisted.
    """
    await asyncio.to_thread(validate_integration_url_no_ssrf, _broker_url(host, port))
    loop = asyncio.get_running_loop()
    answers = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses = list(dict.fromkeys(str(answer[4][0]) for answer in answers))
    if not addresses:
        msg = "Kafka broker did not resolve to an address"
        raise ValueError(msg)
    allowed_hosts = {host.lower() for host in get_settings().integration_url_allowed_hosts}
    for address in addresses:
        await asyncio.to_thread(
            validate_url_no_ssrf,
            _broker_url(address, port),
            allowed_hosts=[address] if host.lower() in allowed_hosts else [],
        )
    return addresses


class _PinnedLoop:
    """Delegate loop operations while pinning just this Kafka socket connection."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def __getattr__(self, name: str) -> object:
        return getattr(self._loop, name)

    async def create_connection(
        self,
        protocol_factory: Callable[[], asyncio.BaseProtocol],
        host: str,
        port: int,
        *,
        ssl: ssl.SSLContext | None = None,
    ) -> tuple[asyncio.Transport, asyncio.BaseProtocol]:
        """Connect to an approved numeric IP and preserve the TLS identity."""
        addresses = await approved_broker_addresses(host, port)

        last_error: OSError | None = None
        for address in addresses:
            try:
                return await self._loop.create_connection(
                    protocol_factory, address, port, ssl=ssl, server_hostname=host if ssl is not None else None
                )
            except OSError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        msg = "No approved Kafka broker address"
        raise KafkaConnectionError(msg)


# aiokafka 0.14 has no type declarations for its connection implementation.
class _PinnedKafkaConnection(AIOKafkaConnection):  # type: ignore[misc]
    """Use upstream framing/authentication with a connection-local pinned loop."""

    _loop: Any

    async def connect(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Open the upstream connection through the pinned socket boundary."""
        original_loop = self._loop
        self._loop = _PinnedLoop(original_loop)
        try:
            return cast("tuple[asyncio.StreamReader, asyncio.StreamWriter]", await super().connect())
        finally:
            self._loop = original_loop

    def close(self, reason: object = None, exc: BaseException | None = None) -> asyncio.Future[None] | None:
        """Abort a health-check socket without an unbounded TLS shutdown wait.

        Upstream creates its closed future before opening a socket. A failed
        DNS/TCP/TLS setup may never call connection_lost, so that future must
        not be awaited when no stream was established.
        """
        writer = getattr(self, "_writer", None)
        closed = super().close(reason=reason, exc=exc)
        if writer is None:
            if closed is not None and not closed.done():
                closed.cancel()
            return None
        writer.transport.abort()
        return cast("asyncio.Future[None] | None", closed)


class KafkaHealthClient:
    """Read one metadata response without starting a background metadata client.

    No advertised broker is contacted by this check. Each call resolves and
    pins its own socket without a process-wide recorder or background client.
    """

    def __init__(
        self,
        *,
        bootstrap_servers: list[str],
        client_id: str,
        security_protocol: str,
        sasl_mechanism: str,
        sasl_plain_username: str | None,
        sasl_plain_password: str | None,
        ssl_context: ssl.SSLContext | None,
        request_timeout_ms: int,
    ) -> None:
        """Keep connection settings local to this health check."""
        self._servers = bootstrap_servers
        self._kwargs = {
            "client_id": client_id,
            "security_protocol": security_protocol,
            "sasl_mechanism": sasl_mechanism,
            "sasl_plain_username": sasl_plain_username,
            "sasl_plain_password": sasl_plain_password,
            "ssl_context": ssl_context,
            "request_timeout_ms": request_timeout_ms,
        }
        self._connection: _PinnedKafkaConnection | None = None

    async def bootstrap(self) -> None:
        """Authenticate and read metadata without a background client."""
        last_error: Exception | None = None
        for host, port, _ in collect_hosts(self._servers):
            conn = _PinnedKafkaConnection(host, port, **self._kwargs)
            self._connection = conn
            try:
                await conn.connect()
                await conn.send(MetadataRequest([]))
                return
            except (OSError, KafkaError, TimeoutError) as exc:
                last_error = exc
            finally:
                closed = conn.close()
                if inspect.isawaitable(closed):
                    await closed
                self._connection = None
        if last_error is not None:
            raise last_error
        msg = "No Kafka bootstrap servers configured"
        raise KafkaConnectionError(msg)

    async def close(self) -> None:
        """Close any connection left by cancellation or a failed check."""
        if self._connection is not None:
            closed = self._connection.close()
            if inspect.isawaitable(closed):
                await closed
            self._connection = None
