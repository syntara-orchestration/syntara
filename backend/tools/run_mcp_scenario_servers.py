"""Standalone runner for auxiliary MCP servers used by auth-failure E2E tests.

Runs two long-lived MCP servers side by side:

- An auth-required server (rejects unauthenticated requests with 401), used
  to verify the MCP adapter classifies unauthorized integrations as
  AUTH_FAILURE.
- A forbidden server (rejects all requests with 403), used to verify the
  adapter classifies forbidden integrations as AUTH_FAILURE.

These are deployed as a compose service reachable from the syntara backend via a
stable network name (see podman-compose.yml). Earlier revisions of the E2E tests
spun these servers up ad hoc in the pytest process and pointed the backend at
them via ``host.containers.internal``, which under Podman's pasta network
backend resolves to a 169.254.0.0/16 link-local address that is unconditionally
blocked by SSRF cloud-metadata protection. Running these as real,
independently-addressable services avoids that problem.
"""

import asyncio
import os
import signal
from contextlib import suppress

import structlog
from fastmcp.server.auth import StaticTokenVerifier
from orchestrator_test_sdk.app.mcp_servers import ExampleMCPServer, ForbiddenMCPServer

logger = structlog.stdlib.get_logger(__name__)

# Fixed token expected by test_mcp_provider_connection_failure_unauthorized.
_AUTH_TOKEN = "an-api-key"  # noqa: S105


async def main() -> None:
    """Run both auxiliary MCP servers until interrupted."""
    # Use "127.0.0.1" instead of "0.0.0.0" for security unless explicitly overridden
    host = os.getenv("MCP_HOST", "127.0.0.1")
    auth_port = int(os.getenv("MCP_AUTH_PORT", "8766"))
    forbidden_port = int(os.getenv("MCP_FORBIDDEN_PORT", "8767"))

    auth_server = ExampleMCPServer(host=host, port=auth_port, auth=StaticTokenVerifier(tokens={_AUTH_TOKEN: {}}))
    forbidden_server = ForbiddenMCPServer(host=host, port=forbidden_port)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _request_shutdown(sig: signal.Signals) -> None:
        logger.info("Received signal, shutting down", signal=sig.name)
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _request_shutdown, sig)

    logger.info("Starting MCP scenario servers", host=host, auth_port=auth_port, forbidden_port=forbidden_port)

    try:
        await asyncio.gather(auth_server.start(), forbidden_server.start())
        logger.info(
            "MCP scenario servers ready",
            auth_endpoint=auth_server.base_url,
            forbidden_endpoint=forbidden_server.base_url,
        )
        logger.info("Press Ctrl+C to stop")
        await stop_event.wait()
    finally:
        logger.info("Stopping MCP scenario servers...")
        with suppress(asyncio.CancelledError):
            await asyncio.gather(auth_server.stop(), forbidden_server.stop())
        logger.info("MCP scenario servers stopped")


if __name__ == "__main__":
    asyncio.run(main())
