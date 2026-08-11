"""Group 6: Scope Rules — any, self, project scope behavior."""

import pytest

from tests.unit.authz.conftest import allow_policy, build_authz_input, policies_for_role


class TestAnyScopeUniversal:
    """Auditor policies (scope=any) allow read in any project context."""

    @pytest.mark.parametrize(
        ("action", "resource_type"),
        [
            ("read", "workflow"),
            ("read", "execution"),
            ("read", "project"),
        ],
        ids=["workflow:read", "execution:read", "project:read"],
    )
    def test_any_scope_universal(self, evaluate_policy, action: str, resource_type: str):
        result = evaluate_policy(
            build_authz_input(
                action=action,
                resource_type=resource_type,
                effective_policies=policies_for_role("auditor"),
            )
        )
        assert result["allow"] is True


class TestSelfScopeOwnOnly:
    """Self-scoped policy only allows when resource_id matches user_id."""

    def test_self_scope_own_resource(self, evaluate_policy):
        user_id = "user-uuid-123"
        policies = [
            allow_policy("user:read:self", ["user:read"], scope="self"),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="user",
                resource_id=user_id,
                user_id=user_id,
                effective_policies=policies,
            )
        )
        assert result["allow"] is True

    def test_self_scope_other_resource_denied(self, evaluate_policy):
        policies = [
            allow_policy("user:read:self", ["user:read"], scope="self"),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="user",
                resource_id="other-user-id",
                user_id="test-user-id",
                effective_policies=policies,
            )
        )
        assert result["allow"] is False

    def test_self_scope_empty_resource_id_denied(self, evaluate_policy):
        policies = [
            allow_policy("user:read:self", ["user:read"], scope="self"),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="user",
                resource_id="",
                user_id="test-user-id",
                effective_policies=policies,
            )
        )
        assert result["allow"] is False


class TestGroupSelfScope:
    """Self-scoped group policy allows when user is a member of the group."""

    def test_group_self_scope_member_allowed(self, evaluate_policy):
        group_id = "group-uuid-123"
        policies = [
            allow_policy("group:read:self", ["group:read"], scope="self"),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="group",
                resource_id=group_id,
                groups=[{"name": "my-group", "id": group_id, "labels": {}}],
                effective_policies=policies,
            )
        )
        assert result["allow"] is True

    def test_group_self_scope_non_member_denied(self, evaluate_policy):
        policies = [
            allow_policy("group:read:self", ["group:read"], scope="self"),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="group",
                resource_id="other-group-id",
                groups=[{"name": "my-group", "id": "my-group-id", "labels": {}}],
                effective_policies=policies,
            )
        )
        assert result["allow"] is False

    def test_group_self_scope_empty_groups_denied(self, evaluate_policy):
        policies = [
            allow_policy("group:read:self", ["group:read"], scope="self"),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="group",
                resource_id="some-group-id",
                groups=[],
                effective_policies=policies,
            )
        )
        assert result["allow"] is False

    def test_group_any_scope_still_works(self, evaluate_policy):
        policies = [
            allow_policy("group:read:any", ["group:read"], scope="any"),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="group",
                resource_id="any-group-id",
                effective_policies=policies,
            )
        )
        assert result["allow"] is True


class TestProjectScopeBoundaries:
    """Project-scoped policy allows in matching project, denies in others."""

    def test_project_scope_matching_project_allowed(self, evaluate_policy):
        policies = [
            allow_policy("workflow:read:proj-x", ["workflow:read"], scope="project", project="proj-x"),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                resource_project="proj-x",
                effective_policies=policies,
            )
        )
        assert result["allow"] is True

    def test_project_scope_different_project_denied(self, evaluate_policy):
        policies = [
            allow_policy("workflow:read:proj-x", ["workflow:read"], scope="project", project="proj-x"),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                resource_project="proj-y",
                effective_policies=policies,
            )
        )
        assert result["allow"] is False
