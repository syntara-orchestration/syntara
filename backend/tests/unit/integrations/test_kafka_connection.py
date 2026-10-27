"""Regressions at Kafka's DNS/socket and metadata boundaries."""

import asyncio
import ssl
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.integrations.lib.kafka_connection import KafkaHealthClient, _PinnedLoop, approved_broker_addresses


@pytest.mark.asyncio
@pytest.mark.parametrize("address", ["169.254.169.254", "127.0.0.1", "::1", "fd00::1"])
async def test_rebinding_never_reaches_socket(address: str) -> None:
    """A checked name cannot change to a forbidden socket address."""
    loop = MagicMock()
    loop.create_connection = AsyncMock()
    with (
        patch("syntara.integrations.lib.kafka_connection.validate_integration_url_no_ssrf"),
        patch(
            "syntara.integrations.lib.kafka_connection.get_settings",
            return_value=SimpleNamespace(integration_url_allowed_hosts=[]),
        ),
        patch.object(
            asyncio.get_running_loop(), "getaddrinfo", new=AsyncMock(return_value=[(2, 1, 6, "", (address, 9093))])
        ),
    ):
        with pytest.raises(ValueError):
            await _PinnedLoop(loop).create_connection(
                asyncio.Protocol, "broker.example.com", 9093, ssl=ssl.create_default_context()
            )
    loop.create_connection.assert_not_awaited()


@pytest.mark.asyncio
async def test_socket_is_pinned_and_keeps_tls_hostname() -> None:
    """TLS verifies the DNS name while TCP uses only the approved IP."""
    loop = MagicMock()
    transport = MagicMock(spec=asyncio.Transport)
    protocol = asyncio.Protocol()
    loop.create_connection = AsyncMock(return_value=(transport, protocol))
    tls_context = ssl.create_default_context()
    with patch(
        "syntara.integrations.lib.kafka_connection.approved_broker_addresses", new=AsyncMock(return_value=["8.8.8.8"])
    ):
        result = await _PinnedLoop(loop).create_connection(
            asyncio.Protocol, "broker.example.com", 9093, ssl=tls_context
        )
    assert result == (transport, protocol)
    loop.create_connection.assert_awaited_once_with(
        asyncio.Protocol, "8.8.8.8", 9093, ssl=tls_context, server_hostname="broker.example.com"
    )


@pytest.mark.asyncio
async def test_metadata_address_is_rejected_before_success() -> None:
    conn = MagicMock()
    conn.connect = AsyncMock()
    conn.send = AsyncMock(return_value=SimpleNamespace(brokers=[(1, "169.254.169.254", 9093)]))
    conn.close = AsyncMock()
    with patch("syntara.integrations.lib.kafka_connection._PinnedKafkaConnection", return_value=conn):
        client = KafkaHealthClient(
            bootstrap_servers=["broker.example.com:9093"],
            client_id="test",
            security_protocol="SSL",
            sasl_mechanism="PLAIN",
            sasl_plain_username=None,
            sasl_plain_password=None,
            ssl_context=None,
            request_timeout_ms=1000,
        )
        with pytest.raises(ValueError):
            await client.bootstrap()
    conn.close.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("port", [0, 65536, -1])
async def test_metadata_ports_are_validated(port: int) -> None:
    with pytest.raises(ValueError):
        await approved_broker_addresses("broker.example.com", port)


@pytest.mark.asyncio
async def test_pinned_connection_uses_upstream_streams_and_closes() -> None:
    """Exercise the upstream stream/protocol setup against a real local socket."""
    from syntara.integrations.lib.kafka_connection import _PinnedKafkaConnection

    async def accept(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(accept, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    conn = _PinnedKafkaConnection("broker.example.com", port, security_protocol="PLAINTEXT")
    try:
        with (
            patch(
                "syntara.integrations.lib.kafka_connection.approved_broker_addresses",
                new=AsyncMock(return_value=["127.0.0.1"]),
            ),
            patch.object(conn, "_do_version_lookup", new=AsyncMock()),
        ):
            reader, writer = await conn.connect()
            assert isinstance(reader, asyncio.StreamReader)
            assert isinstance(writer, asyncio.StreamWriter)
            closed = conn.close()
            if closed is not None:
                await closed
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("advertised_host", "accepted"), [("169.254.169.254", False), ("::1", False), ("fd00::1", False), ("8.8.8.8", True)]
)
async def test_wire_metadata_checks_advertised_brokers(advertised_host: str, *, accepted: bool) -> None:
    """Decode a real metadata response and accept only permitted broker addresses."""
    import socket
    import struct

    from aiokafka.protocol.admin import ApiVersionResponse_v0
    from aiokafka.protocol.metadata import MetadataResponse_v0

    async def respond(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            for _ in range(2):
                size = struct.unpack(">i", await reader.readexactly(4))[0]
                request = await reader.readexactly(size)
                api_key = struct.unpack(">h", request[:2])[0]
                correlation_id = struct.unpack(">i", request[4:8])[0]
                response = (
                    ApiVersionResponse_v0(0, [(18, 0, 0), (3, 0, 0)])
                    if api_key == 18
                    else MetadataResponse_v0([(1, advertised_host, 9093)], [])
                )
                body = struct.pack(">i", correlation_id) + response.encode()
                writer.write(struct.pack(">i", len(body)) + body)
                await writer.drain()
            await reader.read()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(respond, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    original_resolve = socket.getaddrinfo

    def resolve(host: str, port: int, *args: object, **kwargs: object) -> object:
        return original_resolve("127.0.0.1" if host == "broker.example.com" else host, port)

    client = KafkaHealthClient(
        bootstrap_servers=[f"broker.example.com:{port}"],
        client_id="test",
        security_protocol="PLAINTEXT",
        sasl_mechanism="PLAIN",
        sasl_plain_username=None,
        sasl_plain_password=None,
        ssl_context=None,
        request_timeout_ms=1000,
    )
    try:
        with (
            patch("socket.getaddrinfo", resolve),
            patch(
                "syntara.integrations.lib.kafka_connection.get_settings",
                return_value=SimpleNamespace(integration_url_allowed_hosts=["broker.example.com"]),
            ),
            patch(
                "syntara.integrations.lib.url_validation.get_settings",
                return_value=SimpleNamespace(integration_url_allowed_hosts=["broker.example.com"]),
            ),
        ):
            async with asyncio.timeout(3):
                if accepted:
                    await client.bootstrap()
                else:
                    with pytest.raises(ValueError):
                        await client.bootstrap()
    finally:
        await client.close()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_refused_socket_does_not_wait_for_a_nonexistent_connection_lost() -> None:
    """A failed TCP open keeps its connection error rather than becoming a timeout."""
    server = await asyncio.start_server(lambda _reader, _writer: None, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    server.close()
    await server.wait_closed()
    client = KafkaHealthClient(
        bootstrap_servers=[f"broker.example.com:{port}"],
        client_id="test",
        security_protocol="PLAINTEXT",
        sasl_mechanism="PLAIN",
        sasl_plain_username=None,
        sasl_plain_password=None,
        ssl_context=None,
        request_timeout_ms=1000,
    )
    with patch(
        "syntara.integrations.lib.kafka_connection.approved_broker_addresses", new=AsyncMock(return_value=["127.0.0.1"])
    ):
        async with asyncio.timeout(2):
            with pytest.raises(OSError):
                await client.bootstrap()
    await client.close()
