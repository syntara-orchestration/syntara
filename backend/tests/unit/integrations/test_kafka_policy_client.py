"""Exercise consumer socket policy through the installed aiokafka client."""

import asyncio
import socket
import struct
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiokafka.client
import pytest
from aiokafka import AIOKafkaConsumer
from aiokafka.client import ConnectionGroup
from aiokafka.errors import KafkaConnectionError
from aiokafka.protocol.admin import ApiVersionResponse_v0
from aiokafka.protocol.metadata import MetadataRequest_v0, MetadataRequest_v4, MetadataResponse_v0

from syntara.eventstreams.adapters.kafka_consumer import KafkaPartitionConsumer
from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration
from syntara.eventstreams.core.connection import ResolvedKafkaConnection
from syntara.integrations.lib.kafka_client import KafkaPolicyClient

pytestmark = [pytest.mark.asyncio, pytest.mark.ssrf_enforced]


@pytest.mark.parametrize("host", ["169.254.169.254", "127.0.0.1", "::1", "10.0.0.1"])
async def test_forbidden_bootstrap_never_opens_a_socket(host: str) -> None:
    """The actual bootstrap path enforces policy before any TCP connection."""
    client = KafkaPolicyClient(bootstrap_servers=[f"[{host}]:9093" if ":" in host else f"{host}:9093"])
    loop = asyncio.get_running_loop()
    try:
        with (
            patch.object(loop, "create_connection", new_callable=AsyncMock) as connect,
            patch(
                "syntara.integrations.lib.url_validation.get_settings",
                return_value=SimpleNamespace(integration_url_allowed_hosts=[]),
            ),
        ):
            with pytest.raises(KafkaConnectionError, match="permitted Kafka bootstrap"):
                await client.bootstrap()
            connect.assert_not_awaited()
    finally:
        await client.close()


