"""Tests for backend/scripts/openapi/check-breaking-changes.py.

Covers version helpers, acknowledgment, CVE labels, bump-type matching,
and the full main() gate (oasdiff is mocked).
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
    "acknowledged",
    "justification",
    "ack_insufficient",
    "version_bumped",
    "base_version",
    "head_version",
    "version_bump_type",
    "cve_approved",
    "spec_path",
    "change_kind",
    "gate_code",
)


def _spec_yaml(version: str) -> str:
    return textwrap.dedent(f"""\
        openapi: "3.1.0"
        info:
          title: Syntara API
          version: {version}
        paths: {{}}
    """)


def _write_spec(path: Path, version: str) -> None:
    path.write_text(_spec_yaml(version))


def _run_main(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    base_version: str,
    head_version: str,
    has_breaking: bool,
    changelog: str,
    pr_body: str = "",
    pr_labels: str = "",
    extra_args: list[str] | None = None,
) -> tuple[int, dict[str, Any]]:
    """Invoke main() with mocked oasdiff and return (exit_code, json_result)."""
    base_spec = tmp_path / "base.yaml"
    head_spec = tmp_path / "head.yaml"
    output = tmp_path / "breaking-results.json"
    _write_spec(base_spec, base_version)
    _write_spec(head_spec, head_version)

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
        "--pr-body",
        pr_body,
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
    return int(exc.value.code), result


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


class TestCheckAcknowledgment:
    """Tests for check_acknowledgment()."""

    def test_no_pr_body(self):
        result = check_breaking.check_acknowledgment("")
        assert result["acknowledged"] is False
        assert result["justification"] == ""
        assert result["ack_insufficient"] is False

    def test_no_ack_in_body(self):
        result = check_breaking.check_acknowledgment("This is a normal PR description")
        assert result["acknowledged"] is False

    def test_valid_ack(self):
        body = "Some text\nbreaking-change-ack: This change is necessary for the v2 field rename migration\nMore text"
        result = check_breaking.check_acknowledgment(body)
        assert result["acknowledged"] is True
        assert "v2 field rename" in result["justification"]
        assert result["ack_insufficient"] is False

    def test_insufficient_ack(self):
        body = "breaking-change-ack: too short"
        result = check_breaking.check_acknowledgment(body)
        assert result["acknowledged"] is False
        assert result["ack_insufficient"] is True
        assert result["justification"] == "too short"

    def test_case_insensitive(self):
        body = "Breaking-Change-Ack: This is a sufficiently long justification for the change"
        result = check_breaking.check_acknowledgment(body)
        assert result["acknowledged"] is True

    def test_colon_with_spaces(self):
        body = "breaking-change-ack :   This is a sufficiently long justification text here"
        result = check_breaking.check_acknowledgment(body)
        assert result["acknowledged"] is True

    def test_exactly_20_chars(self):
        body = "breaking-change-ack: 12345678901234567890"
        result = check_breaking.check_acknowledgment(body)
        assert result["acknowledged"] is True

    def test_19_chars_insufficient(self):
        body = "breaking-change-ack: 1234567890123456789"
        result = check_breaking.check_acknowledgment(body)
        assert result["acknowledged"] is False
        assert result["ack_insufficient"] is True


class TestCheckCveLabel:
    """Tests for check_cve_label()."""

    def test_empty_labels(self):
        assert check_breaking.check_cve_label("") is False

    def test_no_cve_label(self):
        assert check_breaking.check_cve_label("bug,enhancement") is False

    def test_cve_label_present(self):
        assert check_breaking.check_cve_label("bug,cve-breaking-change-approved,enhancement") is True

    def test_cve_label_only(self):
        assert check_breaking.check_cve_label("cve-breaking-change-approved") is True

    def test_case_insensitive(self):
        assert check_breaking.check_cve_label("CVE-BREAKING-CHANGE-APPROVED") is True

    def test_whitespace_handling(self):
        assert check_breaking.check_cve_label("bug, cve-breaking-change-approved , fix") is True

    def test_partial_match_rejected(self):
        assert check_breaking.check_cve_label("not-cve-breaking-change-approved-extra") is False


class TestClassifyNonBreakingChanges:
    """Tests for classify_non_breaking_changes()."""

    def test_empty_is_none(self):
        assert check_breaking.classify_non_breaking_changes("") == "none"

    def test_no_changes_text_is_none(self):
        assert check_breaking.classify_non_breaking_changes("No changes") == "none"

    def test_endpoint_added_id_is_additive(self):
        changelog = "info\t[endpoint-added] at paths/widgets.yaml\n\tin API added GET /widgets"
        assert check_breaking.classify_non_breaking_changes(changelog) == "additive"

    def test_request_property_added_is_additive(self):
        changelog = "info [request-property-added] added the optional request property 'nickname'"
        assert check_breaking.classify_non_breaking_changes(changelog) == "additive"

    def test_description_change_is_other(self):
        changelog = "info [endpoint-description-changed] updated description of GET /widgets"
        assert check_breaking.classify_non_breaking_changes(changelog) == "other"


class TestEvaluateGate:
    """Policy decision tests (single source of truth for the gate)."""

    def _decide(
        self,
        *,
        has_breaking: bool = False,
        version_bump_type: str | None = None,
        acknowledged: bool = False,
        ack_insufficient: bool = False,
        justification: str = "",
        cve_approved: bool = False,
        change_kind: str = "none",
    ) -> check_breaking.GateDecision:
        return check_breaking.evaluate_gate(
            has_breaking=has_breaking,
            version_bump_type=version_bump_type,
            acknowledged=acknowledged,
            ack_insufficient=ack_insufficient,
            justification=justification,
            cve_approved=cve_approved,
            change_kind=change_kind,
        )

    def test_no_changes_allowed(self):
        decision = self._decide()
        assert decision.allowed is True
        assert decision.code == "ok"

    def test_breaking_blocked(self):
        decision = self._decide(has_breaking=True)
        assert decision.allowed is False
        assert decision.code == "breaking_blocked"

    def test_breaking_ack_without_major_blocked(self):
        decision = self._decide(has_breaking=True, acknowledged=True, version_bump_type=None)
        assert decision.allowed is False
        assert decision.code == "ack_without_major"

    def test_breaking_minor_bump_ack_blocked(self):
        decision = self._decide(has_breaking=True, acknowledged=True, version_bump_type="minor")
        assert decision.allowed is False
        assert decision.code == "ack_without_major"

    def test_breaking_major_bump_with_ack_allowed(self):
        decision = self._decide(
            has_breaking=True,
            acknowledged=True,
            version_bump_type="major",
            justification="Routing the field rename to /api/v2/",
        )
        assert decision.allowed is True
        assert decision.code == "major_ack"

    def test_breaking_cve_escape_hatch_allowed(self):
        decision = self._decide(has_breaking=True, cve_approved=True)
        assert decision.allowed is True
        assert decision.code == "cve_override"

    def test_additive_minor_bump_allowed(self):
        decision = self._decide(change_kind="additive", version_bump_type="minor")
        assert decision.allowed is True

    def test_additive_patch_bump_blocked(self):
        decision = self._decide(change_kind="additive", version_bump_type="patch")
        assert decision.allowed is False
        assert decision.code == "incorrect_bump"

    def test_additive_no_bump_allowed(self):
        decision = self._decide(change_kind="additive", version_bump_type=None)
        assert decision.allowed is True

    def test_other_patch_bump_allowed(self):
        decision = self._decide(change_kind="other", version_bump_type="patch")
        assert decision.allowed is True

    def test_major_bump_without_breaking_blocked(self):
        decision = self._decide(change_kind="other", version_bump_type="major")
        assert decision.allowed is False
        assert decision.code == "incorrect_bump"


class TestMainGate:
    """End-to-end main() tests with mocked oasdiff."""

    def test_breaking_change_blocked_even_with_ack(self, monkeypatch, tmp_path):
        code, result = _run_main(
            monkeypatch,
            tmp_path,
            base_version="1.0.0",
            head_version="1.0.0",
            has_breaking=True,
            changelog="removed GET /legacy",
            pr_body="breaking-change-ack: This is a sufficiently long justification text",
        )
        assert code == 1
        assert result["has_breaking_changes"] is True
        assert result["acknowledged"] is True
        assert result["version_bumped"] is False
        assert result["base_version"] == "1.0.0"
        assert result["head_version"] == "1.0.0"
        assert result["gate_code"] == "ack_without_major"
        assert result["spec_path"] == "backend/src/syntara/schemas/openapi.yaml"
        for field in REQUIRED_JSON_FIELDS:
            assert field in result, f"Missing required field: {field}"

    def test_breaking_change_with_cve_escape_hatch(self, monkeypatch, tmp_path):
        code, result = _run_main(
            monkeypatch,
            tmp_path,
            base_version="1.0.0",
            head_version="1.0.0",
            has_breaking=True,
            changelog="removed GET /legacy",
            pr_labels="cve-breaking-change-approved",
        )
        assert code == 0
        assert result["cve_approved"] is True
        assert result["gate_code"] == "cve_override"
        assert result["version_bumped"] is False

    def test_breaking_change_major_bump_and_ack(self, monkeypatch, tmp_path):
        code, result = _run_main(
            monkeypatch,
            tmp_path,
            base_version="1.0.0",
            head_version="2.0.0",
            has_breaking=True,
            changelog="removed GET /legacy",
            pr_body="breaking-change-ack: Routing the rename to a new /api/v2/ spec",
        )
        assert code == 0
        assert result["version_bump_type"] == "major"
        assert result["gate_code"] == "major_ack"

    def test_non_breaking_correct_minor_bump(self, monkeypatch, tmp_path):
        code, result = _run_main(
            monkeypatch,
            tmp_path,
            base_version="1.0.0",
            head_version="1.1.0",
            has_breaking=False,
            changelog="info [endpoint-added] in API added GET /widgets",
        )
        assert code == 0
        assert result["change_kind"] == "additive"
        assert result["version_bump_type"] == "minor"
        assert result["version_bumped"] is True
        assert result["gate_code"] == "ok"

    def test_non_breaking_incorrect_patch_bump_for_additive(self, monkeypatch, tmp_path):
        code, result = _run_main(
            monkeypatch,
            tmp_path,
            base_version="1.0.0",
            head_version="1.0.1",
            has_breaking=False,
            changelog="info [endpoint-added] in API added GET /widgets",
        )
        assert code == 1
        assert result["change_kind"] == "additive"
        assert result["version_bump_type"] == "patch"
        assert result["gate_code"] == "incorrect_bump"
        assert result["has_breaking_changes"] is False

    def test_non_breaking_no_bump_allowed(self, monkeypatch, tmp_path):
        code, result = _run_main(
            monkeypatch,
            tmp_path,
            base_version="1.0.0",
            head_version="1.0.0",
            has_breaking=False,
            changelog="info [endpoint-added] in API added GET /widgets",
        )
        assert code == 0
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
        assert result["change_kind"] == "none"
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

    def test_no_breaking_changes(self):
        decision = check_breaking.GateDecision(allowed=True, code="ok", message="No breaking changes detected")
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
        assert "No breaking changes detected" in text
        assert "1.0.0 -> 1.0.1" in text
        assert "backend/src/syntara/schemas/openapi.yaml" in text

    def test_breaking_blocked(self):
        decision = check_breaking.evaluate_gate(
            has_breaking=True,
            version_bump_type=None,
            acknowledged=False,
            ack_insufficient=False,
            justification="",
            cve_approved=False,
            change_kind="none",
        )
        lines = check_breaking._format_text_output(
            has_breaking=True,
            breaking_output="endpoint removed",
            all_changes="endpoint removed",
            decision=decision,
            base_version="1.0.0",
            head_version="1.0.0",
            version_bump_type=None,
            spec_path="backend/src/syntara/schemas/openapi.yaml",
        )
        text = "\n".join(lines)
        assert "BREAKING CHANGES DETECTED" in text
        assert "BLOCKED" in text
        assert "cve-breaking-change-approved" in text

    def test_breaking_cve_approved(self):
        decision = check_breaking.evaluate_gate(
            has_breaking=True,
            version_bump_type=None,
            acknowledged=False,
            ack_insufficient=False,
            justification="",
            cve_approved=True,
            change_kind="none",
        )
        lines = check_breaking._format_text_output(
            has_breaking=True,
            breaking_output="field removed",
            all_changes="field removed",
            decision=decision,
            base_version="1.0.0",
            head_version="1.0.0",
            version_bump_type=None,
            spec_path="backend/src/syntara/schemas/openapi.yaml",
        )
        text = "\n".join(lines)
        assert "ALLOWED: CVE escape hatch" in text

    def test_breaking_major_bump_ack(self):
        decision = check_breaking.evaluate_gate(
            has_breaking=True,
            version_bump_type="major",
            acknowledged=True,
            ack_insufficient=False,
            justification="Routing to v2 for the field rename",
            cve_approved=False,
            change_kind="none",
        )
        lines = check_breaking._format_text_output(
            has_breaking=True,
            breaking_output="endpoint renamed",
            all_changes="endpoint renamed",
            decision=decision,
            base_version="1.0.0",
            head_version="2.0.0",
            version_bump_type="major",
            spec_path="backend/src/syntara/schemas/openapi.yaml",
        )
        text = "\n".join(lines)
        assert "ALLOWED: Major version bump" in text

    def test_incorrect_bump_message(self):
        decision = check_breaking.evaluate_gate(
            has_breaking=False,
            version_bump_type="patch",
            acknowledged=False,
            ack_insufficient=False,
            justification="",
            cve_approved=False,
            change_kind="additive",
        )
        lines = check_breaking._format_text_output(
            has_breaking=False,
            breaking_output="",
            all_changes="info [endpoint-added]",
            decision=decision,
            base_version="1.0.0",
            head_version="1.0.1",
            version_bump_type="patch",
            spec_path="backend/src/syntara/schemas/openapi.yaml",
        )
        text = "\n".join(lines)
        assert "BLOCKED" in text
        assert "minor version bump" in text


class TestPostBreakingChangesComment:
    """Tests for PR comment formatting of the new gate outcomes."""

    def test_blocked_breaking_includes_spec_and_versions(self):
        comment = post_comment.format_breaking_changes_comment(
            {
                "has_breaking_changes": True,
                "breaking_changes": "removed GET /legacy",
                "all_changes": "removed GET /legacy",
                "acknowledged": False,
                "ack_insufficient": False,
                "justification": "",
                "base_version": "1.0.0",
                "head_version": "1.0.0",
                "version_bump_type": None,
                "cve_approved": False,
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

    def test_incorrect_bump_comment(self):
        comment = post_comment.format_breaking_changes_comment(
            {
                "has_breaking_changes": False,
                "breaking_changes": "",
                "all_changes": "info [endpoint-added]",
                "acknowledged": False,
                "ack_insufficient": False,
                "justification": "",
                "base_version": "1.0.0",
                "head_version": "1.0.1",
                "version_bump_type": "patch",
                "cve_approved": False,
                "spec_path": "backend/src/syntara/schemas/openapi.yaml",
                "gate_code": "incorrect_bump",
                "change_kind": "additive",
            },
            "syntara-orchestration",
            "syntara",
        )
        assert "Incorrect Version Bump" in comment
        assert "minor" in comment.lower()
