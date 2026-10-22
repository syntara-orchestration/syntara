"""Loopback-only process probes; never contact customer brokers or dependencies."""

import asyncio
import contextlib
import sys
from collections.abc import Callable
from http import HTTPStatus
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

from syntara.core.constants import EventWorkerDefaults

# Exec probes must not inherit deployment HTTP proxy settings.
_local_http = build_opener(ProxyHandler({}))


class EventWorkerHealthServer:
    """Serve process liveness and authoritative initial reconciliation readiness."""

    def __init__(self, ready: Callable[[], bool]) -> None:
        """Observe lifecycle state without opening database or transport clients."""
        self._ready = ready
        self._server: asyncio.Server | None = None

    async def __aenter__(self) -> "EventWorkerHealthServer":
        """Bind only inside the pod; packaging uses exec probes."""
        self._server = await asyncio.start_server(
            self._respond,
            EventWorkerDefaults.HEALTH_HOST,
            EventWorkerDefaults.HEALTH_PORT,
            limit=EventWorkerDefaults.HEALTH_REQUEST_LIMIT_BYTES,
        )
        return self

    async def __aexit__(self, *_exc: object) -> None:
        """Release the listener after the worker has drained."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _respond(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            async with asyncio.timeout(EventWorkerDefaults.HEALTH_TIMEOUT_SECONDS):
                request = await reader.readline()
                if request == b"GET /live HTTP/1.1\r\n":
                    status = "200 OK"
                elif request == b"GET /ready HTTP/1.1\r\n":
                    status = "200 OK" if self._ready() else "503 Service Unavailable"
                else:
                    status = "404 Not Found"
                writer.write(f"HTTP/1.1 {status}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".encode())
                await writer.drain()
        except (OSError, TimeoutError, ValueError):
            pass
        finally:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()


def probe(mode: str) -> int:
    """Return an exec-probe exit code using only the Python standard library."""
    if mode not in {"live", "ready"}:
        return 1
    url = f"http://{EventWorkerDefaults.HEALTH_HOST}:{EventWorkerDefaults.HEALTH_PORT}/{mode}"
    try:
        with _local_http.open(url, timeout=EventWorkerDefaults.HEALTH_TIMEOUT_SECONDS) as response:
            return 0 if response.status == HTTPStatus.OK else 1
    except (URLError, OSError, TimeoutError):
        return 1


if __name__ == "__main__":
    args = sys.argv[1:]
    sys.exit(probe(args[0] if args else ""))
