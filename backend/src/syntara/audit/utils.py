"""Utility functions for the audit package."""

from functools import lru_cache
from uuid import UUID

import structlog

from syntara.audit.models.audit_event import EventSeverity
from syntara.core.constants import FieldLimits
from syntara.core.lib.sanitization import strip_control_chars
from syntara.core.models.principal import KNOWN_SERVICE_CNS, PrincipalType, service_principal_id

logger = structlog.stdlib.get_logger(__name__)

# Ordering for EventSeverity (StrEnum does not provide natural ordering).
# Higher rank means more severe.
_SEVERITY_RANK: dict[EventSeverity, int] = {
    EventSeverity.INFO: 0,
    EventSeverity.WARNING: 1,
    EventSeverity.ERROR: 2,
    EventSeverity.CRITICAL: 3,
}


def escalate_severity(current: EventSeverity, minimum: EventSeverity) -> EventSeverity:
    """Return the more severe of ``current`` and ``minimum``.

    Used to ensure audit events emitted from exception paths carry at least
    ``minimum`` severity, without downgrading caller-declared severities that
    are already higher (e.g. ``CRITICAL`` remains ``CRITICAL`` when escalating
    to ``ERROR``).
    """
    return current if _SEVERITY_RANK[current] >= _SEVERITY_RANK[minimum] else minimum


@lru_cache(maxsize=1)
def _get_service_principal_ids() -> frozenset[UUID]:
    return frozenset(service_principal_id(cn) for cn in KNOWN_SERVICE_CNS)


def escalate_actor_type(actor_id: UUID) -> PrincipalType:
    """Classify an actor UUID as SERVICE or USER.

    Needed because some code paths construct synthetic ``User`` objects
    with a service principal UUID (via ``make_service_user``) to satisfy
    ``BaseService``.  Since the actor is a ``User`` instance, the caller
    cannot distinguish it by type alone — this function checks the UUID
    against the known service principal set.

    For HTTP requests the cert middleware already sets actor_type=SERVICE
    directly; this function covers non-HTTP paths (audit context managers,
    invocation executor fallback).

    """
    if actor_id in _get_service_principal_ids():
        logger.debug(
            "actor_type_escalated",
            actor_id=str(actor_id),
            actor_type=PrincipalType.SERVICE,
            reason="actor_id matches a known service principal",
        )
        return PrincipalType.SERVICE

    return PrincipalType.USER


def sanitize_actor_username(username: str | None) -> str | None:
    """Sanitize and cap an actor username for audit context.

    Strips ASCII control characters and truncates to ``NAME_MAX_LENGTH``
    to prevent unbounded values from reaching audit logs or PostgreSQL
    session variables.
    """
    if username is None:
        return None
    sanitized = strip_control_chars(username)
    return sanitized[: FieldLimits.NAME_MAX_LENGTH] if sanitized else None


def resolve_actor_type(
    actor_id: UUID | None = None,
    *,
    principal_type: PrincipalType | None = None,
) -> PrincipalType:
    """Determine the correct PrincipalType for audit attribution.

    Central resolver used by audit event handlers to avoid hard-coding
    ``PrincipalType.USER``.  Dispatch sites set *principal_type* from
    whatever context they have (e.g. the instance-level
    ``__principal_type__`` on SA virtual principals, or a mapping from
    ``TokenPayload.token_type``).

    Resolution order:
    1. Explicit *principal_type* when set by the dispatch site.
    2. ``escalate_actor_type(actor_id)`` — checks for known service principals.
    3. ``PrincipalType.USER`` as the default.
    """
    if principal_type is not None:
        return principal_type
    if actor_id is not None:
        return escalate_actor_type(actor_id)
    return PrincipalType.USER
