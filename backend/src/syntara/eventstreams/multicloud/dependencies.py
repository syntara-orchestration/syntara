"""FastStream ``Depends`` providers — mostly HOLD, but must be re-wired per broker.

The provider callables here are transport-neutral: the same ``get_db_session`` and
``get_request_logger`` work on any broker. That is the good news.

The catch (see ``brokers/``): FastStream resolves ``Depends`` from a subscriber's
signature, and subscribers are broker-typed. So while the provider *functions* are
written once, the ``= Depends(get_db_session)`` wiring must be repeated in every
per-broker handler signature — the injection points do not carry across transports.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import structlog

logger = structlog.stdlib.get_logger(__name__)


async def get_db_session() -> AsyncIterator[Any]:
    """Yield a database session (stub).

    A real implementation would yield an ``AsyncSession`` from the app's engine and
    close it afterwards. FastStream supports async generator dependencies (setup /
    teardown around the handler) exactly like FastAPI — this is transport-neutral.
    """
    session: dict[str, Any] = {"_stub_session": True}
    try:
        yield session
    finally:
        # teardown (commit/rollback/close) would go here
        pass


def get_request_logger() -> structlog.stdlib.BoundLogger:
    """Return a bound logger for the current message (transport-neutral)."""
    return structlog.stdlib.get_logger("eventstream.multicloud")
