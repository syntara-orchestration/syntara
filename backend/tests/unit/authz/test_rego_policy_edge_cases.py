"""Policy structure edge cases — SEC-038 to SEC-042, CHAOS-022, CHAOS-023.

Verifies behavior with multiple conditions (AND semantics), missing
conditions key, empty policy lists, and unknown effect/scope values.
"""

import pytest

from tests.unit.authz.conftest import allow_policy, build_authz_input, deny_policy, policies_for_role


class TestMultipleConditionsAND:
    """SEC-038: Multiple condition types combine with AND semantics."""

    def test_all_conditions_met_allows(self, evaluate_policy):
        """Allow when both resource_labels and user_labels match."""
        policies = [
            allow_policy(
                "multi-cond",
                ["workflow:read"],
                conditions={
                    "resource_labels": {"env": "production"},
                    "user_labels": {"clearance": "high"},
                },
            ),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                resource_labels={"env": "production"},
                user_labels={"clearance": "high"},
                effective_policies=policies,
            )
        )
        assert result["allow"] is True

    def test_only_resource_label_met_denied(self, evaluate_policy):
        """Deny when resource_labels match but user_labels do not."""
        policies = [
            allow_policy(
                "multi-cond",
                ["workflow:read"],
                conditions={
                    "resource_labels": {"env": "production"},
                    "user_labels": {"clearance": "high"},
                },
            ),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                resource_labels={"env": "production"},
                user_labels={"clearance": "low"},
                effective_policies=policies,
            )
        )
        assert result["allow"] is False

    def test_only_user_label_met_denied(self, evaluate_policy):
        """Deny when user_labels match but resource_labels do not."""
        policies = [
            allow_policy(
                "multi-cond",
                ["workflow:read"],
                conditions={
                    "resource_labels": {"env": "production"},
                    "user_labels": {"clearance": "high"},
                },
            ),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                resource_labels={"env": "staging"},
                user_labels={"clearance": "high"},
                effective_policies=policies,
            )
        )
        assert result["allow"] is False

    def test_neither_condition_met_denied(self, evaluate_policy):
        policies = [
            allow_policy(
                "multi-cond",
                ["workflow:read"],
                conditions={
                    "resource_labels": {"env": "production"},
                    "user_labels": {"clearance": "high"},
                },
            ),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                resource_labels={"env": "staging"},
                user_labels={"clearance": "low"},
                effective_policies=policies,
            )
        )
        assert result["allow"] is False

    def test_three_condition_types_all_required(self, evaluate_policy):
        """Resource labels + user labels + group labels must ALL match."""
        policies = [
            allow_policy(
                "triple-cond",
                ["execution:run"],
                conditions={
                    "resource_labels": {"env": "prod"},
                    "user_labels": {"role": "ops"},
                    "group_labels": {"tier": "premium"},
                },
            ),
        ]
        # All match -> allow
        result = evaluate_policy(
            build_authz_input(
                action="run",
                resource_type="execution",
                resource_labels={"env": "prod"},
                user_labels={"role": "ops"},
                groups=[{"name": "ops-team", "labels": {"tier": "premium"}}],
                effective_policies=policies,
            )
        )
        assert result["allow"] is True

        # Missing group label -> deny
        result = evaluate_policy(
            build_authz_input(
                action="run",
                resource_type="execution",
                resource_labels={"env": "prod"},
                user_labels={"role": "ops"},
                groups=[{"name": "basic-team", "labels": {"tier": "basic"}}],
                effective_policies=policies,
            )
        )
        assert result["allow"] is False


class TestNoConditionsKey:
    """SEC-039: Policy with no conditions key matches unconditionally."""

    def test_policy_without_conditions_key_allows(self, evaluate_policy):
        policies = [
            {
                "name": "no-conditions-policy",
                "effect": "allow",
                "actions": ["workflow:read"],
                "scope": "any",
            },
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                effective_policies=policies,
            )
        )
        assert result["allow"] is True

    def test_policy_without_conditions_key_allows_with_any_labels(self, evaluate_policy):
        """Should still allow even when resource has labels — policy just doesn't check them."""
        policies = [
            {
                "name": "no-conditions-policy",
                "effect": "allow",
                "actions": ["workflow:read"],
                "scope": "any",
            },
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                resource_labels={"env": "production", "team": "security"},
                effective_policies=policies,
            )
        )
        assert result["allow"] is True


class TestNoPoliciesDeny:
    """SEC-040: No effective policies → default deny."""

    def test_empty_policies_deny(self, evaluate_policy):
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                effective_policies=[],
            )
        )
        assert result["allow"] is False
        assert result["deny"] is False  # no deny policy fired either

    def test_none_policies_deny(self, evaluate_policy):
        """Omitted effective_policies (None -> []) also results in deny."""
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
            )
        )
        assert result["allow"] is False


class TestUnknownEffectIgnored:
    """SEC-041 / CHAOS-022: Policies with unknown effect values are silently ignored."""

    @pytest.mark.parametrize(
        "effect",
        ["maybe", "permit", "grant", "ALLOW", "Allow", ""],
        ids=["maybe", "permit", "grant", "ALLOW-caps", "Allow-mixed", "empty"],
    )
    def test_unknown_effect_does_not_allow(self, evaluate_policy, effect: str):
        policies = [
            {
                "name": "weird-effect",
                "effect": effect,
                "actions": ["workflow:read"],
                "scope": "any",
            },
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                effective_policies=policies,
            )
        )
        assert result["allow"] is False

    def test_unknown_effect_does_not_deny(self, evaluate_policy):
        """Effect 'maybe' should not trigger the deny rule either."""
        policies = [
            {
                "name": "maybe-policy",
                "effect": "maybe",
                "actions": ["workflow:read"],
                "scope": "any",
            },
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                effective_policies=policies,
            )
        )
        assert result["deny"] is False


