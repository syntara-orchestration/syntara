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
            "deny",
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
