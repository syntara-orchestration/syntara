"""Deny override hardening — SEC-010, SEC-011, SEC-012, SEC-013.

Verifies that deny policies always override allow policies regardless
of specificity, scope, wildcards, or conditions.
"""

import pytest

from tests.unit.authz.conftest import build_authz_input, deny_policy, policies_for_role


class TestDenyBeatsAdmin:
    """SEC-010: Deny always overrides admin-level allow."""

    def test_deny_overrides_admin_for_specific_action(self, evaluate_policy):
        policies = [*policies_for_role("admin"), deny_policy("deny-policy-create", ["policy:create"])]
        result = evaluate_policy(
            build_authz_input(
                action="create",
                resource_type="policy",
                effective_policies=policies,
            )
        )
        assert result["allow"] is False
        assert result["deny"] is True

    def test_deny_overrides_admin_other_actions_unaffected(self, evaluate_policy):
        """Deny on policy:create should not affect policy:read."""
        policies = [*policies_for_role("admin"), deny_policy("deny-policy-create", ["policy:create"])]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="policy",
                effective_policies=policies,
            )
        )
        assert result["allow"] is True
        assert result["deny"] is False


class TestWildcardDeny:
    """SEC-011: Wildcard deny blocks all actions on a resource type."""

    @pytest.mark.parametrize(
        "action",
        ["create", "read", "update", "delete"],
        ids=["create", "read", "update", "delete"],
    )
    def test_wildcard_deny_blocks_all_crud(self, evaluate_policy, action: str):
        policies = [
            *policies_for_role("admin"),
            deny_policy("deny-all-workflow", ["workflow:*"]),
        ]
        result = evaluate_policy(
            build_authz_input(
                action=action,
                resource_type="workflow",
                effective_policies=policies,
            )
        )
        assert result["allow"] is False
        assert result["deny"] is True

    def test_wildcard_deny_does_not_affect_other_resources(self, evaluate_policy):
        """Wildcard deny on workflow:* should not block policy:read."""
        policies = [
            *policies_for_role("admin"),
            deny_policy("deny-all-workflow", ["workflow:*"]),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="policy",
                effective_policies=policies,
            )
        )
        assert result["allow"] is True


class TestProjectScopedDeny:
    """SEC-012: Deny scoped to a specific project only blocks that project."""

    def test_project_deny_blocks_target_project(self, evaluate_policy):
        policies = [
            *policies_for_role("admin"),
            {
                "name": "deny-prod-workflow-delete",
                "effect": "deny",
                "actions": ["workflow:delete"],
                "scope": "project",
                "project": "production",
            },
        ]
        result = evaluate_policy(
            build_authz_input(
                action="delete",
                resource_type="workflow",
                resource_project="production",
                effective_policies=policies,
            )
        )
        assert result["allow"] is False

    def test_project_deny_allows_other_project(self, evaluate_policy):
        policies = [
            *policies_for_role("admin"),
            {
                "name": "deny-prod-workflow-delete",
                "effect": "deny",
                "actions": ["workflow:delete"],
                "scope": "project",
                "project": "production",
            },
        ]
        result = evaluate_policy(
            build_authz_input(
                action="delete",
                resource_type="workflow",
                resource_project="staging",
                effective_policies=policies,
            )
        )
        assert result["allow"] is True


class TestConditionalDenyOverride:
    """SEC-013: Conditional deny only fires when conditions match."""

    _DENY_ARCHIVED = deny_policy(
        "deny-archived-ops",
        ["workflow:delete", "workflow:update"],
        conditions={"resource_labels": {"status": "archived"}},
    )

    @pytest.mark.parametrize(
        "action",
        ["delete", "update"],
        ids=["delete", "update"],
    )
    def test_conditional_deny_fires_when_label_matches(self, evaluate_policy, action: str):
        policies = [*policies_for_role("admin"), self._DENY_ARCHIVED]
        result = evaluate_policy(
            build_authz_input(
                action=action,
                resource_type="workflow",
                resource_labels={"status": "archived"},
                effective_policies=policies,
            )
        )
        assert result["allow"] is False
        assert result["deny"] is True

    @pytest.mark.parametrize(
        "action",
        ["delete", "update"],
        ids=["delete", "update"],
    )
    def test_conditional_deny_passes_when_label_absent(self, evaluate_policy, action: str):
        policies = [*policies_for_role("admin"), self._DENY_ARCHIVED]
        result = evaluate_policy(
            build_authz_input(
                action=action,
                resource_type="workflow",
                resource_labels={"status": "active"},
                effective_policies=policies,
            )
        )
        assert result["allow"] is True
        assert result["deny"] is False

    def test_conditional_deny_does_not_affect_unrelated_action(self, evaluate_policy):
        """Deny on delete/update should not block read."""
        policies = [*policies_for_role("admin"), self._DENY_ARCHIVED]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                resource_labels={"status": "archived"},
                effective_policies=policies,
            )
        )
        assert result["allow"] is True


class TestMultipleDenyPolicies:
    """Multiple deny policies stack — each independently blocks its actions."""

    def test_both_denies_fire_independently(self, evaluate_policy):
        policies = [
            *policies_for_role("admin"),
            deny_policy("deny-wf-delete", ["workflow:delete"]),
            deny_policy("deny-wf-create", ["workflow:create"]),
        ]
        # Both delete and create denied
        for action in ("delete", "create"):
            result = evaluate_policy(
                build_authz_input(
                    action=action,
                    resource_type="workflow",
                    effective_policies=policies,
                )
            )
            assert result["allow"] is False, f"Expected {action} to be denied"

    def test_non_denied_action_still_allowed(self, evaluate_policy):
        policies = [
            *policies_for_role("admin"),
            deny_policy("deny-wf-delete", ["workflow:delete"]),
            deny_policy("deny-wf-create", ["workflow:create"]),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                effective_policies=policies,
            )
        )
        assert result["allow"] is True
