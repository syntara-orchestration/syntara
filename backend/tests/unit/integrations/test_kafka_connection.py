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
