"""Single implementation of "resolve a principal id to a :class:`UserReference`".

Response schemas declare *which* of their fields hold a user reference via
:class:`~syntara.core.models.user_reference.UserReferenceFieldsMixin`; this module
turns those declarations into values. Nothing else should query principal tables
to enrich an audit field.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from syntara.core.models.principal import (
    KNOWN_SERVICE_CNS,
    Principal,
    service_principal_id,
)
from syntara.core.models.user import User, user_display_name
from syntara.core.models.user_reference import DEFAULT_USER_REFERENCE_FIELDS, UserReference

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from sqlmodel.ext.asyncio.session import AsyncSession

logger = structlog.stdlib.get_logger(__name__)

# Service principals (mTLS-authenticated internal services) get a ``principals``
# row but no child-table row, so their display name is derived from the cert CN.
_SERVICE_CN_BY_PRINCIPAL_ID: dict[UUID, str] = {service_principal_id(cn): cn for cn in KNOWN_SERVICE_CNS}


def user_reference_fields(obj: object) -> tuple[str, ...]:
    """Return the fields of *obj* that carry a user reference.

    Read from the schema's ``USER_REFERENCE_FIELDS`` declaration, so callers never
    restate field names. Falls back to the conventional audit pair for plain
    objects that predate the declaration.
    """
    return tuple(getattr(type(obj), "USER_REFERENCE_FIELDS", DEFAULT_USER_REFERENCE_FIELDS))


def _principal_id_from_value(val: object) -> UUID | None:
    """Extract a principal UUID from a raw field value (UUID, string, or UserReference)."""
    if val is None:
        return None
    if isinstance(val, UserReference):
        return val.id
    if isinstance(val, UUID):
        return val
    if isinstance(val, str):
        # The Read models still permit a str id; the lookup map is keyed by
        # UUID, so an unnormalised str would never match and would be
        # silently nulled out.
        try:
            return UUID(val)
        except ValueError:
            return None
    return None


def _display_name(
    principal_id: UUID,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    service_account_name: str | None,
) -> str:
    """Pick the best available display name for a principal.

    ``created_by``/``updated_by`` reference ``principals.id``, which may be a
    user, a service account, or an internal service. For users this mirrors
    :attr:`User.display_name` (full name, else username) so every API surface
    shows the same name for the same principal. Falling back to the raw id
    keeps attribution visible rather than dropping it.
    """
    if username is not None:
        return user_display_name(username, first_name, last_name)
    return service_account_name or _SERVICE_CN_BY_PRINCIPAL_ID.get(principal_id) or str(principal_id)


class UserReferenceResolver:
    """Resolves every declared user-reference field on a set of response objects.

    One batched query per call, regardless of how many objects or fields are
    involved. Enrichment must never fail the parent request, so a lookup failure
    degrades the affected fields to ``None`` rather than raising — the OpenAPI
    contract is ``UserReference | null``, so a raw id cannot be left in place.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Bind the resolver to the session its lookups run on."""
        self.session = session

    async def resolve(self, objects: Sequence[Any]) -> None:
        """Resolve declared user-reference fields on *objects*, in place."""
        if not objects:
            return
        principal_map = await self.lookup(objects)
        if principal_map is None:
            # Intentional: degrade to null rather than fail the request.
            for obj in objects:
                for field in user_reference_fields(obj):
                    if getattr(obj, field, None) is not None:
                        setattr(obj, field, None)
            return
        for obj in objects:
            for field in user_reference_fields(obj):
                pid = _principal_id_from_value(getattr(obj, field, None))
                if pid is None:
                    continue
                name = principal_map.get(pid)
                setattr(obj, field, UserReference(id=pid, name=name) if name is not None else None)

    async def lookup(self, objects: Iterable[Any]) -> dict[UUID, str] | None:
        """Batch-resolve every principal id referenced by *objects*.

        Resolves every principal type in a single query: users by name,
        service accounts by name, and internal services by cert CN.

        Returns ``{principal_id: name}``, or ``None`` when the query fails.
        """
        principal_ids: set[UUID] = set()
        for obj in objects:
            for field in user_reference_fields(obj):
                pid = _principal_id_from_value(getattr(obj, field, None))
                if pid:
                    principal_ids.add(pid)
        if not principal_ids:
            return {}
        # Imported lazily: a module-level import forces SQLModel mapper
        # configuration before every model is registered, which breaks
        # unrelated relationships (e.g. Credential.credential_type).
        from syntara.service_accounts.models.service_account import ServiceAccount  # noqa: PLC0415

        try:
            # sqlmodel/sqlalchemy only type select() overloads up to 4 entities;
            # 5 columns is valid at runtime but has no matching overload.
            stmt = (
                select(  # type: ignore[call-overload]
                    Principal.id,
                    User.username,
                    User.first_name,
                    User.last_name,
                    ServiceAccount.name,
                )
                .select_from(Principal)
                .outerjoin(User, User.id == Principal.id)
                .outerjoin(ServiceAccount, ServiceAccount.id == Principal.id)
                .where(Principal.id.in_(principal_ids))  # type: ignore[attr-defined]
            )
            result = await self.session.exec(stmt)
        except (SQLAlchemyError, OSError):
            logger.warning(
                "Failed to resolve user references",
                principal_count=len(principal_ids),
                exc_info=True,
            )
            return None
        return {row[0]: _display_name(row[0], row[1], row[2], row[3], row[4]) for row in result}


class UserReferenceResolverMixin:
    """Service mixin granting access to the shared :class:`UserReferenceResolver`.

    Services that return schemas with user-reference fields call
    ``resolve_user_references()`` from their read-model conversion, so every
    endpoint backed by that service is enriched without wiring it per route.
    """

    session: AsyncSession

    async def resolve_user_references(self, objects: Sequence[Any]) -> None:
        """Resolve declared user-reference fields on *objects*, in place."""
        await UserReferenceResolver(self.session).resolve(objects)
