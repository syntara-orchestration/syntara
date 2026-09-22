"""Tests for PolicyStatementSchema field validators.

Tests cover:
- ``effect`` accepts ``allow`` and ``deny`` and nothing else
- deny-effect statements are limited to deny-eligible resource types (AAP-74620 / ANSTRAT-1750)
- ``scope`` accepts only the known scopes
"""

import pytest
from pydantic import ValidationError

from syntara.authz.schemas import PolicyStatementSchema


def _make_statement(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "effect": "allow",
        "actions": ["resource:read"],
        "scope": "any",
    }
    defaults.update(overrides)
    return defaults


class TestEffectValidator:
    """Tests for the effect field validator on PolicyStatementSchema."""

    def test_allow_is_accepted(self) -> None:
        stmt = PolicyStatementSchema(**_make_statement(effect="allow"))
        assert stmt.effect == "allow"

    def test_deny_is_accepted_for_eligible_resource(self) -> None:
        stmt = PolicyStatementSchema(**_make_statement(effect="deny", actions=["workflow_node:execute"]))
        assert stmt.effect == "deny"

    def test_deny_wildcard_is_accepted_for_eligible_resource(self) -> None:
        stmt = PolicyStatementSchema(**_make_statement(effect="deny", actions=["workflow_node:*"]))
        assert stmt.actions == ["workflow_node:*"]

    @pytest.mark.parametrize(
        "bad_effect",
        [
            "Deny",
            "Allow",
            "ALLOW",
            "banana",
            "",
        ],
    )
    def test_invalid_effect_is_rejected(self, bad_effect: str) -> None:
        with pytest.raises(ValidationError, match="Invalid effect"):
            PolicyStatementSchema(**_make_statement(effect=bad_effect))


class TestDenyEligibility:
    """Deny may only target resource types in the deny allowlist."""

    @pytest.mark.parametrize(
        "action",
        ["workflow:read", "policy:delete", "role-assignment:revoke", "user:update", "credential:use"],
    )
    def test_deny_on_ineligible_resource_is_rejected(self, action: str) -> None:
        with pytest.raises(ValidationError, match="Deny-effect statements may only target"):
            PolicyStatementSchema(**_make_statement(effect="deny", actions=[action]))

    def test_deny_mixing_eligible_and_ineligible_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="workflow:update"):
            PolicyStatementSchema(**_make_statement(effect="deny", actions=["workflow_node:write", "workflow:update"]))

    def test_allow_on_any_resource_is_unaffected(self) -> None:
        stmt = PolicyStatementSchema(**_make_statement(effect="allow", actions=["policy:delete"]))
        assert stmt.actions == ["policy:delete"]

    def test_deny_with_conditions_is_accepted(self) -> None:
        stmt = PolicyStatementSchema(
            **_make_statement(
                effect="deny",
                actions=["workflow_node:execute"],
                scope="project",
                conditions={"resource_labels": {"kind": "http_request"}},
            )
        )
        assert stmt.conditions == {"resource_labels": {"kind": "http_request"}}


class TestScopeValidator:
    """Tests for the scope field validator."""

    @pytest.mark.parametrize("scope", ["any", "self", "project", "own"])
    def test_valid_scopes(self, scope: str) -> None:
        assert PolicyStatementSchema(**_make_statement(scope=scope)).scope == scope

    def test_invalid_scope_rejected(self) -> None:
        with pytest.raises(ValidationError, match="scope must be one of"):
            PolicyStatementSchema(**_make_statement(scope="galaxy"))
