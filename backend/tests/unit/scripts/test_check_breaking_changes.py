"""Tests for backend/scripts/openapi/check-breaking-changes.py.

Covers version helpers, the breaking-change approval label, spec-change
detection, and the full main() gate (oasdiff is mocked).

Gate policy under test:
  * Every OpenAPI spec change must bump info.version (major/minor/patch).
  * Breaking changes are blocked in place unless the privileged
    ``breaking-change-approved`` label is present.
"""

from __future__ import annotations

import importlib
import json
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[3] / "scripts" / "openapi"
sys.path.insert(0, str(SCRIPT_DIR))

check_breaking = importlib.import_module("check-breaking-changes")
post_comment = importlib.import_module("post-breaking-changes-comment")

REQUIRED_JSON_FIELDS = (
    "has_breaking_changes",
    "breaking_changes",
    "all_changes",
    "has_changes",
    "version_bumped",
    "base_version",
    "head_version",
    "version_bump_type",
    "breaking_approved",
    "spec_path",
    "gate_code",
)


def _spec_yaml(version: str, *, description: str | None = None) -> str:
    extra = f"  description: {description}\n" if description else ""
    return f'openapi: "3.1.0"\ninfo:\n  title: Syntara API\n{extra}  version: {version}\npaths: {{}}\n'


def _write_spec(path: Path, version: str, *, description: str | None = None) -> None:
    path.write_text(_spec_yaml(version, description=description))


def _run_main(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    base_version: str,
    head_version: str,
    has_breaking: bool,
    changelog: str,
    pr_labels: str = "",
    extra_args: list[str] | None = None,
    head_description: str | None = None,
) -> tuple[int, dict[str, Any]]:
    """Invoke main() with mocked oasdiff and return (exit_code, json_result)."""
    base_spec = tmp_path / "base.yaml"
    head_spec = tmp_path / "head.yaml"
    output = tmp_path / "breaking-results.json"
    _write_spec(base_spec, base_version)
    _write_spec(head_spec, head_version, description=head_description)

    monkeypatch.setattr(
        check_breaking,
        "check_breaking_changes",
        lambda *_args, **_kwargs: (has_breaking, "removed GET /legacy" if has_breaking else ""),
    )
    monkeypatch.setattr(
        check_breaking,
        "get_all_changes",
        lambda *_args, **_kwargs: changelog,
    )

    argv = [
        "check-breaking-changes.py",
        "--base-spec",
        str(base_spec),
        "--head-spec",
        str(head_spec),
        "--spec-path",
        "backend/src/syntara/schemas/openapi.yaml",
        "--output",
        str(output),
        "--pr-labels",
        pr_labels,
    ]
    if extra_args:
        argv.extend(extra_args)

    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exc:
        check_breaking.main()

    raw = output.read_text() if output.exists() else ""
    is_text = extra_args is not None and "text" in extra_args
    result: dict[str, Any] = {} if is_text or not raw else json.loads(raw)
    return int(exc.value.code or 0), result


class TestExtractInfoVersion:
    """Tests for extract_info_version()."""

    def test_standard_yaml(self):
        content = textwrap.dedent("""\
            openapi: "3.1.0"
            info:
              title: Syntara API
              version: 1.0.0
            paths: {}
        """)
        assert check_breaking.extract_info_version(content) == "1.0.0"

    def test_quoted_version(self):
        content = textwrap.dedent("""\
            openapi: "3.1.0"
            info:
              title: Syntara API
              version: "2.1.0"
            paths: {}
        """)
        assert check_breaking.extract_info_version(content) == "2.1.0"

    def test_single_quoted_version(self):
        content = textwrap.dedent("""\
            openapi: "3.1.0"
            info:
              title: Test
              version: '0.1.0'
            paths: {}
        """)
        assert check_breaking.extract_info_version(content) == "0.1.0"

    def test_version_with_prerelease(self):
        content = textwrap.dedent("""\
            openapi: "3.1.0"
            info:
              title: Test
              version: 1.0.0-beta.1
            paths: {}
        """)
        assert check_breaking.extract_info_version(content) == "1.0.0-beta.1"

    def test_no_info_section(self):
        content = textwrap.dedent("""\
            openapi: "3.1.0"
            paths: {}
        """)
        assert check_breaking.extract_info_version(content) is None

    def test_no_version_in_info(self):
        content = textwrap.dedent("""\
            openapi: "3.1.0"
            info:
              title: Test
            paths: {}
        """)
        assert check_breaking.extract_info_version(content) is None

    def test_version_field_outside_info_ignored(self):
        content = textwrap.dedent("""\
            openapi: "3.1.0"
            info:
              title: Test
              version: 1.0.0
            components:
              schemas:
                Foo:
                  version: 99.0.0
        """)
        assert check_breaking.extract_info_version(content) == "1.0.0"

    def test_info_with_extra_fields_before_version(self):
        content = textwrap.dedent("""\
            openapi: "3.1.0"
            info:
              title: Syntara API
              description: Some description
              contact:
                name: Support
              version: 3.2.1
            paths: {}
        """)
        assert check_breaking.extract_info_version(content) == "3.2.1"


