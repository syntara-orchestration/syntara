"""Scope bypass hardening — SEC-006, SEC-007, SEC-008.

Verifies that self-scope and project-scope cannot be bypassed
by manipulating resource IDs or project fields.
"""

import pytest

from tests.unit.authz.conftest import allow_policy, build_authz_input, deny_policy


class TestSelfScopeBypass:
    """SEC-006/007: Self-scope must not be tricked by wrong or empty IDs."""

    def test_self_scope_wrong_user_id_denied(self, evaluate_policy):
        """SEC-006: Self-scope denies when resource_id is a different user."""
        policies = [
            allow_policy("user:read:self", ["user:read"], scope="self"),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="user",
                resource_id="attacker-id",
                user_id="victim-id",
                effective_policies=policies,
            )
        )
        assert result["allow"] is False

    def test_self_scope_empty_both_ids_allowed(self, evaluate_policy):
        """SEC-007: When both user_id and resource_id are empty, "" == "" matches.

        This is a known Rego behavior — empty strings are equal.  The
        application layer must ensure user_id is never empty before
        reaching Rego.
        """
        policies = [
            allow_policy("user:read:self", ["user:read"], scope="self"),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="user",
                resource_id="",
                user_id="",
                effective_policies=policies,
            )
        )
        assert result["allow"] is True

    def test_self_scope_rejects_mismatched_resource_type(self, evaluate_policy):
        """Self-scope must not match when resource type differs from policy target.

        A self-scoped policy granting workflow:read should not match just
        because resource.id == user.id — that would be a privilege
        escalation (SEC-006).  Self-scope is only valid for resource
        types with an explicit _scope_matches rule (user, user_identity,
        group).
        """
        policies = [
            allow_policy("user:read:self", ["workflow:read"], scope="self"),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                resource_id="test-user-id",
                user_id="test-user-id",
                effective_policies=policies,
            )
        )
        assert result["allow"] is False

    @pytest.mark.parametrize(
        "resource_id",
        [
            "test-user-id ",
            " test-user-id",
            "TEST-USER-ID",
        ],
        ids=["trailing-space", "leading-space", "uppercase"],
    )
    def test_self_scope_near_match_denied(self, evaluate_policy, resource_id: str):
        """Self-scope requires exact string match — whitespace/case variants denied."""
        policies = [
            allow_policy("user:read:self", ["user:read"], scope="self"),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="user",
                resource_id=resource_id,
                user_id="test-user-id",
                effective_policies=policies,
            )
        )
        assert result["allow"] is False


class TestProjectScopeBypass:
    """SEC-008: Project-scope must not grant access when project is empty or mismatched."""

    def test_project_scope_empty_resource_project_denied(self, evaluate_policy):
        """SEC-008: Project-scoped policy denies when resource has no project."""
        policies = [
            allow_policy("workflow:read:proj-x", ["workflow:read"], scope="project", project="proj-x"),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                resource_project="",
                effective_policies=policies,
            )
        )
        assert result["allow"] is False

    def test_project_scope_empty_policy_project_denied(self, evaluate_policy):
        """Project-scoped policy with empty project field should not match any resource."""
        policies = [
            allow_policy("workflow:read:empty", ["workflow:read"], scope="project", project=""),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                resource_project="proj-x",
                effective_policies=policies,
            )
        )
        assert result["allow"] is False

    def test_project_scope_both_empty_denied(self, evaluate_policy):
        """When policy project is empty, allow_policy() omits the key entirely.

        Rego treats missing ``policy.project`` as undefined, so the
        comparison ``policy.project == input.resource.project`` fails.
        Result: deny.  This is safe — a project-scoped policy without
        a project field cannot match anything.
        """
        policies = [
            allow_policy("workflow:read:empty", ["workflow:read"], scope="project", project=""),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                resource_project="",
                effective_policies=policies,
            )
        )
        assert result["allow"] is False

    @pytest.mark.parametrize(
        "resource_project",
        [
            "proj-X",
            "proj-x ",
            " proj-x",
        ],
        ids=["case-mismatch", "trailing-space", "leading-space"],
    )
    def test_project_scope_near_match_denied(self, evaluate_policy, resource_project: str):
        """Project scope requires exact string match."""
        policies = [
            allow_policy("workflow:read:proj-x", ["workflow:read"], scope="project", project="proj-x"),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                resource_project=resource_project,
                effective_policies=policies,
            )
        )
        assert result["allow"] is False

    def test_project_scope_multiple_projects_isolated(self, evaluate_policy):
        """User with access to proj-a cannot access proj-b resources."""
        policies = [
            allow_policy("workflow:read:proj-a", ["workflow:read"], scope="project", project="proj-a"),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                resource_project="proj-b",
                effective_policies=policies,
            )
        )
        assert result["allow"] is False

    def test_any_project_flag_allows_empty_resource_project(self, evaluate_policy):
        """check_any_project / any_project=true matches a concrete project grant."""
        policies = [
            allow_policy(
                "role-assignment:read:proj-x",
                ["role-assignment:read"],
                scope="project",
                project="proj-x",
            ),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="role-assignment",
                resource_project="",
                any_project=True,
                effective_policies=policies,
            )
        )
        assert result["allow"] is True

    def test_any_project_flag_false_still_denies_empty_project(self, evaluate_policy):
        """SEC-008 still holds when any_project is explicitly false."""
        policies = [
            allow_policy("workflow:read:proj-x", ["workflow:read"], scope="project", project="proj-x"),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                resource_project="",
                any_project=False,
                effective_policies=policies,
            )
        )
        assert result["allow"] is False

    def test_any_project_flag_ignores_empty_policy_project(self, evaluate_policy):
        """any_project must not match project-scoped policies with empty project."""
        policies = [
            allow_policy("workflow:read:empty", ["workflow:read"], scope="project", project=""),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                resource_project="",
                any_project=True,
                effective_policies=policies,
            )
        )
        assert result["allow"] is False

    def test_any_project_does_not_grant_unrelated_action(self, evaluate_policy):
        """any_project only widens scope matching — action must still match."""
        policies = [
            allow_policy("workflow:read:proj-x", ["workflow:read"], scope="project", project="proj-x"),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="create",
                resource_type="workflow",
                resource_project="",
                any_project=True,
                effective_policies=policies,
            )
        )
        assert result["allow"] is False

    def test_any_project_deny_in_one_project_blocks_allow_elsewhere(self, evaluate_policy):
        """Deny+any_project is fail-closed across projects.

        Deny policies also use _scope_matches — any_project makes a project
        deny match without a concrete resource project. A targeted deny in any
        project suppresses the action for check_any_project=true UI gates,
        even if another project still has an allow grant.
        """
        policies = [
            allow_policy(
                "role-assignment:read:proj-a",
                ["role-assignment:read"],
                scope="project",
                project="proj-a",
            ),
            {
                **deny_policy(
                    "role-assignment:read:deny-b",
                    ["role-assignment:read"],
                    scope="project",
                ),
                "project": "proj-b",
            },
        ]

        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="role-assignment",
                resource_project="",
                any_project=True,
                effective_policies=policies,
            )
        )
        assert result["allow"] is False
        assert result["deny"] is True

    def test_any_project_allow_without_deny_still_allows(self, evaluate_policy):
        """Control: allow-only project grant still allows with any_project."""
        policies = [
            allow_policy(
                "role-assignment:read:proj-a",
                ["role-assignment:read"],
                scope="project",
                project="proj-a",
            ),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="role-assignment",
                resource_project="",
                any_project=True,
                effective_policies=policies,
            )
        )
        assert result["allow"] is True
        assert result["deny"] is False
