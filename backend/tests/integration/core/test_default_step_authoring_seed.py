"""Editable step-authoring defaults survive subsequent bootstrap runs."""

import asyncio
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz import resource_actions
from syntara.authz.evaluator import evaluate_policy_input
from syntara.authz.exceptions import PolicyNameConflictError, RoleNameConflictError
from syntara.authz.models import Policy, Role, RoleAssignment
from syntara.authz.resolver import resolve_effective_policies
from syntara.authz.schemas import PolicyStatementSchema
from syntara.authz.seed import (
    DEFAULT_STEP_ALLOW_SEED_KEY,
    _seed_default_step_authoring_once,
    seed_authz_data,
    seed_groups_project_admin,
)
from syntara.authz.services.policy_service import PolicyService
from syntara.authz.services.role_assignment_service import RoleAssignmentService
from syntara.authz.services.role_service import RoleService
from syntara.core.models import User
from syntara.core.models.group import Group
from syntara.core.models.seed_marker import SeedMarker
from syntara.workflows.node_kinds import NODE_KINDS


@pytest.fixture(autouse=True)
def _step_action_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Service tests bypass the app lifespan that normally builds this registry."""
    monkeypatch.setattr(resource_actions, "_registry", {"step_type": ["write"]})
    monkeypatch.setattr(resource_actions, "_all_pairs", frozenset({"step_type:write"}))
    monkeypatch.setattr(resource_actions, "_project_eligible", frozenset({"step_type"}))


async def _defaults(db: AsyncSession) -> tuple[Policy, Role, RoleAssignment]:
    policy = (await db.exec(select(Policy).where(Policy.name == "step_type:write:any"))).one()
    role = (await db.exec(select(Role).where(Role.name == "step-author"))).one()
    assignment = (await db.exec(select(RoleAssignment).where(RoleAssignment.role_name == role.name))).one()
    return policy, role, assignment


async def _allows(db: AsyncSession, user: User, kind: str, project: str = "payments") -> bool:
    decision = evaluate_policy_input(
        {
            "user": {"id": str(user.id), "labels": {}},
            "groups": [],
            "action": "write",
            "resource": {"type": "step_type", "project": project, "labels": {"kind": kind}},
            "effective_policies": await resolve_effective_policies(db, user.id),
        }
    )
    return bool(decision["allow"])


@pytest.mark.parametrize("seed", [seed_authz_data, seed_groups_project_admin])
async def test_default_seed_is_custom_and_idempotent(
    test_db_session: AsyncSession,
    test_user: User,
    seed: Callable[[AsyncSession], Awaitable[None]],
) -> None:
    """Both entrypoints produce one editable baseline covering future kinds too."""
    db = test_db_session
    await seed(db)
    policy, role, assignment = await _defaults(db)
    assert not policy.is_builtin
    assert not role.is_builtin
    assert not assignment.is_builtin
    assert policy.project_id is None
    assert policy.scope == "any"
    assert policy.statements == [{"effect": "allow", "actions": ["step_type:write"], "scope": "any"}]
    PolicyStatementSchema.model_validate(policy.statements[0])
    assert role.project_id is None
    assert role.scope == "system"
    assert role.policy_names == [policy.name]
    assert assignment.project_id is None
    assert assignment.principal_id is None
    group = await db.get(Group, assignment.group_id)
    assert group is not None
    assert group.name == "authenticated"
    marker = await db.get(SeedMarker, DEFAULT_STEP_ALLOW_SEED_KEY)
    assert marker is not None
    assert marker.seeded_at is not None

    ids = (policy.id, role.id, assignment.id)
    await seed(db)
    assert tuple(record.id for record in await _defaults(db)) == ids
    assert len((await db.exec(select(SeedMarker))).all()) == 1
    for kind in (*sorted(NODE_KINDS), "future_step_kind"):
        for project in ("payments", "other"):
            assert await _allows(db, test_user, kind, project)


@pytest.mark.parametrize("change", ["edit-policy", "rename-policy", "rename-role"])
async def test_default_edits_survive_reseeding(test_db_session: AsyncSession, test_user: User, change: str) -> None:
    """Normal CRUD edits and name-reference updates remain authoritative."""
    db = test_db_session
    await seed_authz_data(db)
    policy, role, assignment = await _defaults(db)
    if change == "edit-policy":
        await PolicyService(db, test_user).update_policy(
            policy.id,
            statements=[
                {
                    "effect": "allow",
                    "actions": ["step_type:write"],
                    "scope": "any",
                    "conditions": {"resource_labels": {"kind": "script"}},
                }
            ],
        )
    elif change == "rename-policy":
        await PolicyService(db, test_user).update_policy(policy.id, name="chosen-step-policy")
    else:
        await RoleService(db, test_user).update_role(role.id, name="chosen-step-role")

    expected = (policy.name, policy.statements, role.name, role.policy_names, assignment.role_name)
    for seed in (seed_groups_project_admin, seed_authz_data):
        await seed(db)
    await db.refresh(policy)
    await db.refresh(role)
    await db.refresh(assignment)
    assert (policy.name, policy.statements, role.name, role.policy_names, assignment.role_name) == expected
    assert len((await db.exec(select(Policy))).all()) == 1
    assert len((await db.exec(select(Role))).all()) == 1
    assert await _allows(db, test_user, "script")
    assert await _allows(db, test_user, "http_request") is (change != "edit-policy")


@pytest.mark.parametrize("change", ["detach-policy", "revoke-assignment", "delete-policy", "delete-role"])
async def test_default_removal_survives_reseeding(test_db_session: AsyncSession, test_user: User, change: str) -> None:
    """Removing any link denies steps, and selected-kind grants still work."""
    db = test_db_session
    await seed_authz_data(db)
    policy, role, assignment = await _defaults(db)
    policy_id, role_id, assignment_id = policy.id, role.id, assignment.id
    assert await _allows(db, test_user, "script")
    if change == "detach-policy":
        await RoleService(db, test_user).update_role(role.id, policies=[])
    elif change == "revoke-assignment":
        await RoleAssignmentService(db, test_user).revoke(assignment.id)
    elif change == "delete-policy":
        await PolicyService(db, test_user).delete_policy(policy.id)
    else:
        await RoleService(db, test_user).delete_role(role.id)

    for seed in (seed_groups_project_admin, seed_authz_data):
        await seed(db)
    assert not await _allows(db, test_user, "script")
    assert not await _allows(db, test_user, "http_request")
    if change == "delete-policy":
        assert await db.get(Policy, policy_id) is None
    if change == "delete-role":
        assert await db.get(Role, role_id) is None
    if change in ("delete-role", "revoke-assignment"):
        assert await db.get(RoleAssignment, assignment_id) is None
    if change in ("detach-policy", "delete-policy"):
        await db.refresh(role)
        assert role.policy_names == []

    selected = await PolicyService(db, test_user).create_policy(
        "script-only",
        [
            {
                "effect": "allow",
                "actions": ["step_type:write"],
                "scope": "any",
                "conditions": {"resource_labels": {"kind": "script"}},
            }
        ],
    )
    chosen_role = await RoleService(db, test_user).create_role("script-only", policies=[selected.name])
    db.add(RoleAssignment(principal_id=test_user.id, role_name=chosen_role.name))
    await db.commit()
    assert await _allows(db, test_user, "script")
    assert not await _allows(db, test_user, "http_request")


@pytest.mark.parametrize("matching_records", [False, True])
async def test_converts_legacy_assignment_and_reuses_matching_records(
    test_db_session: AsyncSession, *, matching_records: bool
) -> None:
    """The former built-in assignment becomes editable without changing its ID."""
    db = test_db_session
    await seed_authz_data(db)
    policy, role, assignment = await _defaults(db)
    original_ids = (policy.id, role.id, assignment.id)
    if not matching_records:
        await db.delete(policy)
        await db.delete(role)
    assignment.is_builtin = True
    marker = await db.get(SeedMarker, DEFAULT_STEP_ALLOW_SEED_KEY)
    assert marker is not None
    await db.delete(marker)
    await db.commit()
    await seed_groups_project_admin(db)
    records = await _defaults(db)
    assert records[2].id == original_ids[2]
    if matching_records:
        assert tuple(record.id for record in records) == original_ids
    await db.refresh(assignment)
    assert not assignment.is_builtin


@pytest.mark.parametrize("conflict", ["policy", "role"])
async def test_conflicting_names_roll_back_marker_and_partial_seed(
    test_db_session: AsyncSession, conflict: str
) -> None:
    """A conflict leaves existing data intact and the seed eligible for retry."""
    db = test_db_session
    group = (await db.exec(select(Group).where(Group.name == "authenticated"))).one()
    record: Policy | Role
    error: type[PolicyNameConflictError | RoleNameConflictError]
    if conflict == "policy":
        record = Policy(name="step_type:write:any", statements=[])
        error = PolicyNameConflictError
    else:
        record = Role(name="step-author", policy_names=[])
        error = RoleNameConflictError
    db.add(record)
    await db.commit()
    with pytest.raises(error, match="already in use"):
        await _seed_default_step_authoring_once(db, group)
    await db.commit()
    assert await db.get(SeedMarker, DEFAULT_STEP_ALLOW_SEED_KEY) is None
    assert (await db.exec(select(RoleAssignment))).all() == []
    assert len((await db.exec(select(Policy))).all()) == (1 if conflict == "policy" else 0)
    await db.refresh(record)
    assert not record.is_builtin
    await db.delete(record)
    await db.commit()
    await _seed_default_step_authoring_once(db, group)
    await db.commit()
    await _defaults(db)


async def test_concurrent_default_seeds_converge(
    test_db_session: AsyncSession, test_db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Only one transaction creates the defaults when seeders overlap."""
    group = (await test_db_session.exec(select(Group).where(Group.name == "authenticated"))).one()
    await test_db_session.commit()

    async def seed() -> None:
        async with test_db_session_factory() as db:
            await _seed_default_step_authoring_once(db, group)
            await db.commit()

    await asyncio.gather(seed(), seed())
    async with test_db_session_factory() as db:
        await _defaults(db)
        assert len((await db.exec(select(SeedMarker))).all()) == 1
