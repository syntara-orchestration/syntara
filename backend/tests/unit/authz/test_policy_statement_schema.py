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


class TestDenyEligibilityValidator:
    """Tests for the deny-eligibility model validator on PolicyStatementSchema."""

    def test_deny_on_step_type_write_is_accepted(self) -> None:
        stmt = PolicyStatementSchema(**_make_statement(effect="deny", actions=["step_type:write"], scope="project"))
        assert stmt.effect == "deny"

    @pytest.mark.parametrize(
        "actions",
        [
            ["workflow:read"],
            ["policy:delete"],
            ["role-assignment:revoke"],
            ["step_type:*"],
            ["step_type:read"],
            ["step_type:write", "workflow:read"],
            [],
        ],
    )
    def test_deny_outside_step_type_write_is_rejected(self, actions: list[str]) -> None:
        with pytest.raises(ValidationError, match="Deny effect is only allowed on 'step_type:write'"):
            PolicyStatementSchema(**_make_statement(effect="deny", actions=actions))

    def test_allow_outside_step_type_write_is_untouched(self) -> None:
        """The eligibility guard only constrains deny statements."""
        stmt = PolicyStatementSchema(**_make_statement(effect="allow", actions=["workflow:read"]))
        assert stmt.effect == "allow"