class TestUnknownScopeIgnored:
    """SEC-042 / CHAOS-023: Policies with unknown scope values are silently ignored."""

    @pytest.mark.parametrize(
        "scope",
        ["everywhere", "global", "ALL", "team", ""],
        ids=["everywhere", "global", "ALL-caps", "team", "empty"],
    )
    def test_unknown_scope_does_not_allow(self, evaluate_policy, scope: str):
        policies = [
            {
                "name": "weird-scope",
                "effect": "allow",
                "actions": ["workflow:read"],
                "scope": scope,
            },
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                effective_policies=policies,
            )
        )
        assert result["allow"] is False

    @pytest.mark.parametrize(
        "scope",
        ["everywhere", "global", "ALL", ""],
        ids=["everywhere", "global", "ALL-caps", "empty"],
    )
    def test_unknown_scope_deny_does_not_fire(self, evaluate_policy, scope: str):
        """Deny policy with unknown scope should not fire — scope doesn't match."""
        policies = [
            *policies_for_role("admin"),
            {
                "name": "deny-weird-scope",
                "effect": "deny",
                "actions": ["workflow:read"],
                "scope": scope,
            },
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                effective_policies=policies,
            )
        )
        # The deny should NOT fire (unknown scope), so the admin allow still works
        assert result["allow"] is True
        assert result["deny"] is False


class TestDeniedByAndMatchedPolicy:
    """Verify denied_by and matched_policy output fields."""

    def test_denied_by_populated_on_deny(self, evaluate_policy):
        policies = [
            *policies_for_role("admin"),
            deny_policy("explicit-block", ["workflow:delete"]),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="delete",
                resource_type="workflow",
                effective_policies=policies,
            )
        )
        assert result["deny"] is True
        assert result["denied_by"] == "explicit-block"

    def test_matched_policy_populated_on_allow(self, evaluate_policy):
        policies = [
            allow_policy("test-allow-policy", ["workflow:read"]),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                effective_policies=policies,
            )
        )
        assert result["allow"] is True
        assert result["matched_policy"] == "test-allow-policy"

    def test_matched_policy_empty_on_deny(self, evaluate_policy):
        policies = [
            deny_policy("block-all", ["workflow:read"]),
            allow_policy("allow-read", ["workflow:read"]),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                effective_policies=policies,
            )
        )
        assert result["allow"] is False
        assert result["matched_policy"] == ""


class TestMetadataConditions:
    """Metadata-based conditions (resource_metadata, user_metadata)."""

    def test_resource_metadata_match_allows(self, evaluate_policy):
        policies = [
            allow_policy(
                "meta-match",
                ["workflow:read"],
                conditions={"resource_metadata": {"sensitivity": "public"}},
            ),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                resource_metadata={"sensitivity": "public"},
                effective_policies=policies,
            )
        )
        assert result["allow"] is True

    def test_resource_metadata_mismatch_denied(self, evaluate_policy):
        policies = [
            allow_policy(
                "meta-match",
                ["workflow:read"],
                conditions={"resource_metadata": {"sensitivity": "public"}},
            ),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                resource_metadata={"sensitivity": "classified"},
                effective_policies=policies,
            )
        )
        assert result["allow"] is False

    def test_user_metadata_match_allows(self, evaluate_policy):
        policies = [
            allow_policy(
                "user-meta",
                ["workflow:delete"],
                conditions={"user_metadata": {"department": "engineering"}},
            ),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="delete",
                resource_type="workflow",
                user_metadata={"department": "engineering"},
                effective_policies=policies,
            )
        )
        assert result["allow"] is True

    def test_user_metadata_mismatch_denied(self, evaluate_policy):
        policies = [
            allow_policy(
                "user-meta",
                ["workflow:delete"],
                conditions={"user_metadata": {"department": "engineering"}},
            ),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="delete",
                resource_type="workflow",
                user_metadata={"department": "marketing"},
                effective_policies=policies,
            )
        )
        assert result["allow"] is False


class TestAllowedProjects:
    """Verify the allowed_projects output set."""

    def test_any_scope_returns_wildcard_project(self, evaluate_policy):
        policies = [allow_policy("all-access", ["workflow:read"])]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                effective_policies=policies,
            )
        )
        assert "*" in result["allowed_projects"]

    def test_project_scope_returns_specific_project(self, evaluate_policy):
        policies = [
            allow_policy("proj-a-read", ["workflow:read"], scope="project", project="proj-a"),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                resource_project="proj-a",
                effective_policies=policies,
            )
        )
        assert "proj-a" in result["allowed_projects"]

    def test_multiple_project_scopes_collected(self, evaluate_policy):
        policies = [
            allow_policy("proj-a-read", ["workflow:read"], scope="project", project="proj-a"),
            allow_policy("proj-b-read", ["workflow:read"], scope="project", project="proj-b"),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                resource_project="proj-a",
                effective_policies=policies,
            )
        )
        assert "proj-a" in result["allowed_projects"]
        # proj-b also collected even though resource_project is proj-a
        assert "proj-b" in result["allowed_projects"]

    def test_denied_request_has_no_projects(self, evaluate_policy):
        policies = [
            allow_policy("proj-a-read", ["workflow:read"], scope="project", project="proj-a"),
            deny_policy("deny-all-read", ["workflow:read"]),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                resource_project="proj-a",
                effective_policies=policies,
            )
        )
        assert result["allowed_projects"] == []
