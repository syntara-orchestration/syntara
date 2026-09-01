"""Shared helpers for resolving user UUID fields to UserReference objects."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from syntara.core.models.principal import (
    KNOWN_SERVICE_CNS,
    Principal,
    service_principal_id,
)
from syntara.core.models.user import User
from syntara.core.models.user_reference import UserReference

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlmodel.ext.asyncio.session import AsyncSession

logger = logging.getLogger(__name__)

# Service principals (mTLS-authenticated internal services) get a ``principals``
# row but no child-table row, so their display name is derived from the cert CN.
_SERVICE_CN_BY_PRINCIPAL_ID: dict[UUID, str] = {service_principal_id(cn): cn for cn in KNOWN_SERVICE_CNS}


def _user_id_from_value(val: object) -> str | UUID | None:
    """Extract a user UUID from a raw field value (UUID, string, or UserReference)."""
    if val is None:
        return None
    if isinstance(val, UserReference):
        return val.id
    if isinstance(val, UUID | str):
        return val
    return None


def _display_name(principal_id: UUID, username: str | None, service_account_name: str | None) -> str:
    """Pick the best available display name for a principal.

    ``created_by``/``updated_by`` reference ``principals.id``, which may be a
    user, a service account, or an internal service. Falling back to the raw id
    keeps attribution visible rather than dropping it.
    """
    return username or service_account_name or _SERVICE_CN_BY_PRINCIPAL_ID.get(principal_id) or str(principal_id)


async def lookup_users(
    session: AsyncSession,
    objects: Sequence[Any],
    field_names: Sequence[str] = ("created_by", "updated_by"),
) -> dict[str | UUID, tuple[UUID, str]] | None:
    """Collect principal UUIDs from *objects* and batch-resolve them.

    Resolves every principal type in a single query: users by username,
    service accounts by name, and internal services by cert CN.

    Returns a mapping {uuid: (uuid, name)} on success, or
    None when the lookup query fails (caller decides fallback).
    """
    principal_ids: set[str | UUID] = set()
    for obj in objects:
        for field in field_names:
            uid = _user_id_from_value(getattr(obj, field, None))
            if uid:
                principal_ids.add(uid)
    if not principal_ids:
        return {}
    # Imported lazily: a module-level import forces SQLModel mapper
    # configuration before every model is registered, which breaks
    # unrelated relationships (e.g. Credential.credential_type).
    from syntara.service_accounts.models.service_account import ServiceAccount  # noqa: PLC0415

    try:
        stmt = (
            select(Principal.id, User.username, ServiceAccount.name)
            .select_from(Principal)
            .outerjoin(User, User.id == Principal.id)  # type: ignore[arg-type]
            .outerjoin(ServiceAccount, ServiceAccount.id == Principal.id)  # type: ignore[arg-type]
            .where(Principal.id.in_(principal_ids))  # type: ignore[attr-defined]
        )
        result = await session.exec(stmt)
        return {row[0]: (row[0], _display_name(row[0], row[1], row[2])) for row in result}
    except (SQLAlchemyError, OSError):
        logger.warning("Failed to resolve usernames", exc_info=True)
        return None


async def resolve_user_references(
    session: AsyncSession,
    objects: Sequence[Any],
    field_names: Sequence[str] = ("created_by", "updated_by"),
) -> None:
    """Resolve principal UUID fields to UserReference objects in-place.

    Ids with no ``principals`` row (e.g. hard-deleted users) produce None
    rather than an empty object, matching credential API behavior.

    Lookup failures (SQLAlchemyError/OSError) also set fields to None
    instead of raising. Username enrichment must not fail the parent
    list/detail request; this matches CredentialService. The OpenAPI
    contract is UserReference | null, so unresolved values cannot be
    left as raw UUIDs.
    """
    user_map = await lookup_users(session, objects, field_names)
    if user_map is None:
        # Intentional: degrade to null rather than fail the request.
        for obj in objects:
            for field in field_names:
                setattr(obj, field, None)
        return
    for obj in objects:
        for field in field_names:
            uid = _user_id_from_value(getattr(obj, field, None))
            if uid is not None and uid in user_map:
                resolved_id, name = user_map[uid]
                setattr(obj, field, UserReference(id=resolved_id, name=name))
            elif uid is not None:
                setattr(obj, field, None)


class UserReferenceMixin:
    """Mixin that resolves user UUID fields to UserReference objects."""

    session: AsyncSession

    async def _lookup_users(
        self,
        objects: Sequence[Any],
        field_names: Sequence[str] = ("created_by", "updated_by"),
    ) -> dict[str | UUID, tuple[UUID, str]] | None:
        """Collect user UUIDs from *objects* and batch-resolve them."""
        return await lookup_users(self.session, objects, field_names)

    async def resolve_user_references(
        self,
        objects: Sequence[Any],
        field_names: Sequence[str] = ("created_by", "updated_by"),
    ) -> None:
        """Resolve user UUID fields to UserReference objects in-place."""
        await resolve_user_references(self.session, objects, field_names)
