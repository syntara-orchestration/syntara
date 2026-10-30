"""Tests for PolicyStatementSchema field validators."""

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


@pytest.mark.parametrize("scope", ["any", "project"])
def test_eligible_deny_is_accepted(scope: str) -> None:
    statement = PolicyStatementSchema(**_make_statement(effect="deny", actions=["step_type:write"], scope=scope))
    assert statement.effect == "deny"


@pytest.mark.parametrize("actions", [["workflow:read"], ["step_type:*"], ["step_type:write", "policy:delete"], []])
def test_ineligible_deny_is_rejected(actions: list[str]) -> None:
    with pytest.raises(ValidationError, match="Deny-effect statements"):
        PolicyStatementSchema(**_make_statement(effect="deny", actions=actions))


@pytest.mark.parametrize("scope", ["self", "own"])
def test_ineligible_deny_scope_is_rejected(scope: str) -> None:
    with pytest.raises(ValidationError, match="scope 'any' or 'project'"):
        PolicyStatementSchema(**_make_statement(effect="deny", actions=["step_type:write"], scope=scope))
