"""Probes follow reconciliation state without consulting brokers or Redis."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from syntara.core.constants import EventWorkerDefaults
from syntara.eventstreams import consumer_health as health


async def test_probes_track_initial_reconciliation_idle_and_shutdown(monkeypatch):
    monkeypatch.setattr(EventWorkerDefaults, "HEALTH_PORT", 0)
    ready = False
    async with health.EventWorkerHealthServer(lambda: ready) as server:
        monkeypatch.setattr(EventWorkerDefaults, "HEALTH_PORT", server._server.sockets[0].getsockname()[1])
        assert await asyncio.to_thread(health.probe, "live") == 0
        assert await asyncio.to_thread(health.probe, "ready") == 1
        ready = True  # Successful empty reconciliation is sufficient.
        assert await asyncio.to_thread(health.probe, "ready") == 0
        ready = False  # Admission closes before shutdown drain.
        assert await asyncio.to_thread(health.probe, "ready") == 1
        assert await asyncio.to_thread(health.probe, "live") == 0
    assert await asyncio.to_thread(health.probe, "live") == 1


@pytest.mark.parametrize("request_line", [b"GET /unknown HTTP/1.1\r\n", b"POST /ready HTTP/1.1\r\n"])
async def test_listener_rejects_unknown_routes_and_methods(request_line):
    reader = AsyncMock()
    reader.readline.return_value = request_line
    writer = MagicMock()
    writer.drain = AsyncMock()
    writer.wait_closed = AsyncMock()
    await health.EventWorkerHealthServer(lambda: True)._respond(reader, writer)
    assert b"404 Not Found" in writer.write.call_args.args[0]
    writer.close.assert_called_once()


@pytest.mark.parametrize("error", [OSError(), TimeoutError(), ValueError("request limit exceeded")])
async def test_listener_closes_failed_or_oversized_requests(error):
    reader = AsyncMock()
    reader.readline.side_effect = error
    writer = MagicMock()
    writer.wait_closed = AsyncMock()
    await health.EventWorkerHealthServer(lambda: True)._respond(reader, writer)
    writer.write.assert_not_called()
    writer.close.assert_called_once()


def test_unknown_probe_does_not_open_a_connection(monkeypatch):
    connect = MagicMock()
    monkeypatch.setattr(health._local_http, "open", connect)
    assert health.probe("unknown") == 1
    connect.assert_not_called()