class TestParseSemver:
    """Tests for parse_semver()."""

    def test_basic(self):
        assert check_breaking.parse_semver("1.0.0") == (1, 0, 0)

    def test_with_prerelease(self):
        assert check_breaking.parse_semver("1.0.0-beta.1") == (1, 0, 0)

    def test_large_numbers(self):
        assert check_breaking.parse_semver("12.34.56") == (12, 34, 56)

    def test_invalid_format(self):
        assert check_breaking.parse_semver("not-a-version") is None

    def test_partial_version(self):
        assert check_breaking.parse_semver("1.0") is None

    def test_empty(self):
        assert check_breaking.parse_semver("") is None


class TestGetVersionBumpType:
    """Tests for get_version_bump_type()."""

    def test_major_bump(self):
        assert check_breaking.get_version_bump_type("1.0.0", "2.0.0") == "major"

    def test_minor_bump(self):
        assert check_breaking.get_version_bump_type("1.0.0", "1.1.0") == "minor"

    def test_patch_bump(self):
        assert check_breaking.get_version_bump_type("1.0.0", "1.0.1") == "patch"

    def test_no_bump(self):
        assert check_breaking.get_version_bump_type("1.0.0", "1.0.0") is None

    def test_major_with_minor_and_patch(self):
        assert check_breaking.get_version_bump_type("1.2.3", "2.0.0") == "major"

    def test_major_bump_resets_minor_patch(self):
        assert check_breaking.get_version_bump_type("1.5.3", "2.1.0") == "major"

    def test_minor_bump_with_patch_change(self):
        assert check_breaking.get_version_bump_type("1.0.5", "1.1.0") == "minor"

    def test_downgrade_returns_none(self):
        assert check_breaking.get_version_bump_type("2.0.0", "1.0.0") is None

    def test_minor_downgrade_returns_none(self):
        assert check_breaking.get_version_bump_type("1.5.0", "1.4.0") is None

    def test_unparseable_base(self):
        assert check_breaking.get_version_bump_type("bad", "1.0.0") is None

    def test_unparseable_head(self):
        assert check_breaking.get_version_bump_type("1.0.0", "bad") is None

    def test_prerelease_to_ga(self):
        assert check_breaking.get_version_bump_type("0.1.0", "1.0.0") == "major"


class TestCheckApprovalLabel:
    """Tests for check_approval_label()."""

    def test_empty_labels(self):
        assert check_breaking.check_approval_label("") is False

    def test_no_approval_label(self):
        assert check_breaking.check_approval_label("bug,enhancement") is False

    def test_approval_label_present(self):
        assert check_breaking.check_approval_label("bug,breaking-change-approved,enhancement") is True

    def test_approval_label_only(self):
        assert check_breaking.check_approval_label("breaking-change-approved") is True

    def test_case_insensitive(self):
        assert check_breaking.check_approval_label("BREAKING-CHANGE-APPROVED") is True

    def test_whitespace_handling(self):
        assert check_breaking.check_approval_label("bug, breaking-change-approved , fix") is True

    def test_partial_match_rejected(self):
        assert check_breaking.check_approval_label("not-breaking-change-approved-extra") is False


