"""Tests for role_conventions module — builtin registries and lookup helpers."""

import pytest

from syntara.authz.role_conventions import (
    BUILTIN_POLICIES,
    BUILTIN_ROLES,
    PolicyInfo,
    builtin_policy_uuid,
    builtin_role_policy_names,
    builtin_role_uuid,
    get_builtin_policy,
    get_builtin_role,
    is_builtin_policy,
    is_builtin_role,
    resolve_builtin_policy_statements,
    resolve_builtin_role_statements,
)

# ============================================================================
# PolicyInfo
# ============================================================================


class TestPolicyInfo:  # noqa: D101
    def test_name_format(self) -> None:
        p = PolicyInfo("workflow", "create", scope="project")
        assert p.name == "workflow:create:project"

    def test_name_default_scope(self) -> None:
        p = PolicyInfo("workflow", "read")
        assert p.name == "workflow:read:any"

    def test_description(self) -> None:
        p = PolicyInfo("workflow", "create")
        assert "Create" in p.description
        assert "workflow" in p.description

    def test_description_self_scope(self) -> None:
        p = PolicyInfo("user", "read", scope="self")
        assert "own" in p.description

    def test_statements(self) -> None:
        p = PolicyInfo("workflow", "read", scope="project")
        stmts = p.statements
        assert len(stmts) == 1
        assert stmts[0]["effect"] == "allow"
        assert stmts[0]["actions"] == ["workflow:read"]
        assert stmts[0]["scope"] == "project"

    def test_from_name_three_parts(self) -> None:
        p = PolicyInfo.from_name("credential:delete:project")
        assert p.resource == "credential"
        assert p.action == "delete"
        assert p.scope == "project"

    def test_from_name_two_parts(self) -> None:
        p = PolicyInfo.from_name("workflow:read")
        assert p.resource == "workflow"
        assert p.action == "read"
        assert p.scope == "any"

    def test_from_name_invalid(self) -> None:
        with pytest.raises(ValueError, match="Invalid policy name"):
            PolicyInfo.from_name("single")


# ============================================================================
# Lookup helpers
# ============================================================================


class TestLookupHelpers:  # noqa: D101
    def test_get_builtin_policy_exists(self) -> None:
        p = get_builtin_policy("workflow:read:any")
        assert p is not None
        assert p.resource == "workflow"
        assert p.action == "read"

    def test_get_builtin_policy_not_found(self) -> None:
        assert get_builtin_policy("nonexistent:policy:any") is None

    def test_get_builtin_role_exists(self) -> None:
        r = get_builtin_role("admin")
        assert r is not None
        assert r.name == "admin"

    def test_get_builtin_role_not_found(self) -> None:
        assert get_builtin_role("nonexistent-role") is None

    def test_is_builtin_role(self) -> None:
        assert is_builtin_role("admin") is True
        assert is_builtin_role("project-admin") is True
        assert is_builtin_role("fake-role") is False

    def test_is_builtin_policy(self) -> None:
        assert is_builtin_policy("workflow:read:any") is True
        assert is_builtin_policy("fake:policy:any") is False


# ============================================================================
# Role→policy mapping
# ============================================================================


