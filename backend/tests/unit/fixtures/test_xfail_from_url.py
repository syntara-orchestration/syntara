"""Unit tests for the xfail-from-url pytest plugin's pure logic."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.fixtures.xfail_from_url import (
    _matches,
    _parse_xfail_entries,
    pytest_collection_modifyitems,
    pytest_report_header,
)

if TYPE_CHECKING:
    from pathlib import Path


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


class TestMatchesParametrized:
    """A pattern that lists the base node-id must match parametrized instances.

    Mirrors pytest's own node-id selection semantics, where
    ``test_foo.py::test_bar`` selects every ``test_bar[...]`` variant. Without
    this, a flaky parametrized test quarantined by its base id is *not* marked
    xfail and fails the suite (the reported bug).
    """

    @pytest.mark.parametrize(
        ("nodeid", "pattern"),
        [
            # base function id must match a single parametrization
            ("tests/unit/test_foo.py::test_bar[case-1]", "tests/unit/test_foo.py::test_bar"),
            # ... and match regardless of which parametrization it is
            ("tests/unit/test_foo.py::test_bar[case-2]", "tests/unit/test_foo.py::test_bar"),
            # base id with a class-scoped parametrized method
            ("tests/unit/test_foo.py::TestC::test_m[a-b]", "tests/unit/test_foo.py::TestC::test_m"),
            # a class base id must match its (non-parametrized) methods
            ("tests/unit/test_foo.py::TestC::test_m", "tests/unit/test_foo.py::TestC"),
            # a class base id must match its parametrized methods
            ("tests/unit/test_foo.py::TestC::test_m[a-b]", "tests/unit/test_foo.py::TestC"),
            # an exact parametrized id still matches itself
            ("tests/unit/test_foo.py::test_bar[case-1]", "tests/unit/test_foo.py::test_bar[case-1]"),
        ],
    )
    def test_base_id_matches_parametrized_instances(self, nodeid: str, pattern: str) -> None:
        assert _matches(nodeid, pattern) is True

    @pytest.mark.parametrize(
        ("nodeid", "pattern"),
        [
            # a base id must not match a different function sharing a prefix
            ("tests/unit/test_foo.py::test_bar_extended", "tests/unit/test_foo.py::test_bar"),
            # ... nor a differently-named parametrized function sharing a prefix
            ("tests/unit/test_foo.py::test_bard[x]", "tests/unit/test_foo.py::test_bar"),
            # a class base id must not match a differently-named class sharing a prefix
            ("tests/unit/test_foo.py::TestCandidate::test_m", "tests/unit/test_foo.py::TestC"),
        ],
    )
    def test_base_id_does_not_over_match(self, nodeid: str, pattern: str) -> None:
        assert _matches(nodeid, pattern) is False


class _FakeItem:
    """Minimal stand-in for a collected pytest item."""

    def __init__(self, nodeid: str) -> None:
        self.nodeid = nodeid
        self.markers: list[pytest.MarkDecorator] = []

    def add_marker(self, marker: pytest.MarkDecorator) -> None:
        self.markers.append(marker)


class _FakeConfig:
    def __init__(self, source: str | None) -> None:
        self._source = source
        self.stash = pytest.Stash()

    def getoption(self, name: str) -> str | None:
        assert name == "--xfail-from-url"
        return self._source


class TestCollectionModifyItems:
    """End-to-end: the collection hook marks the right items xfail.

    This is the behavior the bug report is about — a quarantined test must not
    fail the suite. Here we assert the hook actually attaches an xfail marker to
    the matching items (including a parametrized instance listed by base id).
    """

    def test_parametrized_instance_marked_by_base_id(self, tmp_path: Path) -> None:
        md = tmp_path / "backend.md"
        md.write_text("# tests/unit/test_foo.py::test_bar\nflaky under load\n")

        param_item = _FakeItem("tests/unit/test_foo.py::test_bar[case-1]")
        unrelated_item = _FakeItem("tests/unit/test_foo.py::test_other")
        items = [param_item, unrelated_item]

        pytest_collection_modifyitems(_FakeConfig(str(md)), items)  # type: ignore[arg-type]

        assert len(param_item.markers) == 1
        assert param_item.markers[0].name == "xfail"
        assert "flaky under load" in param_item.markers[0].kwargs["reason"]
        assert unrelated_item.markers == []

    def test_no_source_is_a_noop(self) -> None:
        item = _FakeItem("tests/unit/test_foo.py::test_bar[case-1]")
        items = [item]
        pytest_collection_modifyitems(_FakeConfig(None), items)  # type: ignore[arg-type]
        assert item.markers == []


class TestReportHeader:
    """The active xfail rules are surfaced at the start of the run."""

    def test_header_lists_every_rule(self, tmp_path: Path) -> None:
        md = tmp_path / "backend.md"
        md.write_text(
            "# tests/unit/test_foo.py::test_bar\nflaky under load\n\n# tests/integration/\ninfra flaky\n",
        )

        header = pytest_report_header(_FakeConfig(str(md)))  # type: ignore[arg-type]

        assert header is not None
        joined = "\n".join(header)
        assert "2 rule(s)" in joined
        assert "tests/unit/test_foo.py::test_bar" in joined
        assert "flaky under load" in joined
        assert "tests/integration/" in joined
        assert "infra flaky" in joined

    def test_header_is_absent_without_source(self) -> None:
        assert pytest_report_header(_FakeConfig(None)) is None  # type: ignore[arg-type]
