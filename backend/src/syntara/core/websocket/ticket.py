"""WebSocket ticket exchange for secure connection establishment.

Clients exchange a JWT (via Authorization header) for a short-lived,
single-use opaque ticket, then connect with ``?ticket=<ticket>`` instead
of passing the raw JWT as a query parameter.  This prevents token
leakage in server/proxy logs, browser history, and developer tools.
"""

from __future__ import annotations

import json
import secrets
from uuid import UUID

import structlog

from syntara.core.cache.base import BaseRedisClient
from syntara.core.cache.cache_client import CacheMixin
from syntara.core.constants import WebSocketConfig
from syntara.core.models import User

logger = structlog.stdlib.get_logger(__name__)

_KEY_PREFIX = "ws:ticket:"


class WebSocketTicketClient(BaseRedisClient, CacheMixin):
    """Redis-backed store for single-use WebSocket connection tickets."""

    _client_name: str = "websocket_ticket"

    async def issue_ticket(
        self,
        *,
        user_id: UUID,
        username: str,
        email: str | None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> tuple[str, int]:
        """Generate an opaque ticket and store the user identity in Redis.

        Returns:
            ``(ticket, ttl_seconds)`` — the raw ticket string and its TTL.

        """
        ticket = secrets.token_urlsafe(32)
        ttl = WebSocketConfig.TICKET_TTL_SECONDS
        payload = json.dumps(
            {
                "user_id": str(user_id),
                "username": username,
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        )
        await self.cache_setex(f"{_KEY_PREFIX}{ticket}", ttl, payload)
        logger.debug("ws_ticket_issued", username=username)
        return ticket, ttl

    async def redeem_ticket(self, ticket: str) -> User | None:
        """Atomically consume a ticket and return the associated ``User``.

        The ticket is deleted after the first read (single-use).
        Returns ``None`` if the ticket is invalid, expired, or already used.
        """
        key = f"{_KEY_PREFIX}{ticket}"
        raw = await self.cache_get(key)
        if raw is None:
            return None
        await self.cache_delete(key)
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("ws_ticket_corrupt", ticket_prefix=ticket[:8])
            return None
        return User(
            id=UUID(data["user_id"]),
            username=data["username"],
            email=data.get("email") or f"{data['username']}@unknown",
            first_name=data.get("first_name") or data["username"],
            last_name=data.get("last_name"),
            is_enabled=True,
        )


_client: WebSocketTicketClient | None = None


def get_ticket_client() -> WebSocketTicketClient:
    """Return the module-level singleton, creating it on first call."""
    global _client  # noqa: PLW0603
    if _client is None:
        _client = WebSocketTicketClient()
    return _client
