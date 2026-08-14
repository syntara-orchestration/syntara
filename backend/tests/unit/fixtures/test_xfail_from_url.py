"""Unit tests for the xfail-from-url pytest plugin's pure logic."""

from __future__ import annotations

import pytest

from tests.fixtures.xfail_from_url import _matches, _parse_xfail_entries


class TestParseXfailEntries:
    """Tests for _parse_xfail_entries."""

    def test_single_heading_with_reason(self) -> None:
        content = "# tests/unit/test_foo.py\nflaky on CI"
        assert _parse_xfail_entries(content) == [("tests/unit/test_foo.py", "flaky on CI")]

    def test_multiple_headings(self) -> None:
        content = "# pattern-one\nreason one\n\n# pattern-two\nreason two"
        assert _parse_xfail_entries(content) == [
            ("pattern-one", "reason one"),
            ("pattern-two", "reason two"),
        ]

    def test_default_reason_when_body_empty(self) -> None:
        content = "# some-pattern\n"
        assert _parse_xfail_entries(content) == [("some-pattern", "listed in xfail list")]

    def test_joins_multi_line_reason(self) -> None:
        content = "# pattern\nline one\nline two"
        assert _parse_xfail_entries(content) == [("pattern", "line one line two")]

    def test_skips_blank_lines_in_reason(self) -> None:
        content = "# pattern\nfirst\n\nsecond"
        assert _parse_xfail_entries(content) == [("pattern", "first second")]

    def test_trims_whitespace_from_headings(self) -> None:
        content = "#   spaced-pattern  \nreason"
        assert _parse_xfail_entries(content) == [("spaced-pattern", "reason")]

    def test_no_headings_returns_empty(self) -> None:
        assert _parse_xfail_entries("just some text\nno headings here") == []

    def test_empty_string_returns_empty(self) -> None:
        assert _parse_xfail_entries("") == []

    def test_ignores_non_h1_headings(self) -> None:
        content = "## h2 heading\ntext\n### h3 heading\nmore text"
        assert _parse_xfail_entries(content) == []


class TestMatches:
    """Tests for _matches."""

    def test_prefix_match_directory(self) -> None:
        assert _matches("tests/unit/test_foo.py::test_bar", "tests/unit/") is True

    def test_prefix_match_file(self) -> None:
        assert _matches("tests/unit/test_foo.py::test_bar", "tests/unit/test_foo.py") is True

    def test_prefix_no_match(self) -> None:
        assert _matches("tests/unit/test_foo.py::test_bar", "tests/integration/") is False

    def test_exact_match_with_node_id(self) -> None:
        assert _matches("tests/unit/test_foo.py::test_bar", "tests/unit/test_foo.py::test_bar") is True

    def test_exact_match_rejects_partial(self) -> None:
        assert _matches("tests/unit/test_foo.py::test_bar", "tests/unit/test_foo.py::test_baz") is False

    @pytest.mark.parametrize(
        ("nodeid", "pattern"),
        [
            ("tests/unit/test_foo.py::TestClass::test_method", "tests/unit/test_foo.py::TestClass::test_method"),
            ("tests/unit/test_foo.py::test_bar", "tests/unit/"),
            ("tests/unit/test_foo.py::test_bar", "tests/"),
        ],
    )
    def test_various_valid_matches(self, nodeid: str, pattern: str) -> None:
        assert _matches(nodeid, pattern) is True

    @pytest.mark.parametrize(
        ("nodeid", "pattern"),
        [
            ("tests/unit/test_foo.py::test_bar", "tests/unit/test_foo.py::test_other"),
            ("tests/unit/test_foo.py::test_bar", "tests/integration/test_foo.py"),
            ("tests/unit/test_foo.py::test_bar", "tests/unit/test_foo.py::test_bar_extended"),
        ],
    )
    def test_various_non_matches(self, nodeid: str, pattern: str) -> None:
        assert _matches(nodeid, pattern) is False