class TestRolePolicyMapping:  # noqa: D101
    def test_admin_has_all_admin_policies(self) -> None:
        names = builtin_role_policy_names("admin")
        assert len(names) > 0
        admin_policies = [p.name for p in BUILTIN_POLICIES if "admin" in p.roles]
        for policy_name in admin_policies:
            assert policy_name in names

    def test_project_admin_has_project_scoped_policies(self) -> None:
        names = builtin_role_policy_names("project-admin")
        project_policies = [n for n in names if ":project" in n]
        assert len(project_policies) > 0

    def test_authenticated_role_has_default_policies(self) -> None:
        names = builtin_role_policy_names("authenticated")
        assert len(names) > 0
        assert "user:read:self" in names
        assert "user:update:self" in names
        assert "role-assignment:read:self" in names

    def test_admin_has_credential_use(self) -> None:
        names = builtin_role_policy_names("admin")
        assert "credential:use:any" in names

    def test_project_admin_has_credential_use(self) -> None:
        names = builtin_role_policy_names("project-admin")
        assert "credential:use:project" in names

    def test_project_user_has_credential_use(self) -> None:
        names = builtin_role_policy_names("project-user")
        assert "credential:use:project" in names

    def test_auditor_does_not_have_credential_use(self) -> None:
        names = builtin_role_policy_names("auditor")
        assert not any("credential:use" in n for n in names)

    def test_user_does_not_have_credential_use(self) -> None:
        names = builtin_role_policy_names("user")
        assert not any("credential:use" in n for n in names)

    def test_project_auditor_does_not_have_credential_use(self) -> None:
        names = builtin_role_policy_names("project-auditor")
        assert not any("credential:use" in n for n in names)

    def test_unknown_role_returns_empty(self) -> None:
        names = builtin_role_policy_names("nonexistent")
        assert names == []

    def test_every_builtin_role_has_policies(self) -> None:
        for role in BUILTIN_ROLES:
            names = builtin_role_policy_names(role.name)
            assert len(names) > 0, f"Role '{role.name}' has no policies assigned"


# ============================================================================
# Statement resolution
# ============================================================================


class TestStatementResolution:  # noqa: D101
    def test_resolve_builtin_policy_statements(self) -> None:
        stmts = resolve_builtin_policy_statements("workflow:read:any")
        assert len(stmts) == 1
        assert stmts[0]["effect"] == "allow"
        assert stmts[0]["actions"] == ["workflow:read"]

    def test_resolve_builtin_policy_statements_unknown(self) -> None:
        stmts = resolve_builtin_policy_statements("nonexistent:policy:any")
        assert stmts == []

    def test_resolve_builtin_role_statements(self) -> None:
        stmts = resolve_builtin_role_statements("user")
        assert len(stmts) > 0
        actions = {a for s in stmts for a in s["actions"]}
        assert "project:create" in actions
        assert "user-directory:read" in actions
        assert "group-directory:read" in actions
        assert "user:read" not in actions
        assert "group:read" not in actions

    def test_resolve_builtin_role_statements_unknown(self) -> None:
        stmts = resolve_builtin_role_statements("nonexistent")
        assert stmts == []


# ============================================================================
# Deterministic UUIDs
# ============================================================================


class TestDeterministicUUIDs:  # noqa: D101
    def test_policy_uuid_is_stable(self) -> None:
        uuid1 = builtin_policy_uuid("workflow:read:any")
        uuid2 = builtin_policy_uuid("workflow:read:any")
        assert uuid1 == uuid2

    def test_role_uuid_is_stable(self) -> None:
        uuid1 = builtin_role_uuid("admin")
        uuid2 = builtin_role_uuid("admin")
        assert uuid1 == uuid2

    def test_different_names_produce_different_uuids(self) -> None:
        assert builtin_policy_uuid("workflow:read:any") != builtin_policy_uuid("workflow:create:any")
        assert builtin_role_uuid("admin") != builtin_role_uuid("user")

    def test_policy_and_role_uuids_differ_for_same_name(self) -> None:
        assert builtin_policy_uuid("admin") != builtin_role_uuid("admin")


# ============================================================================
# Registry integrity
# ============================================================================


