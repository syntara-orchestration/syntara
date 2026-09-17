"""Tests for optional first_name on UserCreate."""

import pytest
from pydantic import SecretStr, ValidationError

from syntara.core.constants import FieldLimits
from syntara.core.models.user_schemas import UserCreate

_VALID_PASSWORD = SecretStr("ValidPassword123!")


class TestUserCreateFirstNameOptional:
    """POST /users should accept omitted, null, or empty first_name."""

    def test_omitted_first_name_defaults_to_none(self) -> None:
        user = UserCreate(username="testuser", password=_VALID_PASSWORD)
        assert user.first_name is None

    def test_null_first_name_accepted(self) -> None:
        user = UserCreate(username="testuser", password=_VALID_PASSWORD, first_name=None)
        assert user.first_name is None

    def test_empty_first_name_accepted(self) -> None:
        user = UserCreate(username="testuser", password=_VALID_PASSWORD, first_name="")
        assert user.first_name == ""

    def test_first_name_still_accepted(self) -> None:
        user = UserCreate(username="testuser", password=_VALID_PASSWORD, first_name="Ada")
        assert user.first_name == "Ada"

    def test_first_name_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError, match="at most"):
            UserCreate(
                username="testuser",
                password=_VALID_PASSWORD,
                first_name="x" * (FieldLimits.NAME_MAX_LENGTH + 1),
            )
