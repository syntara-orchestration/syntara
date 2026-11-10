"""Process-local probes: no broker, Redis, database or application imports."""

import asyncio
import socket
import sys
from unittest.mock import MagicMock

import pytest

from syntara.eventstreams import consumer_health as health_module
from syntara.eventstreams.consumer_health import EventWorkerHealth, probe


@pytest.fixture
async def health():
    server = EventWorkerHealth(port=0)
    await server.start()
    try:
        yield server
    finally:
        await server.stop()


async def test_live_before_reconciliation_and_readiness_tracks_current_state(health):
    assert await asyncio.to_thread(probe, "live", port=health.port)
    assert not await asyncio.to_thread(probe, "ready", port=health.port)
    ready = False
    health.set_readiness(lambda: ready)
    ready = True
    assert await asyncio.to_thread(probe, "ready", port=health.port)
    ready = False
    assert not await asyncio.to_thread(probe, "ready", port=health.port)
    assert await asyncio.to_thread(probe, "live", port=health.port)


async def test_shutdown_permanently_closes_readiness_while_drain_stays_live(health):
    health.set_readiness(lambda: True)
    health.close_readiness()
    health.set_readiness(lambda: True)
    assert not await asyncio.to_thread(probe, "ready", port=health.port)
    assert await asyncio.to_thread(probe, "live", port=health.port)
    await health.stop()
    assert not await asyncio.to_thread(probe, "live", port=health.port)


async def test_invalid_or_abandoned_probe_does_not_break_listener(health):
    reader, writer = await asyncio.open_connection(health_module.HEALTH_HOST, health.port)
    writer.write(b"X")
    await writer.drain()
    assert await reader.read(1) == b"0"
    writer.close()
    await writer.wait_closed()
    _, writer = await asyncio.open_connection(health_module.HEALTH_HOST, health.port)
    writer.close()
    await writer.wait_closed()
    assert await asyncio.to_thread(probe, "live", port=health.port)


def test_unresponsive_process_fails_within_probe_deadline(monkeypatch):
    monkeypatch.setattr(health_module, "HEALTH_TIMEOUT_SECONDS", 0.02)
    with socket.socket() as listener:
        listener.bind((health_module.HEALTH_HOST, 0))
        listener.listen()
        assert not probe("live", port=listener.getsockname()[1])


@pytest.mark.parametrize("mode", ["live", "ready"])
@pytest.mark.parametrize("healthy", [False, True])
def test_exec_probe_exit_codes(monkeypatch, mode, healthy):
    check = MagicMock(return_value=healthy)
    monkeypatch.setattr(health_module, "probe", check)
    monkeypatch.setattr(sys, "argv", ["consumer_health", mode])
    assert health_module.main() == (0 if healthy else 1)
    check.assert_called_once_with(mode)


async def test_packaged_module_works_from_a_separate_process():
    server = EventWorkerHealth()
    await server.start()
    try:
        for mode, expected in [("live", 0), ("ready", 1)]:
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "syntara.eventstreams.consumer_health", mode
            )
            assert await asyncio.wait_for(process.wait(), timeout=5) == expected
        server.set_readiness(lambda: True)
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "syntara.eventstreams.consumer_health", "ready"
        )
        assert await asyncio.wait_for(process.wait(), timeout=5) == 0
    finally:
        await server.stop()
