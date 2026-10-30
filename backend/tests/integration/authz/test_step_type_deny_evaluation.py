"""Integration tests: step-type deny policies through the real evaluator.

Exercises the actual in-process RegoEvaluator and the real policy resolver
(the path every other test mocks out) for ``step_type:write`` deny
statements: global vs project scope, deny overriding the admin allow-all,
the shared Blocked step type contract, and deterministic multi-deny
reporting (AAP-99937).
"""

from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import insert
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.engine import AuthzRequest, authorize
from syntara.authz.evaluator import RegoEvaluator
from syntara.authz.models import RoleAssignment
from syntara.authz.models.policy import Policy
from syntara.authz.models.project import Project
from syntara.authz.models.role import Role
from syntara.authz.seed import seed_authz_data
from syntara.core.models import User
from syntara.core.models.group import Group, user_groups
from syntara.workflows.node_permissions import blocked_step_type, denied_node_labels

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def real_authz_evaluator() -> AsyncGenerator[RegoEvaluator, None]:
    """Create the real in-process authz evaluator."""
    evaluator = RegoEvaluator()
    evaluator.start()
    assert await evaluator.health() is True
    yield evaluator
    await evaluator.stop()


@pytest.fixture(autouse=True)
async def _seed(test_db_session: AsyncSession) -> None:
    """Seed built-in policies, roles, and groups before each test."""
    await seed_authz_data(test_db_session)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_user(session: AsyncSession, username: str) -> User:
    user = User(
        id=uuid4(),
        username=username,
        email=f"{username}@test.local",
        first_name=username.title(),
        password_hash="$argon2id$test",  # noqa: S106
        is_enabled=True,
    )
    session.add(user)
    await session.flush()
    return user


async def _assign_builtin_role(session: AsyncSession, user: User, role_name: str) -> None:
    """Attach a built-in role to *user* through a dedicated group."""
    group = Group(name=f"{role_name}-{uuid4()}", description="", labels={})
    session.add(group)
    await session.flush()
    session.add(RoleAssignment(group_id=group.id, role_name=role_name))
    await session.exec(insert(user_groups).values(user_id=user.id, group_id=group.id))
    await session.commit()


async def _attach_policy(
    session: AsyncSession,
    user: User,
    policy: Policy,
    *,
    project_id: UUID | None = None,
) -> None:
    """Persist *policy* (if needed) and attach it to *user* via a role + group."""
    session.add(policy)
    role = Role(
        id=uuid4(),
        name=f"role-{policy.name}-{uuid4().hex[:8]}",
        description="",
        is_builtin=False,
        policy_names=[policy.name],
        labels={},
    )
    session.add(role)
    group = Group(name=f"grp-{policy.name}-{uuid4().hex[:8]}", description="", labels={})
    session.add(group)
    await session.flush()
    session.add(RoleAssignment(group_id=group.id, role_name=role.name, project_id=project_id))
    await session.exec(insert(user_groups).values(user_id=user.id, group_id=group.id))
    await session.commit()


def _deny_policy(
    name: str,
    kind: str,
    *,
    scope: str = "any",
    project_id: UUID | None = None,
    not_condition: bool = False,
) -> Policy:
    """Build a deny policy for one step type (or every kind but one)."""
    condition_key = "resource_labels_not" if not_condition else "resource_labels"
    return Policy(
        id=uuid4(),
        name=name,
        description="",
        statements=[
            {
                "effect": "deny",
                "actions": ["step_type:write"],
                "scope": scope,
                "conditions": {condition_key: {"kind": kind}},
            }
        ],
        is_builtin=False,
        labels={},
        project_id=project_id,
    )


