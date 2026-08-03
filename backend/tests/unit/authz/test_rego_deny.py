"""Group 4: Deny Rules — deny overrides and deny with conditions."""

import pytest

from tests.unit.authz.conftest import build_authz_input, deny_policy, policies_for_role

_DENY_PROD_DELETE = deny_policy(
    "deny-prod-delete",
    ["workflow:delete"],
    conditions={"resource_labels": {"env": "production"}},
)


class TestDenyOverridesAllow:
    """Explicit deny on workflow:delete overrides admin allow."""

    @pytest.mark.parametrize(
        ("action", "resource_type", "expected"),
        [
            ("read", "workflow", True),
            ("create", "workflow", True),
            ("delete", "workflow", False),
        ],
        ids=["workflow:read-allowed", "workflow:create-allowed", "workflow:delete-denied"],
    )
    def test_deny_overrides_allow(
        self,
        evaluate_policy,
        action: str,
        resource_type: str,
        expected: bool,  # noqa: FBT001
    ):
        policies = [*policies_for_role("admin"), deny_policy("deny-wf-delete", ["workflow:delete"])]
        result = evaluate_policy(
            build_authz_input(
                action=action,
                resource_type=resource_type,
                effective_policies=policies,
            )
        )
        assert result["allow"] is expected


class TestDenyWithResourceLabels:
    """Deny workflow:delete only when env=production."""

    def test_delete_production_denied(self, evaluate_policy):
        policies = [*policies_for_role("admin"), _DENY_PROD_DELETE]
        result = evaluate_policy(
            build_authz_input(
                action="delete",
                resource_type="workflow",
                resource_labels={"env": "production"},
                effective_policies=policies,
            )
        )
        assert result["allow"] is False

    def test_delete_staging_allowed(self, evaluate_policy):
        policies = [*policies_for_role("admin"), _DENY_PROD_DELETE]
        result = evaluate_policy(
            build_authz_input(
                action="delete",
                resource_type="workflow",
                resource_labels={"env": "staging"},
                effective_policies=policies,
            )
        )
        assert result["allow"] is True

    def test_delete_no_labels_allowed(self, evaluate_policy):
        policies = [*policies_for_role("admin"), _DENY_PROD_DELETE]
        result = evaluate_policy(
            build_authz_input(
                action="delete",
                resource_type="workflow",
                effective_policies=policies,
            )
        )
        assert result["allow"] is True


class TestWildcardAllowSpecificDeny:
    """Admin role (workflow CRUD) + deny workflow:update."""

    @pytest.mark.parametrize(
        ("action", "resource_type", "expected"),
        [
            ("read", "workflow", True),
            ("create", "workflow", True),
            ("delete", "workflow", True),
            ("update", "workflow", False),
        ],
        ids=[
            "workflow:read-allowed",
            "workflow:create-allowed",
            "workflow:delete-allowed",
            "workflow:update-denied",
        ],
    )
    def test_wildcard_allow_specific_deny(
        self,
        evaluate_policy,
        action: str,
        resource_type: str,
        expected: bool,  # noqa: FBT001
    ):
        policies = [*policies_for_role("admin"), deny_policy("deny-wf-update", ["workflow:update"])]
        result = evaluate_policy(
            build_authz_input(
                action=action,
                resource_type=resource_type,
                effective_policies=policies,
            )
        )
        assert result["allow"] is expected
