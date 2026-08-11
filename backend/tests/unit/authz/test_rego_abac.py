"""Group 5: ABAC Conditions — label-based conditional access."""

from tests.unit.authz.conftest import allow_policy, build_authz_input, deny_policy, policies_for_role


class TestResourceLabelConditions:
    """Allow workflow:read only when team=platform."""

    def test_read_team_platform_allowed(self, evaluate_policy):
        policies = [
            allow_policy(
                "only-platform-read",
                ["workflow:read"],
                conditions={"resource_labels": {"team": "platform"}},
            ),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                resource_labels={"team": "platform"},
                effective_policies=policies,
            )
        )
        assert result["allow"] is True

    def test_read_team_infra_denied(self, evaluate_policy):
        policies = [
            allow_policy(
                "only-platform-read",
                ["workflow:read"],
                conditions={"resource_labels": {"team": "platform"}},
            ),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                resource_labels={"team": "infra"},
                effective_policies=policies,
            )
        )
        assert result["allow"] is False

    def test_read_no_labels_denied(self, evaluate_policy):
        policies = [
            allow_policy(
                "only-platform-read",
                ["workflow:read"],
                conditions={"resource_labels": {"team": "platform"}},
            ),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="workflow",
                effective_policies=policies,
            )
        )
        assert result["allow"] is False


class TestUserLabelConditions:
    """Allow workflow:delete only when user level=senior."""

    def test_senior_user_allowed(self, evaluate_policy):
        policies = [
            allow_policy(
                "senior-delete",
                ["workflow:delete"],
                conditions={"user_labels": {"level": "senior"}},
            ),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="delete",
                resource_type="workflow",
                user_labels={"level": "senior"},
                effective_policies=policies,
            )
        )
        assert result["allow"] is True

    def test_junior_user_denied(self, evaluate_policy):
        policies = [
            allow_policy(
                "senior-delete",
                ["workflow:delete"],
                conditions={"user_labels": {"level": "senior"}},
            ),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="delete",
                resource_type="workflow",
                user_labels={"level": "junior"},
                effective_policies=policies,
            )
        )
        assert result["allow"] is False


class TestUserLabelsNotCondition:
    """Tests for the user_labels_not condition type — deny or allow when user lacks specified labels."""

    _ALLOW_CRED = allow_policy("allow-cred-read", ["credential:read"])
    _DENY_NOT_ENGINEERING = deny_policy(
        "deny-not-engineering",
        ["credential:read"],
        conditions={"user_labels_not": {"department": "engineering"}},
    )

    def test_deny_fires_when_user_label_key_missing(self, evaluate_policy):
        """User has no labels — deny fires because they can't prove they're in engineering."""
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="credential",
                user_labels={},
                effective_policies=[self._ALLOW_CRED, self._DENY_NOT_ENGINEERING],
            )
        )
        assert result["allow"] is False
        assert result["deny"] is True

    def test_deny_fires_when_user_label_value_differs(self, evaluate_policy):
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="credential",
                user_labels={"department": "contractors"},
                effective_policies=[self._ALLOW_CRED, self._DENY_NOT_ENGINEERING],
            )
        )
        assert result["allow"] is False
        assert result["deny"] is True

    def test_allow_when_user_label_matches_excluded_value(self, evaluate_policy):
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="credential",
                user_labels={"department": "engineering"},
                effective_policies=[self._ALLOW_CRED, self._DENY_NOT_ENGINEERING],
            )
        )
        assert result["allow"] is True
        assert result["deny"] is False

    def test_deny_fires_when_all_user_keys_differ_or_missing(self, evaluate_policy):
        deny_multi = deny_policy(
            "deny-not-eng-senior",
            ["credential:read"],
            conditions={"user_labels_not": {"department": "engineering", "level": "senior"}},
        )
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="credential",
                user_labels={"department": "contractors"},
                effective_policies=[self._ALLOW_CRED, deny_multi],
            )
        )
        assert result["allow"] is False
        assert result["deny"] is True

    def test_allow_when_one_user_key_matches_excluded_value(self, evaluate_policy):
        deny_multi = deny_policy(
            "deny-not-eng-senior",
            ["credential:read"],
            conditions={"user_labels_not": {"department": "engineering", "level": "senior"}},
        )
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="credential",
                user_labels={"department": "engineering"},
                effective_policies=[self._ALLOW_CRED, deny_multi],
            )
        )
        assert result["allow"] is True
        assert result["deny"] is False

    def test_allow_effect_with_user_labels_not_grants_when_label_absent(self, evaluate_policy):
        """Allow-effect policy with user_labels_not grants access when user lacks the label."""
        policy = allow_policy(
            "allow-non-contractor",
            ["credential:read"],
            conditions={"user_labels_not": {"role": "contractor"}},
        )
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="credential",
                user_labels={"role": "engineer"},
                effective_policies=[policy],
            )
        )
        assert result["allow"] is True

    def test_allow_effect_with_user_labels_not_denies_when_label_matches(self, evaluate_policy):
        """Allow-effect policy with user_labels_not does not grant when user has the label."""
        policy = allow_policy(
            "allow-non-contractor",
            ["credential:read"],
            conditions={"user_labels_not": {"role": "contractor"}},
        )
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="credential",
                user_labels={"role": "contractor"},
                effective_policies=[policy],
            )
        )
        assert result["allow"] is False

    def test_combined_user_labels_and_user_labels_not(self, evaluate_policy):
        """Policy requiring user_labels AND user_labels_not — must be ops but not intern."""
        policy = allow_policy(
            "allow-ops-non-intern",
            ["credential:read"],
            conditions={
                "user_labels": {"team": "ops"},
                "user_labels_not": {"role": "intern"},
            },
        )
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="credential",
                user_labels={"team": "ops", "role": "senior"},
                effective_policies=[policy],
            )
        )
        assert result["allow"] is True

        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="credential",
                user_labels={"team": "ops", "role": "intern"},
                effective_policies=[policy],
            )
        )
        assert result["allow"] is False


