"""Integration tests locking FK ondelete rules for user/group hard delete.

These read ``pg_constraint.confdeltype`` on the live, migrated schema —
the same query the migration's ``_assert_fk_not_cascade`` guard uses —
rather than SQLAlchemy model metadata. A hand-written migration that sets
a different ondelete than the model declares would pass a metadata-only
test; it fails here, because this asserts what the migration actually
built in the database.

Also covers the group-side cascades (user_groups.group_id,
user_idp_groups.group_id, idp_group_mapping_entries.mapped_group_id,
approval_approver_groups.group_id) and behavioral deletes for every
user-scoped table, including the ones with no other test coverage:
UserIdentity, RefreshSession, ApprovalApproverUser, user_idp_groups.

Row-existence assertions use plain ``COUNT(*)`` SQL rather than ORM
``select(Model)`` so they can't be tripped up by lazy-loaded relationships
on the involved models (e.g. ``ApprovalRequest.approver_group_records``),
which would raise ``MissingGreenlet`` if touched outside an awaited context.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import insert, text
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.approvals.models import ApprovalRequest, ApprovalRequestStatus
from syntara.approvals.models.approval_approvers import ApprovalApproverGroup, ApprovalApproverUser
from syntara.auth.session.models import RefreshSession
from syntara.core.models import User
from syntara.core.models.group import Group, user_groups, user_idp_groups
from syntara.core.models.user_identity import UserIdentity
from syntara.identity_providers.models.idp_group_mapping import IdpGroupMappingEntry
from syntara.users.services.group_service import GroupsService
from syntara.users.services.user_service import UsersService
from tests.integration.helpers.identity_provider import IdentityProviderCreate

# (table, constraint, expected confdeltype: "c"=CASCADE, "n"=SET NULL, "a"=NO ACTION)
_EXPECTED_CONFDELTYPE: list[tuple[str, str, str]] = [
    ("user_groups", "user_groups_user_id_fkey", "c"),
    ("user_groups", "user_groups_group_id_fkey", "c"),
    ("user_idp_groups", "user_idp_groups_user_id_fkey", "c"),
    ("user_idp_groups", "user_idp_groups_group_id_fkey", "c"),
    ("user_idp_groups", "user_idp_groups_identity_provider_id_fkey", "c"),
    ("user_identities", "user_identities_user_id_fkey", "c"),
    ("refresh_sessions", "refresh_sessions_user_id_fkey", "c"),
    ("user_token_configs", "user_token_configs_user_id_fkey", "c"),
    ("approval_approver_users", "approval_approver_users_user_id_fkey", "c"),
    ("approval_approver_groups", "approval_approver_groups_group_id_fkey", "c"),
    # Column was renamed nexus_group_id -> mapped_group_id in 4ca3cbf8652a, but Postgres
    # doesn't rename constraints on RENAME COLUMN and no migration issued RENAME CONSTRAINT,
    # so the FK is still named after the old column.
    ("idp_group_mapping_entries", "idp_group_mapping_entries_nexus_group_id_fkey", "c"),
    ("token_usage_records", "token_usage_records_user_id_fkey", "n"),
    ("groups", "groups_created_by_fkey", "n"),
]


async def _confdeltype(session: AsyncSession, table: str, constraint: str) -> str | None:
    result = await session.execute(
        text(
            "SELECT confdeltype::text FROM pg_constraint "
            "WHERE conrelid = CAST(:table_name AS regclass) AND conname = :constraint_name"
        ),
        {"table_name": table, "constraint_name": constraint},
    )
    raw_result = result.scalar_one_or_none()
    if raw_result is None:
        return None
    return raw_result if isinstance(raw_result, str) else raw_result.decode()


async def _count(session: AsyncSession, table: str, where_sql: str, **params: object) -> int:
    """Return a row count for ``table`` using a plain SQL WHERE clause.

    Deliberately bypasses the ORM so assertions can never trip a lazy-load
    (MissingGreenlet) on models with relationships, such as ApprovalRequest.
    """
    result = await session.execute(text(f"SELECT COUNT(*) FROM {table} WHERE {where_sql}"), params)  # noqa: S608
    return int(result.scalar_one())


async def _add_test_user_to_admins(session: AsyncSession, user_id: UUID) -> None:
    """Ensure the actor is an enabled admin so delete_user's admin-count guard passes.

    The "admins" group is not guaranteed to be seeded in the integration test
    template (only "authenticated" is auto-created), so this gets-or-creates it,
    mirroring the pattern in tests/integration/users/services/test_user_service.py.
    """
    admins_group_id = (await session.execute(text("SELECT id FROM groups WHERE name = 'admins'"))).scalar_one_or_none()
    if admins_group_id is None:
        admins_group_id = uuid4()
        session.add(Group(id=admins_group_id, name="admins", is_builtin=True, labels={}))
        await session.flush()

    already_member = await _count(
        session,
        "user_groups",
        "user_id = :user_id AND group_id = :group_id",
        user_id=user_id,
        group_id=admins_group_id,
    )
    if not already_member:
        await session.exec(insert(user_groups).values(user_id=user_id, group_id=admins_group_id))
    await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(("table", "constraint", "expected"), _EXPECTED_CONFDELTYPE)
async def test_fk_ondelete_matches_migrated_schema(
    test_db_session: AsyncSession, table: str, constraint: str, expected: str
) -> None:
    """Assert against pg_constraint on the actual migrated database.

    This is the guard the migration's runtime check also uses. It closes the
    gap where a hand-written CUSTOM migration diverges from what the
    SQLModel declarations say, since the migration is applied SQL, not
    Python metadata.
    """
    confdeltype = await _confdeltype(test_db_session, table, constraint)
    assert confdeltype == expected, f"{table}.{constraint} is confdeltype={confdeltype!r}, expected {expected!r}"


@pytest.mark.asyncio
async def test_delete_user_cascades_identity_session_and_approver_rows(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """UserIdentity, RefreshSession, ApprovalApproverUser, and user_idp_groups have no other coverage."""
    await _add_test_user_to_admins(test_db_session, test_user.id)

    idp_factory = IdentityProviderCreate(test_db_session, test_user)
    idp = await idp_factory.create()

    service = UsersService(test_db_session, test_user)
    groups_service = GroupsService(test_db_session, test_user)

    victim = await service.create_user(
        username="fk-coverage-victim",
        email="fk-coverage-victim@example.com",
        first_name="Fk",
        last_name="Victim",
        password="Sup3rSecret!23",  # noqa: S106
    )

    idp_group = await groups_service.create_group(name="idp-synced-group", description=None)

    identity = UserIdentity(
        user_id=victim.id,
        identity_provider_id=idp.id,
        issuer="https://idp.example.com",
        subject=f"sub-{victim.id.hex[:8]}",
    )
    test_db_session.add(identity)

    session_row = RefreshSession(
        jti=f"jti-{uuid4().hex[:12]}",
        user_id=victim.id,
        issued_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    test_db_session.add(session_row)

    approval = ApprovalRequest(
        project_id=test_project_id,
        execution_id=uuid4(),
        name="fk-coverage-approval",
        approval_node_id="node-1",
        status=ApprovalRequestStatus.PENDING,
        next_step_approved={"id": "next", "name": "Next", "type": "llm"},
    )
    test_db_session.add(approval)
    await test_db_session.flush()

    approver_row = ApprovalApproverUser(approval_id=approval.id, user_id=victim.id)
    test_db_session.add(approver_row)

    await test_db_session.exec(
        insert(user_idp_groups).values(user_id=victim.id, identity_provider_id=idp.id, group_id=idp_group.id)
    )
    await test_db_session.commit()

    identity_id = identity.id
    approval_id = approval.id
    session_jti = session_row.jti
    victim_id = victim.id
    idp_id = idp.id
    idp_group_id = idp_group.id

    await service.delete_user(victim_id)

    assert await _count(test_db_session, "user_identities", "id = :id", id=identity_id) == 0
    assert await _count(test_db_session, "refresh_sessions", "jti = :jti", jti=session_jti) == 0
    assert (
        await _count(
            test_db_session,
            "approval_approver_users",
            "approval_id = :approval_id AND user_id = :user_id",
            approval_id=approval_id,
            user_id=victim_id,
        )
        == 0
    )
    assert (
        await _count(
            test_db_session,
            "user_idp_groups",
            "user_id = :user_id AND identity_provider_id = :idp_id AND group_id = :group_id",
            user_id=victim_id,
            idp_id=idp_id,
            group_id=idp_group_id,
        )
        == 0
    )

    # The approval request itself is untouched — only the approver link is user-scoped.
    assert await _count(test_db_session, "approval_requests", "id = :id", id=approval_id) == 1


@pytest.mark.asyncio
async def test_delete_group_cascades_group_scoped_rows_and_preserves_users_and_approval(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """user_groups, user_idp_groups, idp_group_mapping_entries, approval_approver_groups all clean up."""
    idp_factory = IdentityProviderCreate(test_db_session, test_user)
    idp = await idp_factory.create()

    groups_service = GroupsService(test_db_session, test_user)
    group = await groups_service.create_group(name="cascade-check-group", description=None)

    await groups_service.add_member(group.id, test_user.id)

    await test_db_session.exec(
        insert(user_idp_groups).values(user_id=test_user.id, identity_provider_id=idp.id, group_id=group.id)
    )

    mapping = IdpGroupMappingEntry(identity_provider_id=idp.id, idp_group_value="engineering", mapped_group_id=group.id)
    test_db_session.add(mapping)

    approval = ApprovalRequest(
        project_id=test_project_id,
        execution_id=uuid4(),
        name="group-cascade-approval",
        approval_node_id="node-1",
        status=ApprovalRequestStatus.PENDING,
        next_step_approved={"id": "next", "name": "Next", "type": "llm"},
    )
    test_db_session.add(approval)
    await test_db_session.flush()

    approver_group_row = ApprovalApproverGroup(approval_id=approval.id, group_id=group.id)
    test_db_session.add(approver_group_row)
    await test_db_session.commit()

    group_id = group.id
    mapping_id = mapping.id
    approval_id = approval.id
    idp_id = idp.id
    user_id = test_user.id

    await groups_service.delete_group(group_id)

    assert (
        await _count(
            test_db_session,
            "user_groups",
            "user_id = :user_id AND group_id = :group_id",
            user_id=user_id,
            group_id=group_id,
        )
        == 0
    )
    assert (
        await _count(
            test_db_session,
            "user_idp_groups",
            "user_id = :user_id AND identity_provider_id = :idp_id AND group_id = :group_id",
            user_id=user_id,
            idp_id=idp_id,
            group_id=group_id,
        )
        == 0
    )
    assert await _count(test_db_session, "idp_group_mapping_entries", "id = :id", id=mapping_id) == 0
    assert (
        await _count(
            test_db_session,
            "approval_approver_groups",
            "approval_id = :approval_id AND group_id = :group_id",
            approval_id=approval_id,
            group_id=group_id,
        )
        == 0
    )

    # The user and the approval request itself must survive a group delete.
    assert await _count(test_db_session, "users", "id = :id", id=user_id) == 1
    assert await _count(test_db_session, "approval_requests", "id = :id", id=approval_id) == 1