async def _check(
    session: AsyncSession,
    evaluator: RegoEvaluator,
    user: User,
    kind: str,
    *,
    project: str = "",
) -> tuple[bool, bool, str, list[str]]:
    """Evaluate step_type:write for *kind*; return (allowed, denied, denied_by, denied_by_policies)."""
    result = await authorize(
        session,
        evaluator,
        AuthzRequest(
            user_id=user.id,
            action="write",
            resource_type="step_type",
            resource_id="",
            resource_labels={"kind": kind},
            resource_project=project,
        ),
    )
    return result.allowed, result.denied, result.denied_by, result.denied_by_policies


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_global_deny_blocks_step_type_in_every_project(
    test_db_session: AsyncSession,
    real_authz_evaluator: RegoEvaluator,
) -> None:
    """A global deny blocks its step type in every project; others stay allowed."""
    user = await _make_user(test_db_session, "global-deny-admin")
    await _assign_builtin_role(test_db_session, user, "admin")
    await _attach_policy(test_db_session, user, _deny_policy("deny-script-global", "script"))

    for project in ("alpha", "beta"):
        allowed, denied, denied_by, _ = await _check(
            test_db_session, real_authz_evaluator, user, "script", project=project
        )
        assert allowed is False, f"script must be denied in project {project}"
        assert denied is True
        assert denied_by == "deny-script-global"

    # The admin allow-all builtin still covers kinds outside the deny.
    allowed, denied, _, _ = await _check(test_db_session, real_authz_evaluator, user, "approval")
    assert allowed is True
    assert denied is False


@pytest.mark.asyncio
async def test_deny_beats_admin_allow_all_no_admin_exemption(
    test_db_session: AsyncSession,
    real_authz_evaluator: RegoEvaluator,
) -> None:
    """An admin carrying a deny is denied — deny overrides the builtin allow-all."""
    admin_without_deny = await _make_user(test_db_session, "admin-no-deny")
    await _assign_builtin_role(test_db_session, admin_without_deny, "admin")

    admin_with_deny = await _make_user(test_db_session, "admin-with-deny")
    await _assign_builtin_role(test_db_session, admin_with_deny, "admin")
    await _attach_policy(test_db_session, admin_with_deny, _deny_policy("deny-agentic", "agentic"))

    allowed, _, _, _ = await _check(test_db_session, real_authz_evaluator, admin_without_deny, "agentic")
    assert allowed is True, "admin alone is allowed by the step_type:write builtin"

    allowed, denied, denied_by, _ = await _check(test_db_session, real_authz_evaluator, admin_with_deny, "agentic")
    assert allowed is False, "an admin carrying a deny is denied — no admin exemption"
    assert denied is True
    assert denied_by == "deny-agentic"


@pytest.mark.asyncio
async def test_project_deny_blocks_only_that_project(
    test_db_session: AsyncSession,
    real_authz_evaluator: RegoEvaluator,
) -> None:
    """A project-scoped deny blocks its step type only in that project."""
    project = Project(name=f"deny-proj-{uuid4().hex[:8]}", labels={})
    test_db_session.add(project)
    await test_db_session.flush()

    user = await _make_user(test_db_session, "project-deny-admin")
    await _assign_builtin_role(test_db_session, user, "admin")
    await _attach_policy(
        test_db_session,
        user,
        _deny_policy("deny-http-in-proj", "http_request", scope="project", project_id=project.id),
        project_id=project.id,
    )

    allowed, denied, denied_by, _ = await _check(
        test_db_session, real_authz_evaluator, user, "http_request", project=project.name
    )
    assert allowed is False
    assert denied is True
    assert denied_by == "deny-http-in-proj"

    # Outside the denying project the admin allow-all still applies.
    allowed, _, _, _ = await _check(
        test_db_session, real_authz_evaluator, user, "http_request", project="somewhere-else"
    )
    assert allowed is True


