"""Principal model for unified identity attribution.

The ``principals`` table is the supertype in a class-table-inheritance
hierarchy.  Every entity that can act as a principal (users, service
accounts, etc.) has a row here whose ``id`` is shared with the entity's
own PK.  Foreign keys on ``created_by``, ``updated_by``, and
``RoleAssignment.principal_id`` all point to ``principals.id``, giving
the database real referential integrity across principal types.

A ``before_flush`` event listener auto-creates Principal rows whenever a
registered subtype (User, ServiceAccount) is added to the session — no
special helper is needed, just use ``session.add(entity)``.

Groups are NOT principals — they use ``RoleAssignment.group_id``
(FK → groups) instead of ``principal_id``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid5

from sqlalchemy import String
from sqlmodel import Field, SQLModel

from syntara.core.constants import FieldLimits

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from syntara.core.models.user import User

_SERVICE_PRINCIPAL_NS = UUID("8001555d-5289-4875-8848-7756b26e6bc3")

KNOWN_SERVICE_CNS: tuple[str, ...] = (
    "backend.ao.svc",
    "worker.ao.svc",
    "background-worker.ao.svc",
    "temporal.ao.svc",
)


def service_principal_id(cn: str) -> UUID:
    """Deterministic UUID for a service principal identified by mTLS cert CN."""
    return uuid5(_SERVICE_PRINCIPAL_NS, cn)


def make_service_user(cn: str) -> User:
    """Build a non-persistent synthetic User for a service principal.

    Used where ``BaseService`` requires a ``User`` but the caller is an
    internal service operating outside a user request context.  The
    returned object is NOT backed by a database row — do not pass it to
    ``session.refresh()`` or access ORM relationships on it.
    """
    from syntara.core.models.user import User  # noqa: PLC0415

    return User(
        id=service_principal_id(cn),
        username=cn,
        email=f"{cn}@internal",
        first_name=cn,
        is_enabled=True,
    )


class PrincipalType(StrEnum):
    """Types that get rows in the principals table (class-table inheritance).

    Most types correspond 1:1 to a child table (USER → ``users``,
    SERVICE_ACCOUNT → ``service_accounts``).  SERVICE represents
    internal mTLS-authenticated services (backend, worker, background-worker, temporal)
    that have Principal rows but no child-table rows.

    SYSTEM is retained for backward compatibility with existing DB rows
    from before the system user was replaced by per-service principals.
    New code should use SERVICE instead.
    """

    USER = "user"
    SERVICE_ACCOUNT = "service_account"
    SERVICE = "service"
    SYSTEM = "system"
    # Not implemented yet. Possible future type:
    #   - DELETED_USER: sentinel for hard-deleted users, so created_by/updated_by
    #     FKs remain valid and the audit trail records "done by a removed user"


class Principal(SQLModel, table=True):
    """Supertype row for every entity that can act as a principal.

    Note: if a hard-delete path is ever added for users,
    the corresponding Principal row must be deleted in the same
    transaction to avoid FK violations on created_by/updated_by.
    """

    __tablename__ = "principals"

    id: UUID = Field(primary_key=True)
    principal_type: PrincipalType = Field(
        sa_type=String(FieldLimits.PRINCIPAL_TYPE_MAX_LENGTH),  # type: ignore[call-overload]
        index=True,
    )

    @classmethod
    def for_user(cls, user_id: UUID) -> Principal:
        """Create a principal row for a user."""
        return cls(id=user_id, principal_type=PrincipalType.USER)

    @classmethod
    def for_service_account(cls, sa_id: UUID) -> Principal:
        """Create a principal row for a service account."""
        return cls(id=sa_id, principal_type=PrincipalType.SERVICE_ACCOUNT)

    @classmethod
    def for_service(cls, cn: str) -> Principal:
        """Create a principal row for an internal service identified by cert CN."""
        return cls(id=service_principal_id(cn), principal_type=PrincipalType.SERVICE)


def _before_flush(session: Session, _flush_context: object, _instances: object) -> None:
    """Auto-create Principal rows for new principal subtypes before flush.

    Any model with a ``__principal_type__`` ClassVar is treated as a
    principal subtype.  Uses a Core INSERT (bypassing the ORM
    unit-of-work) so the row exists before SQLAlchemy flushes the
    subtype.  This sidesteps the flush-ordering problem where
    SQLAlchemy cannot detect the FK dependency when the PK itself is
    the FK.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: PLC0415

    existing_principal_ids = {obj.id for obj in session.new if isinstance(obj, Principal)}
    for obj in list(session.new):
        principal_type = getattr(obj, "__principal_type__", None)
        if principal_type is not None and obj.id not in existing_principal_ids:
            stmt = pg_insert(Principal.__table__).values(  # type: ignore[attr-defined]
                id=obj.id, principal_type=principal_type.value
            )
            stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
            session.execute(stmt)
            existing_principal_ids.add(obj.id)
