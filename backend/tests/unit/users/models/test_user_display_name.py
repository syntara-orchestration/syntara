"""Tests for User.display_name and empty first_name persistence on the model."""

from uuid import uuid4

from syntara.core.models import User


def test_display_name_combines_first_and_last() -> None:
    user = User(id=uuid4(), username="jdoe", first_name="Jane", last_name="Doe")
    assert user.display_name == "Jane Doe"


def test_display_name_first_name_only() -> None:
    user = User(id=uuid4(), username="jane", first_name="Jane")
    assert user.display_name == "Jane"


def test_display_name_skips_empty_first_name() -> None:
    user = User(id=uuid4(), username="jdoe", first_name="", last_name="Doe")
    assert user.display_name == "Doe"


def test_display_name_skips_whitespace_first_name() -> None:
    user = User(id=uuid4(), username="jdoe", first_name="   ", last_name="Doe")
    assert user.display_name == "Doe"


def test_display_name_falls_back_to_username_when_both_names_blank() -> None:
    user = User(id=uuid4(), username="jdoe", first_name="")
    assert user.display_name == "jdoe"


def test_display_name_falls_back_to_username_when_names_are_whitespace() -> None:
    user = User(id=uuid4(), username="jdoe", first_name="   ", last_name="  ")
    assert user.display_name == "jdoe"


def test_display_name_strips_whitespace_around_names() -> None:
    user = User(id=uuid4(), username="jdoe", first_name=" Jane ", last_name=" Doe ")
    assert user.display_name == "Jane Doe"


def test_user_model_accepts_empty_first_name() -> None:
    user = User(id=uuid4(), username="jdoe", first_name="")
    assert user.first_name == ""
