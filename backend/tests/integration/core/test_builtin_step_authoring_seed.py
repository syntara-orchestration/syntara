"""Both bootstrap paths preserve the built-in step-authoring assignment."""

from collections.abc import Awaitable, Callable

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.exceptions import BuiltinProtectionError
from syntara.authz.models import Policy, Role, RoleAssignment
from syntara.authz.seed import seed_authz_data, seed_groups_project_admin
from syntara.authz.services.role_assignment_service import RoleAssignmentService
from syntara.core.models import User
from syntara.core.models.group import Group


@pytest.mark.parametrize("seed", [seed_authz_data, seed_groups_project_admin])
async def test_builtin_step_authoring_seed_is_protected_and_idempotent(
    test_db_session: AsyncSession,
    test_user: User,
    seed: Callable[[AsyncSession], Awaitable[None]],
) -> None:
    """Only the global protected assignment is persisted, with a stable ID."""
    db = test_db_session
    await seed(db)
    assignment = (await db.exec(select(RoleAssignment).where(RoleAssignment.role_name == "step-author"))).one()
    assignment_id = assignment.id
    assert assignment.is_builtin
    assert assignment.project_id is None
    assert assignment.principal_id is None
    group = await db.get(Group, assignment.group_id)
    assert group is not None
    assert group.name == "authenticated"

    with pytest.raises(BuiltinProtectionError, match="Cannot revoke built-in role assignment"):
        await RoleAssignmentService(db, test_user).revoke(assignment.id)

    await seed(db)
    assignments = (await db.exec(select(RoleAssignment).where(RoleAssignment.role_name == "step-author"))).all()
    assert len(assignments) == 1
    assert assignments[0].id == assignment_id
    assert assignments[0].is_builtin
    assert (await db.exec(select(Role))).all() == []
    assert (await db.exec(select(Policy))).all() == []
