"""Tests for backend/scripts/openapi/check-breaking-changes.py.

Covers version helpers, the breaking-change approval label, canonical
spec-change detection, bump-segment classification, and the full main() gate
(oasdiff is mocked except in the explicitly-integration tests).

Gate policy under test:
  * Every *meaningful* OpenAPI spec change must bump info.version. Comparison is
    canonical, so serialization-only diffs (whitespace, key order, quotes) do
    not require a bump.
  * The bump segment must match the change type: minor for additive changes,
    patch for spec-only edits. A wrong-segment bump is blocked.
  * Breaking changes are blocked in place unless the privileged
    ``breaking-change-approved`` label is present AND the bump is a minor.
"""

from __future__ import annotations

import importlib
import json
import shutil
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
    "expected_bump_type",
    "breaking_approved",
    "spec_path",
    "gate_code",
)

# A representative structural (additive) changelog entry as oasdiff emits it.
ADDITIVE_ENTRY = {"id": "endpoint-added", "text": "endpoint added", "level": 1}


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
    changelog_entries: list[dict[str, Any]] | None = None,
    pr_labels: str = "",
    extra_args: list[str] | None = None,
    head_description: str | None = None,
    base_spec_text: str | None = None,
    head_spec_text: str | None = None,
) -> tuple[int, dict[str, Any]]:
    """Invoke main() with mocked oasdiff and return (exit_code, json_result).

    ``has_meaningful_change`` uses the real canonical comparison of the written
    base/head files, so control it via ``head_description`` (spec-only diff) or
    explicit ``base_spec_text`` / ``head_spec_text`` overrides. ``has_breaking``
    and ``changelog_entries`` are mocked to drive the breaking/segment logic.
    """
    base_spec = tmp_path / "base.yaml"
    head_spec = tmp_path / "head.yaml"
    output = tmp_path / "breaking-results.json"
    if base_spec_text is not None:
        base_spec.write_text(base_spec_text)
    else:
        _write_spec(base_spec, base_version)
    if head_spec_text is not None:
        head_spec.write_text(head_spec_text)
    else:
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
    monkeypatch.setattr(
        check_breaking,
        "get_changelog_entries",
        lambda *_args, **_kwargs: (changelog_entries if changelog_entries is not None else []),
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


class TestCanonicalizeSpec:
    """Tests for canonicalize_spec()."""

    def test_parses_and_strips_info_version(self):
        ok, data = check_breaking.canonicalize_spec(_spec_yaml("1.0.0"))
        assert ok is True
        assert "version" not in data["info"]

    def test_none_content(self):
        ok, data = check_breaking.canonicalize_spec("")
        assert ok is True
        assert data is None

    def test_invalid_yaml_reports_not_ok(self):
        ok, data = check_breaking.canonicalize_spec("key: [unterminated")
        assert ok is False
        assert data is None


class TestHasMeaningfulChange:
    """Tests for has_meaningful_change() (canonical comparison)."""

    def test_identical_content(self):
        spec = _spec_yaml("1.0.0")
        assert check_breaking.has_meaningful_change(spec, spec, has_breaking=False) is False

    def test_version_only_change_is_not_meaningful(self):
        # A bare version bump with no other diff is not a "meaningful" change.
        base = _spec_yaml("1.0.0")
        head = _spec_yaml("1.1.0")
        assert check_breaking.has_meaningful_change(base, head, has_breaking=False) is False

    def test_description_change_is_meaningful(self):
        base = _spec_yaml("1.0.0")
        head = _spec_yaml("1.0.0", description="tweaked")
        assert check_breaking.has_meaningful_change(base, head, has_breaking=False) is True

    def test_serialization_only_diff_is_not_meaningful(self):
        # Same data, different quote style / key order / whitespace.
        base = 'openapi: "3.1.0"\ninfo:\n  title: Syntara API\n  version: 1.0.0\npaths: {}\n'
        head = "info:\n  version: 1.0.0\n  title: 'Syntara API'\n\nopenapi: '3.1.0'\npaths: {}\n"
        assert check_breaking.has_meaningful_change(base, head, has_breaking=False) is False

    def test_breaking_always_counts(self):
        spec = _spec_yaml("1.0.0")
        assert check_breaking.has_meaningful_change(spec, spec, has_breaking=True) is True

    def test_unparseable_falls_back_to_raw_compare(self):
        base = "key: [unterminated"
        head = "key: [unterminated  "
        assert check_breaking.has_meaningful_change(base, head, has_breaking=False) is True


class TestClassifyExpectedSegment:
    """Tests for classify_expected_segment()."""

    def test_no_change(self):
        segment = check_breaking.classify_expected_segment(has_breaking=False, has_changes=False, changelog_entries=[])
        assert segment is None

    def test_additive_change_expects_minor(self):
        segment = check_breaking.classify_expected_segment(
            has_breaking=False, has_changes=True, changelog_entries=[ADDITIVE_ENTRY]
        )
        assert segment == "minor"

    def test_spec_only_change_expects_patch(self):
        # Canonical diff exists but oasdiff reports no structural entries.
        segment = check_breaking.classify_expected_segment(has_breaking=False, has_changes=True, changelog_entries=[])
        assert segment == "patch"

    def test_breaking_change_expects_minor(self):
        segment = check_breaking.classify_expected_segment(has_breaking=True, has_changes=True, changelog_entries=[])
        assert segment == "minor"


class TestEvaluateGate:
    """Policy decision tests (single source of truth for the gate)."""

    def _decide(
        self,
        *,
        has_breaking: bool = False,
        has_changes: bool = False,
        version_bump_type: str | None = None,
        expected_bump_type: str | None = None,
        breaking_approved: bool = False,
    ) -> Any:  # noqa: ANN401 - GateDecision comes from a dynamically imported (hyphenated) module
        return check_breaking.evaluate_gate(
            has_breaking=has_breaking,
            has_changes=has_changes,
            version_bump_type=version_bump_type,
            expected_bump_type=expected_bump_type,
            breaking_approved=breaking_approved,
        )

    def test_no_changes_allowed(self):
        decision = self._decide()
        assert decision.allowed is True
        assert decision.code == "ok"

    def test_breaking_no_label_blocked(self):
        decision = self._decide(
            has_breaking=True, has_changes=True, version_bump_type="minor", expected_bump_type="minor"
        )
        assert decision.allowed is False
        assert decision.code == "breaking_blocked"

    def test_breaking_no_label_blocked_even_without_bump(self):
        # Breaking-without-approval is the dominant reason regardless of bump state.
        decision = self._decide(has_breaking=True, has_changes=True, expected_bump_type="minor")
        assert decision.allowed is False
        assert decision.code == "breaking_blocked"

    def test_breaking_approved_with_minor_bump_allowed(self):
        decision = self._decide(
            has_breaking=True,
            has_changes=True,
            version_bump_type="minor",
            expected_bump_type="minor",
            breaking_approved=True,
        )
        assert decision.allowed is True
        assert decision.code == "breaking_approved"

    def test_breaking_approved_with_major_bump_blocked(self):
        # An approved in-place breaking change must be a minor bump, not major.
        decision = self._decide(
            has_breaking=True,
            has_changes=True,
            version_bump_type="major",
            expected_bump_type="minor",
            breaking_approved=True,
        )
        assert decision.allowed is False
        assert decision.code == "wrong_bump_segment"

    def test_breaking_approved_without_bump_blocked(self):
        decision = self._decide(
            has_breaking=True,
            has_changes=True,
            version_bump_type=None,
            expected_bump_type="minor",
            breaking_approved=True,
        )
        assert decision.allowed is False
        assert decision.code == "version_bump_required"

    def test_additive_with_minor_allowed(self):
        decision = self._decide(has_changes=True, version_bump_type="minor", expected_bump_type="minor")
        assert decision.allowed is True
        assert decision.code == "ok"

    def test_additive_with_patch_blocked(self):
        decision = self._decide(has_changes=True, version_bump_type="patch", expected_bump_type="minor")
        assert decision.allowed is False
        assert decision.code == "wrong_bump_segment"

    def test_spec_only_with_patch_allowed(self):
        decision = self._decide(has_changes=True, version_bump_type="patch", expected_bump_type="patch")
        assert decision.allowed is True
        assert decision.code == "ok"

    def test_spec_only_with_minor_blocked(self):
        decision = self._decide(has_changes=True, version_bump_type="minor", expected_bump_type="patch")
        assert decision.allowed is False
        assert decision.code == "wrong_bump_segment"

    def test_change_without_bump_blocked(self):
        decision = self._decide(has_changes=True, version_bump_type=None, expected_bump_type="minor")
        assert decision.allowed is False
        assert decision.code == "version_bump_required"


class TestMainGate:
    """End-to-end main() tests with mocked oasdiff."""

    def test_breaking_change_blocked_without_label(self, monkeypatch, tmp_path):
        code, result = _run_main(
            monkeypatch,
            tmp_path,
            base_version="1.0.0",
            head_version="1.1.0",
            has_breaking=True,
            changelog="removed GET /legacy",
            head_description="breaking edit",
        )
        assert code == 1
        assert result["has_breaking_changes"] is True
        assert result["breaking_approved"] is False
        assert result["gate_code"] == "breaking_blocked"
        assert result["spec_path"] == "backend/src/syntara/schemas/openapi.yaml"
        for field in REQUIRED_JSON_FIELDS:
            assert field in result, f"Missing required field: {field}"

    def test_breaking_change_with_approval_label_minor_bump(self, monkeypatch, tmp_path):
        code, result = _run_main(
            monkeypatch,
            tmp_path,
            base_version="1.0.0",
            head_version="1.1.0",
            has_breaking=True,
            changelog="removed GET /legacy",
            head_description="approved breaking edit",
            pr_labels="breaking-change-approved",
        )
        assert code == 0
        assert result["breaking_approved"] is True
        assert result["version_bumped"] is True
        assert result["expected_bump_type"] == "minor"
        assert result["gate_code"] == "breaking_approved"

    def test_breaking_change_approved_but_major_bump_blocked(self, monkeypatch, tmp_path):
        code, result = _run_main(
            monkeypatch,
            tmp_path,
            base_version="1.0.0",
            head_version="2.0.0",
            has_breaking=True,
            changelog="removed GET /legacy",
            head_description="approved breaking edit",
            pr_labels="breaking-change-approved",
        )
        assert code == 1
        assert result["version_bump_type"] == "major"
        assert result["expected_bump_type"] == "minor"
        assert result["gate_code"] == "wrong_bump_segment"

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

    def test_additive_minor_bump_allowed(self, monkeypatch, tmp_path):
        code, result = _run_main(
            monkeypatch,
            tmp_path,
            base_version="1.0.0",
            head_version="1.1.0",
            has_breaking=False,
            changelog="info [endpoint-added] in API added GET /widgets",
            changelog_entries=[ADDITIVE_ENTRY],
            head_description="new endpoint",
        )
        assert code == 0
        assert result["has_changes"] is True
        assert result["version_bump_type"] == "minor"
        assert result["expected_bump_type"] == "minor"
        assert result["gate_code"] == "ok"

    def test_additive_patch_bump_wrong_segment_blocked(self, monkeypatch, tmp_path):
        code, result = _run_main(
            monkeypatch,
            tmp_path,
            base_version="1.0.0",
            head_version="1.0.1",
            has_breaking=False,
            changelog="info [endpoint-added] in API added GET /widgets",
            changelog_entries=[ADDITIVE_ENTRY],
            head_description="new endpoint",
        )
        assert code == 1
        assert result["version_bump_type"] == "patch"
        assert result["expected_bump_type"] == "minor"
        assert result["gate_code"] == "wrong_bump_segment"

    def test_spec_only_patch_bump_allowed(self, monkeypatch, tmp_path):
        # Description-only edit: oasdiff reports no structural entries -> expects patch.
        code, result = _run_main(
            monkeypatch,
            tmp_path,
            base_version="1.0.0",
            head_version="1.0.1",
            has_breaking=False,
            changelog="",
            changelog_entries=[],
            head_description="clarified wording",
        )
        assert code == 0
        assert result["has_changes"] is True
        assert result["version_bump_type"] == "patch"
        assert result["expected_bump_type"] == "patch"
        assert result["gate_code"] == "ok"

    def test_spec_only_minor_bump_wrong_segment_blocked(self, monkeypatch, tmp_path):
        code, result = _run_main(
            monkeypatch,
            tmp_path,
            base_version="1.0.0",
            head_version="1.1.0",
            has_breaking=False,
            changelog="",
            changelog_entries=[],
            head_description="clarified wording",
        )
        assert code == 1
        assert result["version_bump_type"] == "minor"
        assert result["expected_bump_type"] == "patch"
        assert result["gate_code"] == "wrong_bump_segment"

    def test_meaningful_change_no_bump_blocked(self, monkeypatch, tmp_path):
        code, result = _run_main(
            monkeypatch,
            tmp_path,
            base_version="1.0.0",
            head_version="1.0.0",
            has_breaking=False,
            changelog="info [endpoint-added] in API added GET /widgets",
            changelog_entries=[ADDITIVE_ENTRY],
            head_description="new endpoint",
        )
        assert code == 1
        assert result["has_changes"] is True
        assert result["version_bumped"] is False
        assert result["gate_code"] == "version_bump_required"

    def test_serialization_only_change_passes_without_bump(self, monkeypatch, tmp_path):
        base = 'openapi: "3.1.0"\ninfo:\n  title: Syntara API\n  version: 1.0.0\npaths: {}\n'
        # Same data, reordered keys and different quote style, no version bump.
        head = "info:\n  version: 1.0.0\n  title: 'Syntara API'\nopenapi: '3.1.0'\npaths: {}\n"
        code, result = _run_main(
            monkeypatch,
            tmp_path,
            base_version="1.0.0",
            head_version="1.0.0",
            has_breaking=False,
            changelog="",
            changelog_entries=[],
            base_spec_text=base,
            head_spec_text=head,
        )
        assert code == 0
        assert result["has_changes"] is False
        assert result["version_bumped"] is False
        assert result["gate_code"] == "ok"

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
        assert result["expected_bump_type"] is None
        assert result["gate_code"] == "ok"
        for field in REQUIRED_JSON_FIELDS:
            assert field in result, f"Missing required field: {field}"

    def test_new_spec_on_base_ref_skips_gate(self, monkeypatch, tmp_path):
        # A new major version introduced as a new spec at a new path has no base
        # to compare against, so the gate does not fire (exit 0, no output).
        monkeypatch.setattr(check_breaking, "get_spec_from_git", lambda *_a, **_k: None)
        output = tmp_path / "breaking-results.json"
        argv = [
            "check-breaking-changes.py",
            "--base",
            "origin/devel",
            "--head",
            "HEAD",
            "--spec-path",
            "backend/src/syntara/schemas/v2/openapi.yaml",
            "--output",
            str(output),
        ]
        monkeypatch.setattr(sys, "argv", argv)
        with pytest.raises(SystemExit) as exc:
            check_breaking.main()
        assert int(exc.value.code or 0) == 0
        assert not output.exists()

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
        assert "version_bumped: false" in text
        assert "BREAKING CHANGES DETECTED" in text
        assert "removed GET /legacy" in text

    def test_json_failure_emits_text_error_on_stderr(self, monkeypatch, tmp_path, capsys):
        # CI writes JSON to --output; the job log must still name spec, versions,
        # version_bumped, and the breaking changes.
        code, result = _run_main(
            monkeypatch,
            tmp_path,
            base_version="1.0.0",
            head_version="1.1.0",
            has_breaking=True,
            changelog="removed GET /legacy",
            head_description="breaking edit",
        )
        assert code == 1
        assert result["version_bumped"] is True
        err = capsys.readouterr().err
        assert "backend/src/syntara/schemas/openapi.yaml" in err
        assert "1.0.0 -> 1.1.0" in err
        assert "version_bumped: true" in err
        assert "removed GET /legacy" in err


_INTEGRATION_BASE = textwrap.dedent("""\
    openapi: "3.1.0"
    info:
      title: Test API
      version: 1.0.0
    paths:
      /things:
        get:
          operationId: list_things
          summary: List things
          responses:
            '200':
              description: ok
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      labels:
                        type: object
                        additionalProperties:
                          type: string
""")

# Same as base but the additionalProperties (dynamic-map) schema changed, plus a patch bump.
_INTEGRATION_DYNAMIC_MAP = textwrap.dedent("""\
    openapi: "3.1.0"
    info:
      title: Test API
      version: 1.0.1
    paths:
      /things:
        get:
          operationId: list_things
          summary: List things
          responses:
            '200':
              description: ok
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      labels:
                        type: object
                        additionalProperties: true
""")

# Base plus a new endpoint (additive) with only a patch bump (wrong segment).
_INTEGRATION_ADDITIVE = textwrap.dedent("""\
    openapi: "3.1.0"
    info:
      title: Test API
      version: 1.0.1
    paths:
      /things:
        get:
          operationId: list_things
          summary: List things
          responses:
            '200':
              description: ok
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      labels:
                        type: object
                        additionalProperties:
                          type: string
      /gadgets:
        get:
          operationId: list_gadgets
          summary: List gadgets
          responses:
            '200':
              description: ok
""")


@pytest.mark.skipif(shutil.which("oasdiff") is None, reason="oasdiff not installed")
class TestOasdiffIntegration:
    """Integration tests exercising the real oasdiff binary."""

    def _run(self, monkeypatch, tmp_path, base: str, head: str, *, pr_labels: str = "") -> tuple[int, dict[str, Any]]:
        base_spec = tmp_path / "base.yaml"
        head_spec = tmp_path / "head.yaml"
        output = tmp_path / "breaking-results.json"
        base_spec.write_text(base)
        head_spec.write_text(head)
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
        monkeypatch.setattr(sys, "argv", argv)
        with pytest.raises(SystemExit) as exc:
            check_breaking.main()
        return int(exc.value.code or 0), json.loads(output.read_text())

    def test_dynamic_map_content_change_not_breaking(self, monkeypatch, tmp_path):
        # Changing an additionalProperties (dynamic-map) field is not breaking.
        code, result = self._run(monkeypatch, tmp_path, _INTEGRATION_BASE, _INTEGRATION_DYNAMIC_MAP)
        assert result["has_breaking_changes"] is False
        assert result["has_changes"] is True
        # oasdiff reports no structural entry -> treated as a patch-level edit.
        assert result["expected_bump_type"] == "patch"
        assert code == 0
        assert result["gate_code"] == "ok"

    def test_additive_endpoint_requires_minor(self, monkeypatch, tmp_path):
        code, result = self._run(monkeypatch, tmp_path, _INTEGRATION_BASE, _INTEGRATION_ADDITIVE)
        assert result["has_breaking_changes"] is False
        assert result["expected_bump_type"] == "minor"
        # Patch bump for an additive change is the wrong segment.
        assert code == 1
        assert result["gate_code"] == "wrong_bump_segment"


class TestFormatTextOutput:
    """Tests for _format_text_output()."""

    def test_non_breaking_with_bump(self):
        decision = check_breaking.GateDecision(
            allowed=True, code="ok", message="Non-breaking spec change with a correct 'patch' version bump"
        )
        lines = check_breaking._format_text_output(
            has_breaking=False,
            breaking_output="",
            all_changes="some changes",
            decision=decision,
            base_version="1.0.0",
            head_version="1.0.1",
            version_bumped=True,
            version_bump_type="patch",
            expected_bump_type="patch",
            spec_path="backend/src/syntara/schemas/openapi.yaml",
        )
        text = "\n".join(lines)
        assert "version bump" in text
        assert "1.0.0 -> 1.0.1" in text
        assert "version_bumped: true" in text
        assert "backend/src/syntara/schemas/openapi.yaml" in text

    def test_breaking_blocked(self):
        decision = check_breaking.evaluate_gate(
            has_breaking=True,
            has_changes=True,
            version_bump_type="minor",
            expected_bump_type="minor",
            breaking_approved=False,
        )
        lines = check_breaking._format_text_output(
            has_breaking=True,
            breaking_output="endpoint removed",
            all_changes="endpoint removed",
            decision=decision,
            base_version="1.0.0",
            head_version="1.1.0",
            version_bumped=True,
            version_bump_type="minor",
            expected_bump_type="minor",
            spec_path="backend/src/syntara/schemas/openapi.yaml",
        )
        text = "\n".join(lines)
        assert "BREAKING CHANGES DETECTED" in text
        assert "BLOCKED" in text
        assert "breaking-change-approved" in text
        assert "version_bumped: true" in text

    def test_wrong_bump_segment(self):
        decision = check_breaking.evaluate_gate(
            has_breaking=False,
            has_changes=True,
            version_bump_type="patch",
            expected_bump_type="minor",
            breaking_approved=False,
        )
        lines = check_breaking._format_text_output(
            has_breaking=False,
            breaking_output="",
            all_changes="added GET /widgets",
            decision=decision,
            base_version="1.0.0",
            head_version="1.0.1",
            version_bumped=True,
            version_bump_type="patch",
            expected_bump_type="minor",
            spec_path="backend/src/syntara/schemas/openapi.yaml",
        )
        text = "\n".join(lines)
        assert "BLOCKED" in text
        assert "minor" in text
        assert "Expected bump: minor" in text
        assert "version_bumped: true" in text

    def test_version_bump_required_message(self):
        decision = check_breaking.evaluate_gate(
            has_breaking=False,
            has_changes=True,
            version_bump_type=None,
            expected_bump_type="minor",
            breaking_approved=False,
        )
        lines = check_breaking._format_text_output(
            has_breaking=False,
            breaking_output="",
            all_changes="info [endpoint-added]",
            decision=decision,
            base_version="1.0.0",
            head_version="1.0.0",
            version_bumped=False,
            version_bump_type=None,
            expected_bump_type="minor",
            spec_path="backend/src/syntara/schemas/openapi.yaml",
        )
        text = "\n".join(lines)
        assert "BLOCKED" in text
        assert "info.version" in text
        assert "version_bumped: false" in text


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
                "expected_bump_type": "minor",
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
        assert "**version_bumped:** `true`" in comment

    def test_approved_breaking_comment(self):
        comment = post_comment.format_breaking_changes_comment(
            {
                "has_breaking_changes": True,
                "breaking_changes": "removed GET /legacy",
                "all_changes": "removed GET /legacy",
                "base_version": "1.0.0",
                "head_version": "1.1.0",
                "version_bump_type": "minor",
                "expected_bump_type": "minor",
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
                "expected_bump_type": "minor",
                "breaking_approved": False,
                "spec_path": "backend/src/syntara/schemas/openapi.yaml",
                "gate_code": "version_bump_required",
            },
            "syntara-orchestration",
            "syntara",
        )
        assert "Version Bump Required" in comment
        assert "info.version" in comment
        assert "minor" in comment
        assert "**version_bumped:** `false`" in comment

    def test_wrong_bump_segment_comment(self):
        comment = post_comment.format_breaking_changes_comment(
            {
                "has_breaking_changes": False,
                "breaking_changes": "",
                "all_changes": "added GET /widgets",
                "base_version": "1.0.0",
                "head_version": "1.0.1",
                "version_bump_type": "patch",
                "expected_bump_type": "minor",
                "breaking_approved": False,
                "spec_path": "backend/src/syntara/schemas/openapi.yaml",
                "gate_code": "wrong_bump_segment",
            },
            "syntara-orchestration",
            "syntara",
        )
        assert "Wrong Version Bump Segment" in comment
        assert "minor" in comment
        assert "patch" in comment
        assert "**version_bumped:** `true`" in comment


REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = Path(__file__).resolve().parents[3]
LABEL_GUARD_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "breaking-change-label-guard.yml"


class TestAckPathRemoved:
    """The breaking-change-ack PR-body override must not remain as a bypass."""

    def test_check_breaking_changes_has_no_pr_body_flag(self):
        source = Path(check_breaking.__file__).read_text()
        assert "--pr-body" not in source
        assert "breaking-change-ack" not in source

    def test_makefile_does_not_pass_pr_body_to_breaking_check(self):
        makefile = (BACKEND_ROOT / "Makefile").read_text()
        assert "--pr-body" not in makefile


class TestBreakingChangeLabelGuard:
    """Contract tests for unauthorized label application being removed.

    The guard is a pull_request_target GitHub Action (inline JS, no PR code
    executed). These tests lock the workflow to: verify syntara-leads
    membership, and on failure remove the label, comment, and fail the check.
    """

    def test_workflow_exists(self):
        assert LABEL_GUARD_WORKFLOW.is_file()

    def test_triggers_on_label_added(self):
        text = LABEL_GUARD_WORKFLOW.read_text()
        assert "pull_request_target:" in text
        assert "types: [labeled]" in text
        assert "github.event.label.name == 'breaking-change-approved'" in text

    def test_verifies_syntara_leads_membership(self):
        text = LABEL_GUARD_WORKFLOW.read_text()
        assert "syntara-leads" in text
        assert "getMembershipForUserInOrg" in text
        assert "res.data.state === 'active'" in text

    def test_unauthorized_application_removed(self):
        text = LABEL_GUARD_WORKFLOW.read_text()
        assert "issues.removeLabel" in text
        assert "issues.createComment" in text
        assert "core.setFailed" in text
        assert "label has been removed" in text

    def test_fails_closed_without_org_token(self):
        text = LABEL_GUARD_WORKFLOW.read_text()
        assert "SYNTARA_LEADS_READ_TOKEN" in text
        assert "secrets.GITHUB_TOKEN" in text
        assert "isMember = false" in text


class TestOpenapiBreakingChangesWorkflow:
    """The CI job must surface spec, versions, and version_bumped on failure."""

    def test_prints_results_json_on_failure(self):
        workflow = REPO_ROOT / ".github" / "workflows" / "openapi-breaking-changes.yml"
        text = workflow.read_text()
        assert "Show breaking-change results on failure" in text
        assert "cat breaking-results.json" in text
        assert "version_bumped" in text
        assert "--pr-labels" in text
        assert "breaking-change-ack" not in text
