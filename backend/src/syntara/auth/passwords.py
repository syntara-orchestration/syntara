"""Password hashing and validation utilities."""

import re

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

MIN_PASSWORD_LENGTH = 14
MIN_CHARACTER_CLASSES = 3

_ph = PasswordHasher()


def validate_password_complexity(password: str) -> None:
    """Validate password meets InfoSec security requirements.

    Raises ``ValueError`` if the password is too short or lacks sufficient
    character-class diversity.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        msg = f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
        raise ValueError(msg)

    character_classes = 0
    if re.search(r"\d", password):
        character_classes += 1
    if re.search(r"[A-Z]", password):
        character_classes += 1
    if re.search(r"[a-z]", password):
        character_classes += 1
    if re.search(r"[^a-zA-Z0-9]", password):
        character_classes += 1

    if character_classes < MIN_CHARACTER_CLASSES:
        msg = (
            "Password must contain at least 3 of the following character classes: "
            "digits (0-9), uppercase letters (A-Z), lowercase letters (a-z), "
            "punctuation/spaces/other characters"
        )
        raise ValueError(msg)


def hash_password(plain: str) -> str:
    """Hash a plaintext password with Argon2id.

    Args:
        plain: The plaintext password.

    Returns:
        The Argon2id hash string.

    """
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against an Argon2id hash.

    Args:
        plain: The plaintext password to check.
        hashed: The stored Argon2id hash.

    Returns:
        True if the password matches.

    """
    try:
        return _ph.verify(hashed, plain)
    except VerifyMismatchError:
        return False