@pytest.mark.asyncio
async def test_blocked_step_type_contract_from_real_result(
    test_db_session: AsyncSession,
    real_authz_evaluator: RegoEvaluator,
) -> None:
    """denied_node_labels builds the shared contract with real evaluation."""
    project = Project(name=f"mixed-proj-{uuid4().hex[:8]}", labels={})
    test_db_session.add(project)
    await test_db_session.flush()

    user = await _make_user(test_db_session, "mixed-admin")
    await _assign_builtin_role(test_db_session, user, "admin")
    # Multi-statement mixed policy: statement 1 allows script, statement 0
    # denies http_request. The deny expands to "mixed-step-policy/0".
    mixed = Policy(
        id=uuid4(),
        name="mixed-step-policy",
        description="",
        statements=[
            {
                "effect": "deny",
                "actions": ["step_type:write"],
                "scope": "project",
                "conditions": {"resource_labels": {"kind": "http_request"}},
            },
            {
                "effect": "allow",
                "actions": ["step_type:write"],
                "scope": "project",
                "conditions": {"resource_labels": {"kind": "script"}},
            },
        ],
        is_builtin=False,
        labels={},
        project_id=project.id,
    )
    await _attach_policy(test_db_session, user, mixed, project_id=project.id)

    denials = await denied_node_labels(
        test_db_session,
        real_authz_evaluator,
        user.id,
        [{"kind": "script"}, {"kind": "http_request"}],
        project=project.name,
    )
    assert [d.kind for d in denials] == ["http_request"]
    denial = denials[0]
    # The original policy name and the deny statement's effective scope/project.
    assert denial.to_dict() == {
        "kind": "http_request",
        "label": "REST API",
        "reason": "explicit_deny",
        "policy": "mixed-step-policy",
        "scope": "project",
        "project": project.name,
    }


@pytest.mark.asyncio
async def test_no_matching_allow_reports_blocked_kind(
    test_db_session: AsyncSession,
    real_authz_evaluator: RegoEvaluator,
) -> None:
    """A principal without any step_type allow is blocked without an explicit deny."""
    # The "user" builtin role carries no step_type:write allow.
    user = await _make_user(test_db_session, "plain-user")
    await _assign_builtin_role(test_db_session, user, "user")

    allowed, denied, denied_by, _ = await _check(
        test_db_session, real_authz_evaluator, user, "script", project="payments"
    )
    assert allowed is False
    assert denied is False
    assert denied_by == ""

    denials = await denied_node_labels(
        test_db_session,
        real_authz_evaluator,
        user.id,
        [{"kind": "script"}],
        project="payments",
    )
    assert [d.to_dict() for d in denials] == [
        {
            "kind": "script",
            "label": "Script",
            "reason": "no_matching_allow",
            "policy": None,
            "scope": None,
            "project": "payments",
        }
    ]


@pytest.mark.asyncio
async def test_multiple_denies_report_deterministic_first(
    test_db_session: AsyncSession,
    real_authz_evaluator: RegoEvaluator,
) -> None:
    """Two matching denies: denied_by is the sorted-first, all are listed."""
    user = await _make_user(test_db_session, "multi-deny-admin")
    await _assign_builtin_role(test_db_session, user, "admin")
    await _attach_policy(test_db_session, user, _deny_policy("b-deny-script", "script"))
    await _attach_policy(test_db_session, user, _deny_policy("a-deny-script", "script"))

    allowed, denied, denied_by, denied_by_policies = await _check(test_db_session, real_authz_evaluator, user, "script")
    assert allowed is False
    assert denied is True
    assert denied_by == "a-deny-script"
    assert denied_by_policies == ["a-deny-script", "b-deny-script"]

    result = await authorize(
        test_db_session,
        real_authz_evaluator,
        AuthzRequest(
            user_id=user.id,
            action="write",
            resource_type="step_type",
            resource_id="",
            resource_labels={"kind": "script"},
        ),
    )
    denial = blocked_step_type(result, "script")
    assert denial.policy == "a-deny-script"
    assert denial.scope is None
    assert denial.project is None


@pytest.mark.asyncio
async def test_deny_with_resource_labels_not_condition(
    test_db_session: AsyncSession,
    real_authz_evaluator: RegoEvaluator,
) -> None:
    """A deny with resource_labels_not blocks every kind except the listed one."""
    user = await _make_user(test_db_session, "not-condition-admin")
    await _assign_builtin_role(test_db_session, user, "admin")
    await _attach_policy(test_db_session, user, _deny_policy("deny-all-but-script", "script", not_condition=True))

    allowed, _, _, _ = await _check(test_db_session, real_authz_evaluator, user, "script")
    assert allowed is True, "the excluded kind is not denied"

    allowed, denied, denied_by, _ = await _check(test_db_session, real_authz_evaluator, user, "approval")
    assert allowed is False
    assert denied is True
    assert denied_by == "deny-all-but-script"
