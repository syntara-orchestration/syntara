"""Shared helpers for resolving user UUID fields to UserReference objects."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from syntara.core.models.user import User
from syntara.core.models.user_reference import UserReference

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlmodel.ext.asyncio.session import AsyncSession

logger = logging.getLogger(__name__)


def _user_id_from_value(val: object) -> str | UUID | None:
    """Extract a user UUID from a raw field value (UUID, string, or UserReference)."""
    if val is None:
        return None
    if isinstance(val, UserReference):
        return val.id
    if isinstance(val, UUID | str):
        return val
    return None


async def lookup_users(
    session: AsyncSession,
    objects: Sequence[Any],
    field_names: Sequence[str] = ("created_by", "updated_by"),
) -> dict[str | UUID, tuple[UUID, str]] | None:
    """Collect user UUIDs from *objects* and batch-resolve them.

    Returns a mapping {uuid: (uuid, username)} on success, or
    None when the lookup query fails (caller decides fallback).
    """
    user_ids: set[str | UUID] = set()
    for obj in objects:
        for field in field_names:
            uid = _user_id_from_value(getattr(obj, field, None))
            if uid:
                user_ids.add(uid)
    if not user_ids:
        return {}
    try:
        stmt = select(User.id, User.username).where(User.id.in_(user_ids))  # type: ignore[attr-defined]
        result = await session.exec(stmt)
        return {row[0]: (row[0], row[1]) for row in result}
    except (SQLAlchemyError, OSError):
        logger.warning("Failed to resolve usernames", exc_info=True)
        return None


async def resolve_user_references(
    session: AsyncSession,
    objects: Sequence[Any],
    field_names: Sequence[str] = ("created_by", "updated_by"),
) -> None:
    """Resolve user UUID fields to UserReference objects in-place.

    Unresolvable UUIDs (e.g. deleted users) produce None rather than
    an empty object, matching credential API behavior.

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
                resolved_id, username = user_map[uid]
                setattr(obj, field, UserReference(id=resolved_id, name=username))
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