class TestSpecHasChanges:
    """Tests for spec_has_changes()."""

    def test_identical_content_no_changelog(self):
        spec = _spec_yaml("1.0.0")
        assert check_breaking.spec_has_changes(spec, spec, has_breaking=False, all_changes="") is False

    def test_identical_content_no_changes_text(self):
        spec = _spec_yaml("1.0.0")
        assert check_breaking.spec_has_changes(spec, spec, has_breaking=False, all_changes="No changes") is False

    def test_content_diff_without_oasdiff_output(self):
        base = _spec_yaml("1.0.0")
        head = _spec_yaml("1.0.0", description="tweaked")
        assert check_breaking.spec_has_changes(base, head, has_breaking=False, all_changes="") is True

    def test_breaking_always_counts(self):
        spec = _spec_yaml("1.0.0")
        assert check_breaking.spec_has_changes(spec, spec, has_breaking=True, all_changes="") is True

    def test_changelog_fallback_when_content_matches(self):
        spec = _spec_yaml("1.0.0")
        assert (
            check_breaking.spec_has_changes(spec, spec, has_breaking=False, all_changes="info [endpoint-added]") is True
        )


class TestEvaluateGate:
    """Policy decision tests (single source of truth for the gate)."""

    def _decide(
        self,
        *,
        has_breaking: bool = False,
        has_changes: bool = False,
        version_bumped: bool = False,
        breaking_approved: bool = False,
    ) -> Any:  # noqa: ANN401 - GateDecision comes from a dynamically imported (hyphenated) module
        return check_breaking.evaluate_gate(
            has_breaking=has_breaking,
            has_changes=has_changes,
            version_bumped=version_bumped,
            breaking_approved=breaking_approved,
        )

    def test_no_changes_allowed(self):
        decision = self._decide()
        assert decision.allowed is True
        assert decision.code == "ok"

    def test_breaking_no_label_blocked(self):
        decision = self._decide(has_breaking=True, has_changes=True, version_bumped=True)
        assert decision.allowed is False
        assert decision.code == "breaking_blocked"

    def test_breaking_no_label_blocked_even_without_bump(self):
        # Breaking-without-approval is the dominant reason regardless of bump state.
        decision = self._decide(has_breaking=True, has_changes=True, version_bumped=False)
        assert decision.allowed is False
        assert decision.code == "breaking_blocked"

    def test_breaking_approved_with_bump_allowed(self):
        decision = self._decide(
            has_breaking=True,
            has_changes=True,
            version_bumped=True,
            breaking_approved=True,
        )
        assert decision.allowed is True
        assert decision.code == "breaking_approved"

    def test_breaking_approved_without_bump_blocked(self):
        # Even an approved breaking change must bump info.version.
        decision = self._decide(
            has_breaking=True,
            has_changes=True,
            version_bumped=False,
            breaking_approved=True,
        )
        assert decision.allowed is False
        assert decision.code == "version_bump_required"

    def test_non_breaking_with_bump_allowed(self):
        decision = self._decide(has_changes=True, version_bumped=True)
        assert decision.allowed is True
        assert decision.code == "ok"

    def test_non_breaking_without_bump_blocked(self):
        decision = self._decide(has_changes=True, version_bumped=False)
        assert decision.allowed is False
        assert decision.code == "version_bump_required"


