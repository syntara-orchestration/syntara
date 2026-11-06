"""Assertions for API UserReference objects ({id, name})."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from syntara.core.models import User


def assert_user_reference(value: object, user: User) -> None:
    """Assert *value* is a UserReference JSON object for *user*."""
    assert isinstance(value, dict), f"expected UserReference object, got {type(value).__name__}: {value!r}"
    assert value["id"] == str(user.id)
    assert value["name"] == user.display_name