class TestRegistryIntegrity:  # noqa: D101
    def test_no_duplicate_policy_names(self) -> None:
        names = [p.name for p in BUILTIN_POLICIES]
        assert len(names) == len(set(names)), f"Duplicate policies: {[n for n in names if names.count(n) > 1]}"

    def test_no_duplicate_role_names(self) -> None:
        names = [r.name for r in BUILTIN_ROLES]
        assert len(names) == len(set(names))

    def test_all_policy_roles_reference_valid_roles(self) -> None:
        role_names = {r.name for r in BUILTIN_ROLES}
        for policy in BUILTIN_POLICIES:
            for role_name in policy.roles:
                assert role_name in role_names, f"Policy '{policy.name}' references unknown role '{role_name}'"

    def test_project_scoped_roles_have_project_scope(self) -> None:
        for role in BUILTIN_ROLES:
            if role.name.startswith("project-"):
                assert role.scope == "project", f"Role '{role.name}' should have scope='project'"

    def test_all_builtin_policies_have_test_coverage(self) -> None:
        from tests.e2e.authz.policies.conftest import (
            E2E_COVERAGE_EXEMPT,
            OWN_SCOPED_CASES,
            PROJECT_SCOPED_CASES,
            SELF_SCOPED_CASES,
            SYSTEM_SCOPED_REPRESENTATIVE,
        )

        e2e_covered = {
            c.policy for c in PROJECT_SCOPED_CASES + SYSTEM_SCOPED_REPRESENTATIVE + SELF_SCOPED_CASES + OWN_SCOPED_CASES
        }
        accounted_for = e2e_covered | E2E_COVERAGE_EXEMPT
        all_builtin = {p.name for p in BUILTIN_POLICIES}

        missing = sorted(all_builtin - accounted_for)
        assert not missing, (
            f"{len(missing)} built-in policies have no test coverage. "
            f"Add a PolicyTestCase to the appropriate list in "
            f"tests/e2e/authorization/policies/conftest.py:\n"
            f"  - project-scoped → PROJECT_SCOPED_CASES\n"
            f"  - system-scoped  → SYSTEM_SCOPED_REPRESENTATIVE\n"
            f"  - self-scoped    → SELF_SCOPED_CASES\n"
            f"Or, if unit-test coverage is sufficient, add to E2E_COVERAGE_EXEMPT.\n"
            f"\nMissing policies:\n  " + "\n  ".join(missing)
        )

        stale = sorted(accounted_for - all_builtin)
        assert not stale, (
            f"{len(stale)} policies are listed in e2e test cases or "
            f"E2E_COVERAGE_EXEMPT but no longer exist in BUILTIN_POLICIES. "
            f"Remove them from tests/e2e/authorization/policies/conftest.py:\n  " + "\n  ".join(stale)
        )

    def test_own_scope_policies_have_project_constraint(self) -> None:
        """Verify all 'own'-scoped policies have a project constraint.

        This test verifies that the removed project-less 'own' Rego branch
        (commit 8ac5970e1) is not needed by any builtin policies. All 'own'-scoped
        policies must have scope="own" AND be assigned only to project-scoped roles,
        ensuring they always have a project constraint.

        If this test fails, it means a builtin policy uses 'own' scope in a
        system-scoped context, which would require the removed Rego branch.
        """
        from syntara.authz.role_conventions import BUILTIN_ROLES

        # Collect all roles by scope
        system_roles = {r.name for r in BUILTIN_ROLES if r.scope != "project"}
        project_roles = {r.name for r in BUILTIN_ROLES if r.scope == "project"}

        # Check all own-scoped policies
        own_policies = [p for p in BUILTIN_POLICIES if p.scope == "own"]

        for policy in own_policies:
            # Verify the policy is only assigned to project-scoped roles
            assigned_roles = set(policy.roles)
            system_role_assignments = assigned_roles & system_roles

            assert not system_role_assignments, (
                f"Policy '{policy.name}' has scope='own' but is assigned to "
                f"system-scoped roles: {sorted(system_role_assignments)}. "
                f"Own-scoped policies require a project constraint (removed in commit 8ac5970e1). "
                f"Either change the scope to 'any' or assign only to project-scoped roles."
            )

            # All assignments should be to project roles
            assert assigned_roles & project_roles, (
                f"Policy '{policy.name}' has scope='own' but is not assigned to any "
                f"project-scoped roles. Assigned to: {sorted(assigned_roles)}"
            )