class TestMainGate:
    """End-to-end main() tests with mocked oasdiff."""

    def test_breaking_change_blocked_without_label(self, monkeypatch, tmp_path):
        code, result = _run_main(
            monkeypatch,
            tmp_path,
            base_version="1.0.0",
            head_version="2.0.0",
            has_breaking=True,
            changelog="removed GET /legacy",
        )
        assert code == 1
        assert result["has_breaking_changes"] is True
        assert result["breaking_approved"] is False
        assert result["gate_code"] == "breaking_blocked"
        assert result["spec_path"] == "backend/src/syntara/schemas/openapi.yaml"
        for field in REQUIRED_JSON_FIELDS:
            assert field in result, f"Missing required field: {field}"

    def test_breaking_change_with_approval_label(self, monkeypatch, tmp_path):
        code, result = _run_main(
            monkeypatch,
            tmp_path,
            base_version="1.0.0",
            head_version="1.0.1",
            has_breaking=True,
            changelog="removed GET /legacy",
            pr_labels="breaking-change-approved",
        )
        assert code == 0
        assert result["breaking_approved"] is True
        assert result["version_bumped"] is True
        assert result["gate_code"] == "breaking_approved"

    def test_breaking_change_approved_but_no_bump_blocked(self, monkeypatch, tmp_path):
        code, result = _run_main(
            monkeypatch,
            tmp_path,
            base_version="1.0.0",
            head_version="1.0.0",
            has_breaking=True,
            changelog="removed GET /legacy",
            pr_labels="breaking-change-approved",
        )
        assert code == 1
        assert result["breaking_approved"] is True
        assert result["version_bumped"] is False
        assert result["gate_code"] == "version_bump_required"

    def test_non_breaking_minor_bump_allowed(self, monkeypatch, tmp_path):
        code, result = _run_main(
            monkeypatch,
            tmp_path,
            base_version="1.0.0",
            head_version="1.1.0",
            has_breaking=False,
            changelog="info [endpoint-added] in API added GET /widgets",
            head_description="new endpoint",
        )
        assert code == 0
        assert result["has_changes"] is True
        assert result["version_bump_type"] == "minor"
        assert result["version_bumped"] is True
        assert result["gate_code"] == "ok"

    def test_non_breaking_patch_bump_allowed(self, monkeypatch, tmp_path):
        # Bump *type* is not enforced — any bump satisfies the gate for non-breaking changes.
        code, result = _run_main(
            monkeypatch,
            tmp_path,
            base_version="1.0.0",
            head_version="1.0.1",
            has_breaking=False,
            changelog="info [endpoint-added] in API added GET /widgets",
            head_description="new endpoint",
        )
        assert code == 0
        assert result["has_changes"] is True
        assert result["version_bump_type"] == "patch"
        assert result["gate_code"] == "ok"

    def test_non_breaking_no_bump_blocked(self, monkeypatch, tmp_path):
        code, result = _run_main(
            monkeypatch,
            tmp_path,
            base_version="1.0.0",
            head_version="1.0.0",
            has_breaking=False,
            changelog="info [endpoint-added] in API added GET /widgets",
            head_description="new endpoint",
        )
        assert code == 1
        assert result["has_changes"] is True
        assert result["version_bumped"] is False
        assert result["gate_code"] == "version_bump_required"

    def test_oasdiff_silent_content_change_requires_bump(self, monkeypatch, tmp_path):
        code, result = _run_main(
            monkeypatch,
            tmp_path,
            base_version="1.0.0",
            head_version="1.0.0",
            has_breaking=False,
            changelog="",
            head_description="metadata only",
        )
        assert code == 1
        assert result["has_changes"] is True
        assert result["gate_code"] == "version_bump_required"

    def test_no_changes(self, monkeypatch, tmp_path):
        code, result = _run_main(
            monkeypatch,
            tmp_path,
            base_version="1.0.0",
            head_version="1.0.0",
            has_breaking=False,
            changelog="",
        )
        assert code == 0
        assert result["has_breaking_changes"] is False
        assert result["has_changes"] is False
        assert result["version_bumped"] is False
        assert result["base_version"] == "1.0.0"
        assert result["head_version"] == "1.0.0"
        assert result["gate_code"] == "ok"
        for field in REQUIRED_JSON_FIELDS:
            assert field in result, f"Missing required field: {field}"

    def test_text_output_includes_spec_and_versions(self, monkeypatch, tmp_path):
        code, _result = _run_main(
            monkeypatch,
            tmp_path,
            base_version="1.0.0",
            head_version="1.0.0",
            has_breaking=True,
            changelog="removed GET /legacy",
            extra_args=["--format", "text"],
        )
        assert code == 1
        text = (tmp_path / "breaking-results.json").read_text()
        assert "backend/src/syntara/schemas/openapi.yaml" in text
        assert "1.0.0 -> 1.0.0" in text
        assert "BREAKING CHANGES DETECTED" in text
        assert "removed GET /legacy" in text


