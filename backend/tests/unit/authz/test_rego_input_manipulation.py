"""Input manipulation hardening — SEC-014 to SEC-018, CHAOS-001, CHAOS-007, CHAOS-024.

Verifies that malformed, empty, or adversarial input fields
result in deny (never allow).
"""

import pytest

from tests.unit.authz.conftest import allow_policy, build_authz_input, policies_for_role


class TestEmptyActionField:
    """SEC-014 / CHAOS-001: Empty action string must be denied."""

    def test_empty_action_with_admin_policies(self, evaluate_policy):
        result = evaluate_policy(
            build_authz_input(
                action="",
                resource_type="workflow",
                effective_policies=policies_for_role("admin"),
            )
        )
        assert result["allow"] is False

    def test_empty_action_with_user_policies(self, evaluate_policy):
        result = evaluate_policy(
            build_authz_input(
                action="",
                resource_type="workflow",
                effective_policies=policies_for_role("user"),
            )
        )
        assert result["allow"] is False


class TestEmptyResourceType:
    """SEC-015: Empty resource_type must be denied."""

    def test_empty_resource_type_with_admin_policies(self, evaluate_policy):
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="",
                effective_policies=policies_for_role("admin"),
            )
        )
        assert result["allow"] is False

    def test_empty_resource_type_with_user_policies(self, evaluate_policy):
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="",
                effective_policies=policies_for_role("user"),
            )
        )
        assert result["allow"] is False


class TestUnknownResourceType:
    """SEC-016: Unknown resource types are implicitly denied."""

    @pytest.mark.parametrize(
        ("action", "resource_type"),
        [
            ("read", "nonexistent"),
            ("create", "secret"),
            ("delete", "database"),
            ("admin", "system"),
        ],
        ids=["read:nonexistent", "create:secret", "delete:database", "admin:system"],
    )
    def test_unknown_resource_denied_even_with_admin(self, evaluate_policy, action: str, resource_type: str):
        result = evaluate_policy(
            build_authz_input(
                action=action,
                resource_type=resource_type,
                effective_policies=policies_for_role("admin"),
            )
        )
        assert result["allow"] is False


class TestWildcardInRequest:
    """SEC-017 / CHAOS-024: Wildcards in action or resource_type fields do not grant access."""

    def test_wildcard_action_denied(self, evaluate_policy):
        """Action field '*' should not match any policy."""
        result = evaluate_policy(
            build_authz_input(
                action="*",
                resource_type="workflow",
                effective_policies=policies_for_role("admin"),
            )
        )
        assert result["allow"] is False

    def test_wildcard_resource_type_denied(self, evaluate_policy):
        """Resource type '*' should not match any policy."""
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="*",
                effective_policies=policies_for_role("admin"),
            )
        )
        assert result["allow"] is False

    def test_star_star_action_denied(self, evaluate_policy):
        """CHAOS-024: '*:*' as action should not grant access."""
        result = evaluate_policy(
            build_authz_input(
                action="*:*",
                resource_type="workflow",
                effective_policies=policies_for_role("admin"),
            )
        )
        assert result["allow"] is False

    def test_wildcard_both_fields_denied(self, evaluate_policy):
        """Both action='*' and resource_type='*' denied."""
        result = evaluate_policy(
            build_authz_input(
                action="*",
                resource_type="*",
                effective_policies=policies_for_role("admin"),
            )
        )
        assert result["allow"] is False


class TestLongStrings:
    """SEC-018: Extremely long strings do not cause Rego to crash or allow."""

    def test_long_action_denied(self, evaluate_policy):
        result = evaluate_policy(
            build_authz_input(
                action="a" * 10000,
                resource_type="workflow",
                effective_policies=policies_for_role("admin"),
            )
        )
        assert result["allow"] is False

    def test_long_resource_type_denied(self, evaluate_policy):
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="x" * 10000,
                effective_policies=policies_for_role("admin"),
            )
        )
        assert result["allow"] is False

    def test_long_user_id_denied(self, evaluate_policy):
        """Long user_id should not break self-scope checks."""
        policies = [
            allow_policy("user:read:self", ["user:read"], scope="self"),
        ]
        long_id = "u" * 10000
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="user",
                resource_id="other",
                user_id=long_id,
                effective_policies=policies,
            )
        )
        assert result["allow"] is False

    def test_long_matching_ids_allowed(self, evaluate_policy):
        """Long but matching IDs should still work for self-scope."""
        policies = [
            allow_policy("user:read:self", ["user:read"], scope="self"),
        ]
        long_id = "u" * 10000
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="user",
                resource_id=long_id,
                user_id=long_id,
                effective_policies=policies,
            )
        )
        assert result["allow"] is True


class TestUnicodeAndSpecialChars:
    """CHAOS-007: Unicode, null bytes, and special characters in fields."""

    @pytest.mark.parametrize(
        ("action", "resource_type"),
        [
            ("\u0000read", "workflow"),
            ("read", "\u0000workflow"),
            ("re\u0000ad", "workflow"),
        ],
        ids=["null-prefix-action", "null-prefix-resource", "null-mid-action"],
    )
    def test_null_bytes_denied(self, evaluate_policy, action: str, resource_type: str):
        result = evaluate_policy(
            build_authz_input(
                action=action,
                resource_type=resource_type,
                effective_policies=policies_for_role("admin"),
            )
        )
        assert result["allow"] is False

    @pytest.mark.parametrize(
        ("action", "resource_type"),
        [
            ("\u200bread", "workflow"),
            ("read", "work\u200bflow"),
            ("\u00e9ead", "workflow"),
        ],
        ids=["zwsp-action", "zwsp-resource", "accent-action"],
    )
    def test_unicode_injection_denied(self, evaluate_policy, action: str, resource_type: str):
        result = evaluate_policy(
            build_authz_input(
                action=action,
                resource_type=resource_type,
                effective_policies=policies_for_role("admin"),
            )
        )
        assert result["allow"] is False

    def test_newline_in_action_denied(self, evaluate_policy):
        result = evaluate_policy(
            build_authz_input(
                action="read\ndelete",
                resource_type="workflow",
                effective_policies=policies_for_role("admin"),
            )
        )
        assert result["allow"] is False

    def test_sql_injection_in_action_denied(self, evaluate_policy):
        result = evaluate_policy(
            build_authz_input(
                action="read' OR '1'='1",
                resource_type="workflow",
                effective_policies=policies_for_role("admin"),
            )
        )
        assert result["allow"] is False
