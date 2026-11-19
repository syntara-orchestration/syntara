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


@pytest.mark.parametrize("port", [-1, 0, 22, 443, 1023, 65536, 2**32, 8768.0, "8768", None, True])
def test_invalid_probe_ports_are_rejected_before_connecting(monkeypatch, port):
    connect = MagicMock()
    monkeypatch.setattr(health_module.socket, "create_connection", connect)
    with pytest.raises(ValueError, match="integer between 1024 and 65535"):
        probe("live", port=port)
    connect.assert_not_called()


@pytest.mark.parametrize("port", [1024, health_module.HEALTH_PORT, 65535])
def test_valid_probe_ports_connect_only_to_fixed_loopback(monkeypatch, port):
    connect = MagicMock()
    connect.return_value.__enter__.return_value.recv.return_value = b"1"
    monkeypatch.setattr(health_module.socket, "create_connection", connect)
    assert probe("live", port=port)
    connect.assert_called_once_with(("127.0.0.1", port), timeout=health_module.HEALTH_TIMEOUT_SECONDS)


@pytest.mark.parametrize(
    "arguments",
    [
        ["live", "--port", "-1"],
        ["ready", "--port", "0"],
        ["live", "--port", "22"],
        ["live", "--port", "1023"],
        ["ready", "--port", "65536"],
        ["live", "--port", "not-a-port"],
        ["live", "--port", "8768.0"],
        ["live", "--port", "127.0.0.1:8768"],
        ["live", "--host", "example.com"],
        ["live", "--port"],
        ["unknown"],
        [],
    ],
)
def test_invalid_probe_arguments_exit_one_without_connecting(monkeypatch, capsys, arguments):
    connect = MagicMock()
    monkeypatch.setattr(health_module.socket, "create_connection", connect)
    monkeypatch.setattr(sys, "argv", ["consumer_health", *arguments])
    assert health_module.main() == 1
    connect.assert_not_called()
    error = capsys.readouterr().err
    assert "error:" in error
    assert "Traceback" not in error


def test_probe_help_exits_successfully_without_connecting(monkeypatch, capsys):
    connect = MagicMock()
    monkeypatch.setattr(health_module.socket, "create_connection", connect)
    monkeypatch.setattr(sys, "argv", ["consumer_health", "--help"])
    assert health_module.main() == 0
    connect.assert_not_called()
    assert "usage:" in capsys.readouterr().out


@pytest.mark.parametrize("mode", ["live", "ready"])
@pytest.mark.parametrize("healthy", [False, True])
@pytest.mark.parametrize("port", [None, 12345])
def test_exec_probe_exit_codes(monkeypatch, mode, healthy, port):
    check = MagicMock(return_value=healthy)
    monkeypatch.setattr(health_module, "probe", check)
    arguments = ["consumer_health", mode]
    if port is not None:
        arguments += ["--port", str(port)]
    monkeypatch.setattr(sys, "argv", arguments)
    assert health_module.main() == (0 if healthy else 1)
    check.assert_called_once_with(mode, port=health_module.HEALTH_PORT if port is None else port)


async def test_packaged_module_works_from_a_separate_process(health):
    for mode, expected in [("live", 0), ("ready", 1)]:
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "syntara.eventstreams.consumer_health", mode, "--port", str(health.port)
        )
        assert await asyncio.wait_for(process.wait(), timeout=5) == expected
    health.set_readiness(lambda: True)
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "syntara.eventstreams.consumer_health", "ready", "--port", str(health.port)
    )
    assert await asyncio.wait_for(process.wait(), timeout=5) == 0


@pytest.mark.parametrize("port", ["22", "65536", "not-a-port"])
async def test_packaged_module_rejects_invalid_ports(port):
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "syntara.eventstreams.consumer_health",
        "live",
        "--port",
        port,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, error = await asyncio.wait_for(process.communicate(), timeout=5)
    assert process.returncode == 1
    assert b"error:" in error
    assert b"Traceback" not in error