class TestFormatTextOutput:
    """Tests for _format_text_output()."""

    def test_non_breaking_with_bump(self):
        decision = check_breaking.GateDecision(
            allowed=True, code="ok", message="Non-breaking spec change with a version bump"
        )
        lines = check_breaking._format_text_output(
            has_breaking=False,
            breaking_output="",
            all_changes="some changes",
            decision=decision,
            base_version="1.0.0",
            head_version="1.0.1",
            version_bump_type="patch",
            spec_path="backend/src/syntara/schemas/openapi.yaml",
        )
        text = "\n".join(lines)
        assert "version bump" in text
        assert "1.0.0 -> 1.0.1" in text
        assert "backend/src/syntara/schemas/openapi.yaml" in text

    def test_breaking_blocked(self):
        decision = check_breaking.evaluate_gate(
            has_breaking=True,
            has_changes=True,
            version_bumped=True,
            breaking_approved=False,
        )
        lines = check_breaking._format_text_output(
            has_breaking=True,
            breaking_output="endpoint removed",
            all_changes="endpoint removed",
            decision=decision,
            base_version="1.0.0",
            head_version="1.1.0",
            version_bump_type="minor",
            spec_path="backend/src/syntara/schemas/openapi.yaml",
        )
        text = "\n".join(lines)
        assert "BREAKING CHANGES DETECTED" in text
        assert "BLOCKED" in text
        assert "breaking-change-approved" in text

    def test_breaking_approved(self):
        decision = check_breaking.evaluate_gate(
            has_breaking=True,
            has_changes=True,
            version_bumped=True,
            breaking_approved=True,
        )
        lines = check_breaking._format_text_output(
            has_breaking=True,
            breaking_output="field removed",
            all_changes="field removed",
            decision=decision,
            base_version="1.0.0",
            head_version="1.0.1",
            version_bump_type="patch",
            spec_path="backend/src/syntara/schemas/openapi.yaml",
        )
        text = "\n".join(lines)
        assert "ALLOWED" in text
        assert "breaking-change-approved" in text

    def test_version_bump_required_message(self):
        decision = check_breaking.evaluate_gate(
            has_breaking=False,
            has_changes=True,
            version_bumped=False,
            breaking_approved=False,
        )
        lines = check_breaking._format_text_output(
            has_breaking=False,
            breaking_output="",
            all_changes="info [endpoint-added]",
            decision=decision,
            base_version="1.0.0",
            head_version="1.0.0",
            version_bump_type=None,
            spec_path="backend/src/syntara/schemas/openapi.yaml",
        )
        text = "\n".join(lines)
        assert "BLOCKED" in text
        assert "info.version" in text


class TestPostBreakingChangesComment:
    """Tests for PR comment formatting of the gate outcomes."""

    def test_blocked_breaking_includes_spec_and_versions(self):
        comment = post_comment.format_breaking_changes_comment(
            {
                "has_breaking_changes": True,
                "breaking_changes": "removed GET /legacy",
                "all_changes": "removed GET /legacy",
                "base_version": "1.0.0",
                "head_version": "1.1.0",
                "version_bump_type": "minor",
                "breaking_approved": False,
                "spec_path": "backend/src/syntara/schemas/openapi.yaml",
                "gate_code": "breaking_blocked",
            },
            "syntara-orchestration",
            "syntara",
        )
        assert "backend/src/syntara/schemas/openapi.yaml" in comment
        assert "1.0.0" in comment
        assert "removed GET /legacy" in comment
        assert "Blocked" in comment
        assert "breaking-change-approved" in comment

    def test_approved_breaking_comment(self):
        comment = post_comment.format_breaking_changes_comment(
            {
                "has_breaking_changes": True,
                "breaking_changes": "removed GET /legacy",
                "all_changes": "removed GET /legacy",
                "base_version": "1.0.0",
                "head_version": "1.0.1",
                "version_bump_type": "patch",
                "breaking_approved": True,
                "spec_path": "backend/src/syntara/schemas/openapi.yaml",
                "gate_code": "breaking_approved",
            },
            "syntara-orchestration",
            "syntara",
        )
        assert "Approved Override" in comment
        assert "breaking-change-approved" in comment

    def test_version_bump_required_comment(self):
        comment = post_comment.format_breaking_changes_comment(
            {
                "has_breaking_changes": False,
                "breaking_changes": "",
                "all_changes": "info [endpoint-added]",
                "base_version": "1.0.0",
                "head_version": "1.0.0",
                "version_bump_type": None,
                "breaking_approved": False,
                "spec_path": "backend/src/syntara/schemas/openapi.yaml",
                "gate_code": "version_bump_required",
            },
            "syntara-orchestration",
            "syntara",
        )
        assert "Version Bump Required" in comment
        assert "info.version" in comment
