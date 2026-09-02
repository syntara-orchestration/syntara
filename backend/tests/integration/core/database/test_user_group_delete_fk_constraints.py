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
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import insert, text
from sqlalchemy import select as sa_select
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.approvals.models import ApprovalRequest, ApprovalRequestStatus
from syntara.approvals.models.approval_approvers import ApprovalApproverGroup, ApprovalApproverUser
from syntara.auth.session.models import RefreshSession
from syntara.core.models import User
from syntara.core.models.group import user_groups, user_idp_groups
from syntara.core.models.user_identity import UserIdentity
from syntara.identity_providers.models.idp_group_mapping import IdpGroupMappingEntry
from syntara.users.services.group_service import GroupsService
from syntara.users.services.user_service import UsersService
from tests.integration.helpers.identity_provider import IdentityProviderCreate

# (table, column, constraint) -> expected ON DELETE action ("c"=CASCADE, "n"=SET NULL, "a"=NO ACTION)
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
    ("idp_group_mapping_entries", "idp_group_mapping_entries_mapped_group_id_fkey", "c"),
    ("token_usage_records", "token_usage_records_user_id_fkey", "n"),
    ("groups", "groups_created_by_fkey", "n"),
]


async def _confdeltype(session: AsyncSession, table: str, constraint: str) -> str | None:
    result = await session.execute(
        text(
            "SELECT confdeltype FROM pg_constraint "
            "WHERE conrelid = :table_name::regclass AND conname = :constraint_name"
        ).bindparams(table_name=table, constraint_name=constraint)
    )
    return result.scalar_one_or_none()


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
    test_db_session.expire_all()

    assert (await test_db_session.exec(select(UserIdentity).where(UserIdentity.id == identity_id))).first() is None
    assert (await test_db_session.exec(select(RefreshSession).where(RefreshSession.jti == session_jti))).first() is None
    approver_result = await test_db_session.exec(
        select(ApprovalApproverUser).where(
            ApprovalApproverUser.approval_id == approval_id, ApprovalApproverUser.user_id == victim_id
        )
    )
    assert approver_result.first() is None
    idp_group_membership = await test_db_session.execute(
        sa_select(user_idp_groups).where(
            user_idp_groups.c.user_id == victim_id,
            user_idp_groups.c.identity_provider_id == idp_id,
            user_idp_groups.c.group_id == idp_group_id,
        )
    )
    assert idp_group_membership.first() is None

    # The approval request itself is untouched — only the approver link is user-scoped.
    surviving_approval = (
        await test_db_session.exec(select(ApprovalRequest).where(ApprovalRequest.id == approval_id))
    ).first()
    assert surviving_approval is not None


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

    await groups_service.delete_group(group_id)
    test_db_session.expire_all()

    membership = await test_db_session.execute(
        sa_select(user_groups).where(user_groups.c.user_id == test_user.id, user_groups.c.group_id == group_id)
    )
    assert membership.first() is None

    idp_membership = await test_db_session.execute(
        sa_select(user_idp_groups).where(
            user_idp_groups.c.user_id == test_user.id,
            user_idp_groups.c.identity_provider_id == idp_id,
            user_idp_groups.c.group_id == group_id,
        )
    )
    assert idp_membership.first() is None

    assert (
        await test_db_session.exec(select(IdpGroupMappingEntry).where(IdpGroupMappingEntry.id == mapping_id))
    ).first() is None

    approver_group_result = await test_db_session.exec(
        select(ApprovalApproverGroup).where(
            ApprovalApproverGroup.approval_id == approval_id, ApprovalApproverGroup.group_id == group_id
        )
    )
    assert approver_group_result.first() is None

    # The user and the approval request itself must survive a group delete.
    surviving_user = (await test_db_session.exec(select(User).where(User.id == test_user.id))).first()
    assert surviving_user is not None
    surviving_approval = (
        await test_db_session.exec(select(ApprovalRequest).where(ApprovalRequest.id == approval_id))
    ).first()
    assert surviving_approval is not None
