"""Project-name patterns: syntax validation, SQL LIKE translation and matching."""

import pytest

from syntara.authz.project_patterns import (
    project_pattern_matches,
    project_pattern_to_like,
    validate_project_pattern,
)
from syntara.core.constants import FieldLimits


@pytest.mark.parametrize("pattern", ["pay*", "*-prod", "team:*:ci", "a*b*c", "pay_*", "x*"])
def test_valid_patterns(pattern: str) -> None:
    assert validate_project_pattern(pattern) is None


@pytest.mark.parametrize(
    ("pattern", "message"),
    [
        ("payments", "must contain '*'"),
        ("*", "matches every project"),
        ("***", "matches every project"),
        ("pay%", "may only contain"),
        ("pay?", "may only contain"),
        ("pay *", "may only contain"),
        ("pay\\*", "may only contain"),
        ("", "may only contain"),
        ("p" * FieldLimits.NAME_MAX_LENGTH + "*", "at most"),
    ],
)
def test_invalid_patterns(pattern: str, message: str) -> None:
    error = validate_project_pattern(pattern)
    assert error is not None
    assert message in error


@pytest.mark.parametrize(
    ("name", "expected"),
    [("payments", True), ("payroll", True), ("pay", True), ("sandbox", False), ("Payments", False)],
)
def test_prefix_pattern_matches_case_sensitively(name: str, *, expected: bool) -> None:
    assert project_pattern_matches("pay*", name) is expected


def test_underscore_is_literal() -> None:
    assert project_pattern_matches("pay_*", "pay_ments") is True
    assert project_pattern_matches("pay_*", "payXments") is False


def test_wildcard_in_middle_and_suffix() -> None:
    assert project_pattern_matches("team-*-prod", "team-a-prod") is True
    assert project_pattern_matches("team-*-prod", "team-a-prod-old") is False
    assert project_pattern_matches("*-prod", "billing-prod") is True


@pytest.mark.parametrize(
    ("pattern", "like"),
    [
        ("pay*", "pay%"),
        ("pay_*", "pay\\_%"),
        ("a*b*", "a%b%"),
        ("team:*", "team:%"),
    ],
)
def test_like_translation_escapes_sql_wildcards(pattern: str, like: str) -> None:
    assert project_pattern_to_like(pattern) == like


def test_like_translation_escapes_percent_and_backslash_defensively() -> None:
    # Not valid pattern characters, but the translation must never widen a match.
    assert project_pattern_to_like("a%b\\*") == "a\\%b\\\\%"
