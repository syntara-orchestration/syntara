"""Unit tests for CredentialListParams — covers the for_action field."""

import pytest
from pydantic import ValidationError

from syntara.credentials.models.query_params import CredentialListParams


class TestCredentialListParams:  # noqa: D101
    def test_for_action_defaults_to_none(self) -> None:
        params = CredentialListParams()
        assert params.for_action is None

    def test_for_action_accepts_use(self) -> None:
        params = CredentialListParams(for_action="use")
        assert params.for_action == "use"

    @pytest.mark.parametrize("invalid", ["read", "create", ""])
    def test_for_action_rejects_unsupported_values(self, invalid: str) -> None:
        with pytest.raises(ValidationError):
            CredentialListParams.model_validate({"for_action": invalid})
