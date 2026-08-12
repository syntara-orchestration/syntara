"""Unit tests for password validation (API-46, AAP-79855).

Tests the InfoSec password requirements:
- Minimum 14 characters
- At least 3 of 4 character classes (digits, uppercase, lowercase, punctuation/spaces/other)
"""

import pytest
from pydantic import ValidationError

from syntara.auth.passwords import validate_password_complexity
from syntara.core.models.user_schemas import UserCreate, UserUpdate


class TestPasswordValidation:
    """Test password validation rules for API-46."""

    def test_password_too_short_rejected(self) -> None:
        """Test passwords under 14 characters are rejected."""
        with pytest.raises(ValidationError, match="at least 14"):
            UserCreate(
                username="testuser",
                first_name="Test",
                last_name="User",
                password="Short123!",  # Only 9 characters  # noqa: S106
            )

    def test_password_only_lowercase_rejected(self) -> None:
        """Test password with only lowercase (1 class) is rejected."""
        with pytest.raises(ValidationError, match=r"at least 3.*character classes"):
            UserCreate(
                username="testuser",
                first_name="Test",
                last_name="User",
                password="lowercasepasswordonly",  # 21 chars but only 1 class  # noqa: S106
            )

    def test_password_two_classes_rejected(self) -> None:
        """Test password with only 2 character classes is rejected."""
        with pytest.raises(ValidationError, match=r"at least 3.*character classes"):
            UserCreate(
                username="testuser",
                first_name="Test",
                last_name="User",
                password="lowercaseonly123456",  # Only lowercase + digits (2 classes)  # noqa: S106
            )

    def test_password_three_classes_upper_lower_digit_accepted(self) -> None:
        """Test password with uppercase + lowercase + digits (3 classes) is accepted."""
        user = UserCreate(
            username="testuser",
            first_name="Test",
            last_name="User",
            password="ValidPassword123",  # Uppercase + lowercase + digits  # noqa: S106
        )
        assert user.username == "testuser"

    def test_password_three_classes_lower_digit_special_accepted(self) -> None:
        """Test password with lowercase + digits + special (3 classes) is accepted."""
        user = UserCreate(
            username="testuser",
            first_name="Test",
            last_name="User",
            password="validpassword123!@#",  # Lowercase + digits + special  # noqa: S106
        )
        assert user.username == "testuser"

    def test_password_three_classes_upper_digit_special_accepted(self) -> None:
        """Test password with uppercase + digits + special (3 classes) is accepted."""
        user = UserCreate(
            username="testuser",
            first_name="Test",
            last_name="User",
            password="VALIDPASSWORD123!",  # Uppercase + digits + special  # noqa: S106
        )
        assert user.username == "testuser"

    def test_password_three_classes_upper_lower_special_accepted(self) -> None:
        """Test password with uppercase + lowercase + special (3 classes) is accepted."""
        user = UserCreate(
            username="testuser",
            first_name="Test",
            last_name="User",
            password="ValidPassword!@#$",  # Uppercase + lowercase + special  # noqa: S106
        )
        assert user.username == "testuser"

    def test_password_four_classes_accepted(self) -> None:
        """Test password with all 4 character classes is accepted."""
        user = UserCreate(
            username="testuser",
            first_name="Test",
            last_name="User",
            password="ValidPassword123!",  # All 4 classes  # noqa: S106
        )
        assert user.username == "testuser"

    def test_password_with_spaces_accepted(self) -> None:
        """Test password can contain spaces (counts as punctuation/other class)."""
        user = UserCreate(
            username="testuser",
            first_name="Test",
            last_name="User",
            password="Valid Password 123",  # Uppercase + lowercase + digits + space  # noqa: S106
        )
        assert user.username == "testuser"

    def test_password_exactly_14_chars_three_classes_accepted(self) -> None:
        """Test minimum length boundary: exactly 14 characters with 3 classes."""
        user = UserCreate(
            username="testuser",
            first_name="Test",
            last_name="User",
            password="ValidPass123!!",  # Exactly 14 chars: upper + lower + digit + special  # noqa: S106
        )
        assert user.username == "testuser"

    def test_password_various_special_characters_accepted(self) -> None:
        """Test various special characters are recognized."""
        special_chars = '!@#$%^&*(),.?":{}|<>'
        password = f"ValidPassword{special_chars}"  # Mix of classes
        user = UserCreate(
            username="testuser",
            first_name="Test",
            last_name="User",
            password=password,
        )
        assert user.username == "testuser"


class TestUserUpdatePasswordValidation:
    """Test password validation on UserUpdate (AAP-79855)."""

    def test_weak_password_too_short_rejected(self) -> None:
        with pytest.raises(ValidationError, match="at least 14"):
            UserUpdate(password="Short123!")  # noqa: S106

    def test_weak_password_insufficient_classes_rejected(self) -> None:
        with pytest.raises(ValidationError, match=r"at least 3.*character classes"):
            UserUpdate(password="lowercasepasswordonly")  # noqa: S106

    def test_strong_password_accepted(self) -> None:
        update = UserUpdate(password="ValidPassword123!")  # noqa: S106
        assert update.password is not None

    def test_none_password_accepted(self) -> None:
        update = UserUpdate(password=None)
        assert update.password is None

    def test_omitted_password_accepted(self) -> None:
        update = UserUpdate(first_name="Updated")
        assert update.password is None


class TestValidatePasswordComplexity:
    """Test the shared validate_password_complexity function."""

    def test_valid_password(self) -> None:
        validate_password_complexity("ValidPassword123!")

    def test_too_short_raises(self) -> None:
        with pytest.raises(ValueError, match="at least 14"):
            validate_password_complexity("Short1!")

    def test_insufficient_classes_raises(self) -> None:
        with pytest.raises(ValueError, match="at least 3"):
            validate_password_complexity("lowercasepasswordonly")
