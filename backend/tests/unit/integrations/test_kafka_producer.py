"""Publish keeps upstream producer behavior while pinning every new socket."""

import asyncio
import inspect
import socket
import struct
from collections.abc import AsyncIterator
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from aiokafka.client import AIOKafkaClient
from aiokafka.conn import CloseReason
from aiokafka.protocol.admin import ApiVersionResponse_v0
from aiokafka.protocol.metadata import MetadataResponse_v0

from syntara.integrations.lib import kafka_connection, kafka_producer


@dataclass
class Broker:
    """A local Kafka metadata endpoint with a separately advertised hostname."""

    port: int = 0
    advertised_host: str = "advertised.example.com"
    connections: int = 0


@pytest_asyncio.fixture
async def broker() -> AsyncIterator[Broker]:
    """Answer real version and metadata requests without running a Kafka service."""
    state = Broker()
    writers: set[asyncio.StreamWriter] = set()
    tasks: set[asyncio.Task[None]] = set()

    async def respond(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        state.connections += 1
        writers.add(writer)
        try:
            while True:
                size = struct.unpack(">i", await reader.readexactly(4))[0]
                request = await reader.readexactly(size)
                api_key = struct.unpack(">h", request[:2])[0]
                correlation_id = struct.unpack(">i", request[4:8])[0]
                response = (
                    ApiVersionResponse_v0(0, [(18, 0, 0), (3, 0, 0)])
                    if api_key == 18
                    else MetadataResponse_v0([(1, state.advertised_host, state.port)], [])
                )
                body = struct.pack(">i", correlation_id) + response.encode()
                writer.write(struct.pack(">i", len(body)) + body)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writers.discard(writer)
            writer.close()
            await writer.wait_closed()

    def accept(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.create_task(respond(reader, writer))
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    server = await asyncio.start_server(accept, "127.0.0.1", 0)
    state.port = server.sockets[0].getsockname()[1]
    try:
        yield state
    finally:
        server.close()
        await server.wait_closed()
        for writer in tuple(writers):
            writer.close()
        if tasks:
            await asyncio.gather(*tasks)


def _dns_policy(monkeypatch: pytest.MonkeyPatch, addresses: list[str], allowed_hosts: list[str]) -> AsyncMock:
    """Keep real numeric-address policy checks while controlling DNS answers."""
    monkeypatch.setattr(kafka_connection, "validate_integration_url_no_ssrf", MagicMock())
    settings = MagicMock(integration_url_allowed_hosts=allowed_hosts)
    monkeypatch.setattr(kafka_connection, "get_settings", lambda: settings)
    dns = AsyncMock(
        side_effect=[[(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 9093))] for address in addresses]
    )
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", dns)
    return dns


def test_all_upstream_connection_entrypoints_are_covered() -> None:
    """An aiokafka upgrade must not silently add an unpinned factory call."""
    entrypoints = {
        name
        for name, method in vars(AIOKafkaClient).items()
        if inspect.isfunction(method) and "create_conn" in method.__code__.co_names
    }
    assert entrypoints == {"bootstrap", "_get_conn"}


async def test_bootstrap_metadata_connections_and_reconnects_are_pinned(
    broker: Broker, monkeypatch: pytest.MonkeyPatch
) -> None:
    approved = AsyncMock(return_value=["127.0.0.1"])
    monkeypatch.setattr(kafka_connection, "approved_broker_addresses", approved)
    upstream_factory = AIOKafkaClient.bootstrap.__globals__["create_conn"]
    producer = kafka_producer.create_kafka_publish_producer(
        bootstrap_servers=[f"bootstrap.example.com:{broker.port}"], acks="all", enable_idempotence=True
    )
    try:
        async with asyncio.timeout(3):
            await producer.client.bootstrap()
            first = await producer.client._get_conn(1)
            assert first is not None
            assert await producer.client._get_conn(1) is first
            await first.close(reason=CloseReason.IDLE_DROP)
            replacement = await producer.client._get_conn(1)
            assert replacement is not None
            assert replacement is not first
        assert [call.args for call in approved.await_args_list] == [
            ("bootstrap.example.com", broker.port),
            (broker.advertised_host, broker.port),
            (broker.advertised_host, broker.port),
        ]
        assert broker.connections == 3
        assert AIOKafkaClient.bootstrap.__globals__["create_conn"] is upstream_factory
        assert AIOKafkaClient._get_conn.__globals__["create_conn"] is upstream_factory
    finally:
        await producer.stop()


async def test_forbidden_bootstrap_never_opens_a_socket(broker: Broker, monkeypatch: pytest.MonkeyPatch) -> None:
    _dns_policy(monkeypatch, ["127.0.0.1"], [])
    producer = kafka_producer.create_kafka_publish_producer(bootstrap_servers=[f"bootstrap.example.com:{broker.port}"])
    try:
        with pytest.raises(ValueError):
            await producer.client.bootstrap()
        assert broker.connections == 0
    finally:
        await producer.stop()


@pytest.mark.parametrize("address", ["169.254.169.254", "127.0.0.1", "::1", "fd00::1"])
async def test_forbidden_metadata_broker_never_opens_a_socket(
    broker: Broker, monkeypatch: pytest.MonkeyPatch, address: str
) -> None:
    broker.advertised_host = address
    _dns_policy(monkeypatch, ["127.0.0.1", address], ["bootstrap.example.com"])
    producer = kafka_producer.create_kafka_publish_producer(bootstrap_servers=[f"bootstrap.example.com:{broker.port}"])
    try:
        async with asyncio.timeout(3):
            await producer.client.bootstrap()
            with pytest.raises(ValueError):
                await producer.client._get_conn(1)
        assert broker.connections == 1
    finally:
        await producer.stop()


async def test_reconnect_rejects_changed_dns_even_for_an_allowed_hostname(
    broker: Broker, monkeypatch: pytest.MonkeyPatch
) -> None:
    dns = _dns_policy(
        monkeypatch,
        ["127.0.0.1", "127.0.0.1", "169.254.169.254"],
        ["bootstrap.example.com", broker.advertised_host],
    )
    producer = kafka_producer.create_kafka_publish_producer(bootstrap_servers=[f"bootstrap.example.com:{broker.port}"])
    try:
        async with asyncio.timeout(3):
            await producer.client.bootstrap()
            connection = await producer.client._get_conn(1)
            assert connection is not None
            await connection.close(reason=CloseReason.IDLE_DROP)
            with pytest.raises(ValueError):
                await producer.client._get_conn(1)
        assert broker.connections == 2
        assert dns.await_count == 3
    finally:
        await producer.stop()