@pytest.mark.parametrize("group", [ConnectionGroup.DEFAULT, ConnectionGroup.COORDINATION])
async def test_consumer_checks_advertised_brokers_and_reconnects(group: ConnectionGroup) -> None:  # noqa: PLR0915 - real wire protocol and cleanup regression
    """Real bootstrap/metadata/socket handling shares policy without global patches.

    Use allowed private test brokers, then change DNS to cloud metadata. Both
    normal and coordinator reconnections must fail without opening another socket.
    """
    writers: list[asyncio.StreamWriter] = []
    handlers: set[asyncio.Task[None]] = set()
    advertised_address = "127.0.0.1"
    port = 0

    async def respond(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        assert task is not None
        handlers.add(task)
        writers.append(writer)
        try:
            while True:
                size = struct.unpack(">i", await reader.readexactly(4))[0]
                request = await reader.readexactly(size)
                api_key = struct.unpack(">h", request[:2])[0]
                correlation_id = struct.unpack(">i", request[4:8])[0]
                response = (
                    ApiVersionResponse_v0(0, [(18, 0, 0), (3, 0, 0)])
                    if api_key == 18
                    else MetadataResponse_v0([(1, "advertised.example.com", port)], [])
                )
                body = struct.pack(">i", correlation_id) + response.encode()
                writer.write(struct.pack(">i", len(body)) + body)
                await writer.drain()
        except asyncio.IncompleteReadError:
            pass
        finally:
            writer.close()
            await writer.wait_closed()
            handlers.discard(task)

    server = await asyncio.start_server(respond, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    adapter = KafkaPartitionConsumer(
        ResolvedKafkaConnection(bootstrap_servers=[f"bootstrap.example.com:{port}"], security_protocol="PLAINTEXT"),
        KafkaSourceConfiguration(topic="events", group_id="policy-test"),
    )
    original_resolve = socket.getaddrinfo
    original_factory = vars(aiokafka.client)["create_conn"]

    def resolve(host: str, target_port: int, *args: Any, **kwargs: Any) -> object:  # noqa: ANN401 - socket.getaddrinfo boundary
        if host == "bootstrap.example.com":
            host = "127.0.0.1"
        elif host == "advertised.example.com":
            host = advertised_address
        return original_resolve(host, target_port, *args, **kwargs)

    settings = SimpleNamespace(integration_url_allowed_hosts=["bootstrap.example.com", "advertised.example.com"])
    try:
        # Retain real consumer construction and cleanup, invoking its installed
        # internal client directly so this fixture needs no full group protocol.
        with patch.object(AIOKafkaConsumer, "start", new_callable=AsyncMock):
            await adapter.start()
        assert adapter._consumer is not None
        client = adapter._consumer._client
        assert isinstance(client, KafkaPolicyClient)
        with (
            patch("socket.getaddrinfo", side_effect=resolve),
            patch("syntara.integrations.lib.kafka_connection.get_settings", return_value=settings),
            patch("syntara.integrations.lib.url_validation.get_settings", return_value=settings),
        ):
            async with asyncio.timeout(5):
                await client.bootstrap()
                assert len(writers) == 1
                # subscribe() requested metadata before bootstrap started its
                # background task. Settle that allowed connection before the
                # DNS change and the forbidden-reconnect socket assertion.
                metadata_update = client._md_update_fut
                assert metadata_update is not None
                assert await metadata_update
                connection = await client._get_conn(1, group=group)
                assert connection is not None
                assert connection.connected()
                expected_connections = 2 + int(group == ConnectionGroup.COORDINATION)
                assert len(writers) == expected_connections
                assert await client._get_conn(1, group=group) is connection
                closed = connection.close()
                if closed is not None:
                    await closed
                # A previously allowed hostname cannot bypass the cloud-metadata
                # prohibition, even though it is explicitly allowlisted.
                advertised_address = "169.254.169.254"
                with patch.object(asyncio.get_running_loop(), "create_connection", new_callable=AsyncMock) as connect:
                    assert await client._get_conn(1, group=group) is None
                    connect.assert_not_awaited()
                assert len(writers) == expected_connections
                assert vars(aiokafka.client)["create_conn"] is original_factory
    finally:
        await adapter.stop()
        server.close()
        await server.wait_closed()
        for writer in writers:
            writer.close()
        if handlers:
            await asyncio.gather(*handlers)


@pytest.mark.parametrize("group", [ConnectionGroup.DEFAULT, ConnectionGroup.COORDINATION])
async def test_forbidden_advertised_broker_never_opens_a_socket(group: ConnectionGroup) -> None:
    """Forbidden metadata addresses cannot open either kind of client connection."""
    client = KafkaPolicyClient()
    client.cluster.update_metadata(MetadataResponse_v0([(1, "169.254.169.254", 9093)], []))
    try:
        with patch.object(asyncio.get_running_loop(), "create_connection", new_callable=AsyncMock) as connect:
            assert await client._get_conn(1, group=group) is None
            connect.assert_not_awaited()
    finally:
        await client.close()


async def test_failed_metadata_shutdown_still_closes_owned_sockets() -> None:
    """A failed maintenance metadata task cannot bypass socket teardown."""
    client = KafkaPolicyClient()

    async def fail() -> None:
        msg = "metadata unavailable"
        raise OSError(msg)

    task = asyncio.create_task(fail())
    with pytest.raises(OSError):
        await task
    client._sync_task = task
    connection = MagicMock()
    client._conns[(1, ConnectionGroup.DEFAULT)] = connection
    with pytest.raises(OSError):
        await client.close()
    connection.close.assert_called_once()
    assert not client._conns
    assert client._sync_task is None


async def test_background_topic_metadata_cannot_create_a_missing_topic() -> None:
    client = KafkaPolicyClient()
    response = MetadataResponse_v0([(1, "broker.example.com", 9093)], [])
    client.cluster.update_metadata(response)
    connection = MagicMock()
    connection.send = AsyncMock(return_value=response)
    try:
        with patch.object(client, "_get_conn", new_callable=AsyncMock, return_value=connection):
            assert await client._metadata_update(client.cluster, {"missing-topic"})
        request = connection.send.await_args.args[0]
        modern = request.build(MetadataRequest_v4)
        assert modern.topics == ["missing-topic"]
        assert modern.allow_auto_topic_creation is False
        # Old protocols cannot disable creation of named topics. Request the
        # existing topic list instead, then let subscription lookup fail closed.
        assert request.build(MetadataRequest_v0).topics == []
    finally:
        await client.close()
