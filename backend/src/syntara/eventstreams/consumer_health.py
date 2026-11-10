"""Process-local exec probes served by the worker's own event loop.

The probe client imports only the standard library and never contacts worker
dependencies. A stalled or exited process cannot answer a liveness request.
"""

import argparse
import asyncio
import socket
from collections.abc import Callable
from contextlib import suppress

HEALTH_HOST = "127.0.0.1"
HEALTH_PORT = 8765
HEALTH_TIMEOUT_SECONDS = 2


class EventWorkerHealth:
    """Answer bounded loopback requests without consulting external services."""

    def __init__(self, *, port: int = HEALTH_PORT) -> None:
        """Start unready; the entrypoint later attaches authoritative readiness."""
        self.port = port
        self._server: asyncio.Server | None = None
        self._ready: Callable[[], bool] = lambda: False
        self._closing = False

    def set_readiness(self, ready: Callable[[], bool]) -> None:
        """Read the manager's current state rather than storing a stale marker."""
        self._ready = ready

    def close_readiness(self) -> None:
        """Close readiness permanently before drain and shared-client teardown."""
        self._closing = True

    async def start(self) -> None:
        """Bind only loopback; no Kubernetes Service or public listener is needed."""
        self._server = await asyncio.start_server(self._respond, HEALTH_HOST, self.port)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        """Stop accepting probes after readiness has closed."""
        self.close_readiness()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _respond(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            async with asyncio.timeout(HEALTH_TIMEOUT_SECONDS):
                mode = await reader.readexactly(1)
                healthy = mode == b"L" or (mode == b"R" and not self._closing and self._ready())
                writer.write(b"1" if healthy else b"0")
                await writer.drain()
        except (OSError, TimeoutError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()


def probe(mode: str, *, port: int = HEALTH_PORT) -> bool:
    """Require a fresh response from this process, bounded below the exec timeout."""
    try:
        with socket.create_connection((HEALTH_HOST, port), timeout=HEALTH_TIMEOUT_SECONDS) as connection:
            connection.sendall(b"L" if mode == "live" else b"R")
            return connection.recv(1) == b"1"
    except OSError:
        return False


def main() -> int:
    """Return a conventional exec-probe exit code without loading app settings."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("live", "ready"))
    args = parser.parse_args()
    return 0 if probe(args.mode) else 1


if __name__ == "__main__":
    raise SystemExit(main())