class TestGroupLabelConditions:
    """Allow execution:run only when group tier=premium."""

    def test_premium_group_allowed(self, evaluate_policy):
        policies = [
            allow_policy(
                "premium-run",
                ["execution:run"],
                conditions={"group_labels": {"tier": "premium"}},
            ),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="run",
                resource_type="execution",
                groups=[{"name": "premium-team", "labels": {"tier": "premium"}}],
                effective_policies=policies,
            )
        )
        assert result["allow"] is True

    def test_basic_group_denied(self, evaluate_policy):
        policies = [
            allow_policy(
                "premium-run",
                ["execution:run"],
                conditions={"group_labels": {"tier": "premium"}},
            ),
        ]
        result = evaluate_policy(
            build_authz_input(
                action="run",
                resource_type="execution",
                groups=[{"name": "basic-team", "labels": {"tier": "basic"}}],
                effective_policies=policies,
            )
        )
        assert result["allow"] is False


class TestResourceLabelsNotCondition:
    """Deny credential:read when env label is NOT production (resource_labels_not condition)."""

    _ALLOW_CRED = allow_policy("allow-cred-read", ["credential:read"])
    _DENY_NOT_PROD = deny_policy(
        "deny-not-prod",
        ["credential:read"],
        conditions={"resource_labels_not": {"env": "production"}},
    )

    def test_deny_fires_when_label_key_missing(self, evaluate_policy):
        """THE BUG: resource has no labels at all — deny must fire."""
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="credential",
                resource_labels={},
                effective_policies=[self._ALLOW_CRED, self._DENY_NOT_PROD],
            )
        )
        assert result["allow"] is False
        assert result["deny"] is True

    def test_deny_fires_when_label_value_differs(self, evaluate_policy):
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="credential",
                resource_labels={"env": "staging"},
                effective_policies=[self._ALLOW_CRED, self._DENY_NOT_PROD],
            )
        )
        assert result["allow"] is False
        assert result["deny"] is True

    def test_allow_when_label_matches_excluded_value(self, evaluate_policy):
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="credential",
                resource_labels={"env": "production"},
                effective_policies=[self._ALLOW_CRED, self._DENY_NOT_PROD],
            )
        )
        assert result["allow"] is True
        assert result["deny"] is False

    def test_deny_fires_when_all_keys_differ_or_missing(self, evaluate_policy):
        """Multi-key: env=staging (differs) and tier missing — deny fires for both."""
        deny_multi = deny_policy(
            "deny-not-prod-gold",
            ["credential:read"],
            conditions={"resource_labels_not": {"env": "production", "tier": "gold"}},
        )
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="credential",
                resource_labels={"env": "staging"},
                effective_policies=[self._ALLOW_CRED, deny_multi],
            )
        )
        assert result["allow"] is False
        assert result["deny"] is True

    def test_allow_when_one_key_matches_excluded_value(self, evaluate_policy):
        """Multi-key AND semantics: env=production matches, so deny does not fire."""
        deny_multi = deny_policy(
            "deny-not-prod-gold",
            ["credential:read"],
            conditions={"resource_labels_not": {"env": "production", "tier": "gold"}},
        )
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="credential",
                resource_labels={"env": "production"},
                effective_policies=[self._ALLOW_CRED, deny_multi],
            )
        )
        assert result["allow"] is True
        assert result["deny"] is False

    def test_allow_when_all_keys_match_excluded_values(self, evaluate_policy):
        """All labels match the excluded values — deny does not fire."""
        deny_multi = deny_policy(
            "deny-not-prod-gold",
            ["credential:read"],
            conditions={"resource_labels_not": {"env": "production", "tier": "gold"}},
        )
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="credential",
                resource_labels={"env": "production", "tier": "gold"},
                effective_policies=[self._ALLOW_CRED, deny_multi],
            )
        )
        assert result["allow"] is True
        assert result["deny"] is False


class TestResourceLabelsNotViaDeny:
    """Allow workflow:delete via admin role + deny when status=archived."""

    _DENY_ARCHIVED = deny_policy(
        "deny-archived-delete",
        ["workflow:delete"],
        conditions={"resource_labels": {"status": "archived"}},
    )

    def test_delete_active_allowed(self, evaluate_policy):
        policies = [*policies_for_role("admin"), self._DENY_ARCHIVED]
        result = evaluate_policy(
            build_authz_input(
                action="delete",
                resource_type="workflow",
                resource_labels={"status": "active"},
                effective_policies=policies,
            )
        )
        assert result["allow"] is True

    def test_delete_archived_denied(self, evaluate_policy):
        policies = [*policies_for_role("admin"), self._DENY_ARCHIVED]
        result = evaluate_policy(
            build_authz_input(
                action="delete",
                resource_type="workflow",
                resource_labels={"status": "archived"},
                effective_policies=policies,
            )
        )
        assert result["allow"] is False
