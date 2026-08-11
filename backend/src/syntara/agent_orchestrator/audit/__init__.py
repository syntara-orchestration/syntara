"""Audit events and handlers for agent_orchestrator domain.

This package contains domain-specific audit events and handlers for tracking
agent execution, LLM interactions, context integration, and invocation lifecycle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID

    from syntara.audit.emitter import AuditActorContext
    from syntara.core.models.principal import PrincipalType


def extract_actor_fields(
    actor_context: AuditActorContext | None,
) -> tuple[UUID | None, str | None, PrincipalType | None]:
    """Extract actor identity fields from an optional AuditActorContext.

    Returns:
        Tuple of (actor_id, actor_username, actor_type), all ``None``
        when *actor_context* is ``None``.

    """
    if actor_context is None:
        return None, None, None
    return actor_context.actor_id, actor_context.actor_username, actor_context.actor_type
