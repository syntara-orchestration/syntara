"""Centralised audit/telemetry handler registration.

Provides :func:`discover_and_register_all_handlers` so the API server,
Temporal worker, and any other entry-point can share a single handler
list without duplicating imports or discovery calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

import syntara.aap.audit
import syntara.agent_orchestrator.audit
import syntara.approvals.audit
import syntara.audit.events
import syntara.auth.audit
import syntara.authz.audit
import syntara.core.websocket.audit
import syntara.credentials.audit
import syntara.files.audit
import syntara.identity_providers.audit
import syntara.integrations.audit
import syntara.settings.audit
import syntara.telemetry.handlers
import syntara.workflows.audit
from syntara.audit.discovery import discover_handlers
from syntara.audit.dispatcher import AuditEventDispatcher

if TYPE_CHECKING:
    from types import ModuleType

logger = structlog.stdlib.get_logger(__name__)


def _handler_packages() -> list[ModuleType]:
    """Return the ordered list of packages that contain audit/telemetry handlers."""
    return [
        syntara.aap.audit,
        syntara.agent_orchestrator.audit,
        syntara.approvals.audit,
        syntara.audit.events,
        syntara.auth.audit,
        syntara.authz.audit,
        syntara.core.websocket.audit,
        syntara.credentials.audit,
        syntara.files.audit,
        syntara.identity_providers.audit,
        syntara.integrations.audit,
        syntara.settings.audit,
        syntara.telemetry.handlers,
        syntara.workflows.audit,
    ]


def discover_and_register_all_handlers() -> None:
    """Discover audit/telemetry event handlers and register them with the dispatcher.

    Scoped to known sub-packages; add new domains to :func:`_handler_packages`.
    Continues startup if discovery fails — audit is observability, not critical path.
    """
    try:
        total = 0
        for package in _handler_packages():
            registry = discover_handlers(package)
            AuditEventDispatcher.register(registry)
            total += len(registry)

        logger.info("Audit event handlers discovered", handler_count=total)
    except Exception:
        logger.exception("Failed to discover and register audit handlers - audit system degraded")
