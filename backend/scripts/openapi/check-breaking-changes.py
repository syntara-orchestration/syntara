#!/usr/bin/env python3
"""Check OpenAPI spec for breaking changes using oasdiff.

This script compares two OpenAPI specs and detects breaking changes,
returning structured JSON output for consumption by CI or local tooling.

The gate enforces these rules (per the AO REST API Versioning and Deprecation
Policy):

  1. Every *meaningful* OpenAPI spec change MUST bump ``info.version``.
     Comparison is **canonical** (semantic): the two specs are parsed and
     compared as data structures, so serialization-only diffs (whitespace,
     indentation, line endings, key order, quote style) do not count as a change
     and do not require a bump.
  2. The bump segment MUST match the change type:
       * ``minor`` for additive changes (new endpoint, field, or enum value),
       * ``patch`` for spec-only edits (description, example, or annotation).
     A bump of the wrong segment is blocked with an error naming the expected
     segment.
  3. Breaking changes are never allowed in place. A breaking change is only
     permitted when the privileged ``breaking-change-approved`` label is present
     (a formal override restricted to engineering leadership) AND ``info.version``
     is bumped by a ``minor`` increment. Otherwise it is blocked, full stop. A
     genuinely new major version is a new spec served from a separate URL path,
     so it would not register as a breaking change here.

Dynamic-map / ``additionalProperties`` content (labels, context_data,
input_data, output_data, result) is not treated as breaking; oasdiff reports
such changes as non-breaking.

Usage:
    ./check-breaking-changes.py --base devel --head HEAD
    ./check-breaking-changes.py --base-spec baseline.yaml --head-spec current.yaml
    ./check-breaking-changes.py --base devel --head HEAD --pr-labels '["breaking-change-approved"]'

Returns:
    JSON with structure:
    {
        "has_breaking_changes": bool,
        "breaking_changes": str,
        "all_changes": str,
        "has_changes": bool,
        "version_bumped": bool,
        "base_version": str,
        "head_version": str,
        "version_bump_type": str | null,
        "expected_bump_type": str | null,
        "breaking_approved": bool,
        "spec_path": str,
        "gate_code": str
    }

Exit codes:
    0 - Change is allowed (no changes, non-breaking change bumped by the correct
        segment, or an approved breaking change bumped by a minor segment)
    1 - Change is blocked (breaking without approval, any meaningful spec change
        with no version bump, or a wrong-segment bump)
    2 - Error running oasdiff or processing specs
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


DEFAULT_SPEC_PATH = "backend/src/syntara/schemas/openapi.yaml"
# Privileged override label for breaking changes. Restricted to the
# ``syntara-leads`` team via the Breaking Change Label Guard workflow; CI here
# only checks for its presence.
BREAKING_CHANGE_APPROVED_LABEL = "breaking-change-approved"


@dataclass(frozen=True)
class GateDecision:
    """Result of applying the OpenAPI versioning gate."""

    allowed: bool
    code: str
    message: str


def run_command(cmd: list[str], capture_output: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and return the result."""
    try:
        return subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            check=False,  # Don't raise on non-zero exit
        )
    except FileNotFoundError as e:
        print(f"ERROR: Command not found: {cmd[0]}", file=sys.stderr)
        print(f"Details: {e}", file=sys.stderr)
        sys.exit(2)


def get_spec_from_git(ref: str, spec_path: str) -> str | None:
    """Get OpenAPI spec content from a git reference.

    Returns None only when the ref resolves but the path does not exist on it
    (e.g. the file was renamed or added in this branch). Exits with code 2 if
    the ref itself cannot be resolved (e.g. a typo, or the branch was not
    fetched in CI), so a bad ref cannot be silently treated as "new spec,
    nothing to check". Also exits with code 2 on other git errors.
    """
    ref_exists = run_command(
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"]
    )
    if ref_exists.returncode != 0:
        print(
            f"ERROR: Git ref '{ref}' could not be resolved. "
            f"Ensure it exists and is fetched (e.g. 'git fetch origin {ref}').",
            file=sys.stderr,
        )
        sys.exit(2)
    exists = run_command(["git", "cat-file", "-e", f"{ref}:{spec_path}"])
    if exists.returncode != 0:
        return None
    result = run_command(["git", "show", f"{ref}:{spec_path}"])
    if result.returncode != 0:
        print(f"ERROR: Failed to get spec from git ref '{ref}'", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(2)
    return result.stdout


def extract_info_version(content: str) -> str | None:
    """Extract info.version from OpenAPI spec YAML content."""
    in_info = False
    for line in content.split("\n"):
        if line.startswith("info:"):
            in_info = True
            continue
        if in_info:
            if line and not line[0].isspace():
                break
            stripped = line.strip()
            if stripped.startswith("version:"):
                return stripped.split(":", 1)[1].strip().strip("\"'")
    return None


def parse_semver(version: str) -> tuple[int, int, int] | None:
    """Parse a semver string into (major, minor, patch). Returns None on failure."""
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def get_version_bump_type(base_version: str, head_version: str) -> str | None:
    """Determine the version bump type between base and head.

    Returns "major", "minor", "patch", or None (no bump / downgrade / unparseable).
    """
    base = parse_semver(base_version)
    head = parse_semver(head_version)
    if base is None or head is None:
        return None
    if head[0] > base[0]:
        return "major"
    if head == base:
        return None
    if head[1] > base[1] and head[0] == base[0]:
        return "minor"
    if head[2] > base[2] and head[0] == base[0] and head[1] == base[1]:
        return "patch"
    return None


def check_breaking_changes(base_spec: str, head_spec: str) -> tuple[bool, str]:
    """Run oasdiff breaking changes check.

    Args:
        base_spec: Path to baseline spec or spec content
        head_spec: Path to current spec or spec content

    Returns:
        Tuple of (has_breaking_changes, output_text)
    """
    # Check if oasdiff is installed
    version_check = run_command(["oasdiff", "--version"])
    if version_check.returncode != 0:
        print("ERROR: oasdiff is not installed.", file=sys.stderr)
        print("Run: ./scripts/openapi/install-oasdiff.sh", file=sys.stderr)
        sys.exit(2)

    # Run oasdiff breaking changes check. Without --fail-on, oasdiff exits 0 even
    # when it finds breaking changes, so we must request a failing exit code.
    # With --fail-on ERR the exit code is:
    #   0   -> no ERR-level breaking changes
    #   1   -> at least one ERR-level breaking change
    #   >1  -> oasdiff error (e.g. spec failed to load), not a breaking change
    result = run_command(
        [
            "oasdiff",
            "breaking",
            base_spec,
            head_spec,
            "--format",
            "text",
            "--fail-on",
            "ERR",
        ]
    )
    output = (result.stdout + result.stderr).strip()

    # Distinguish "breaking changes found" (exit 1) from a tool error (exit >1).
    # Treating any non-zero code as breaking would both misreport oasdiff errors
    # as breaking changes and (before --fail-on was added) miss real ones.
    if result.returncode not in (0, 1):
        print(
            f"ERROR: oasdiff failed (exit {result.returncode}) while checking for breaking changes:\n{output}",
            file=sys.stderr,
        )
        sys.exit(2)

    has_breaking = result.returncode == 1
    return has_breaking, output


def get_all_changes(base_spec: str, head_spec: str) -> str:
    """Get all changes (breaking and non-breaking) using oasdiff changelog.

    Args:
        base_spec: Path to baseline spec or spec content
        head_spec: Path to current spec or spec content

    Returns:
        Changelog output text
    """
    result = run_command(
        [
            "oasdiff",
            "changelog",
            base_spec,
            head_spec,
            "--format",
            "text",
        ]
    )

    return (result.stdout + result.stderr).strip()


def get_changelog_entries(base_spec: str, head_spec: str) -> list[dict[str, Any]]:
    """Get structured changelog entries from oasdiff (JSON format).

    Each entry describes a *structural* change (added endpoint, field, enum
    value, etc.). oasdiff does NOT report spec-only edits (description, summary,
    example, annotation) here; those are detected via canonical comparison
    instead. Returns an empty list when there are no structural changes or the
    JSON cannot be parsed.
    """
    result = run_command(["oasdiff", "changelog", base_spec, head_spec, "--format", "json"])
    text = (result.stdout or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def check_approval_label(pr_labels_json: str) -> bool:
    """Check if the breaking-change approval label is present on the PR.

    The contract is a JSON-encoded array of the PR's label names (e.g.
    ``["bug", "breaking-change-approved"]``), matched **exactly**. A JSON array
    is used instead of a comma-joined string so that a label name that itself
    contains a comma cannot be split into two and forge the approval label. The
    match is case-sensitive to stay consistent with the exact-case ``if:``
    conditions in ``breaking-change-label-guard.yml`` and
    ``openapi-breaking-changes.yml``; a case-variant label that never triggers
    those guards must not be accepted here either.

    Args:
        pr_labels_json: JSON-encoded array of PR label names

    Returns:
        True if the ``breaking-change-approved`` label is present
    """
    if not pr_labels_json:
        return False
    try:
        labels = json.loads(pr_labels_json)
    except json.JSONDecodeError as exc:
        # Fail loudly: a malformed value almost always means a caller reverted
        # to the old comma-joined format. Silently returning False would hide
        # that as a confusing "not approved" false-negative.
        raise SystemExit(f"--pr-labels must be JSON-encoded, got: {pr_labels_json!r}") from exc
    return isinstance(labels, list) and BREAKING_CHANGE_APPROVED_LABEL in labels


def canonicalize_spec(content: str | None) -> tuple[bool, Any]:
    """Parse spec content into a canonical (semantic) data structure.

    ``info.version`` is stripped so that a version bump on its own is not counted
    as a meaningful change. Returns ``(parsed_ok, data)``; ``parsed_ok`` is False
    when the content is not valid YAML (the caller then falls back to a raw
    string comparison).
    """
    if not content:
        return True, None
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError:
        return False, None
    if isinstance(data, dict) and isinstance(data.get("info"), dict):
        data["info"] = {k: v for k, v in data["info"].items() if k != "version"}
    return True, data


def has_meaningful_change(
    base_content: str | None,
    head_content: str | None,
    *,
    has_breaking: bool,
) -> bool:
    """True if the spec changed semantically (ignoring ``info.version``).

    Comparison is canonical: whitespace, indentation, line endings, key order,
    and quote style do not count as changes. Breaking changes always count.
    Falls back to a raw string comparison if either spec cannot be parsed.
    """
    if has_breaking:
        return True
    base_ok, base_data = canonicalize_spec(base_content)
    head_ok, head_data = canonicalize_spec(head_content)
    if base_ok and head_ok:
        return base_data != head_data
    return (base_content or "") != (head_content or "")


def classify_expected_segment(
    *,
    has_breaking: bool,
    has_changes: bool,
    changelog_entries: list[dict[str, Any]],
) -> str | None:
    """Determine the version-bump segment a change is expected to use.

    Rules (see module docstring):
      * No meaningful change -> None (no bump required).
      * Breaking change (approved in place) -> "minor" (never "major"; a new
        major version is a new spec at a new URL path, outside this gate).
      * Additive change (oasdiff reports structural entries) -> "minor".
      * Spec-only edit (canonical diff with no structural entries, e.g. a
        description/example/annotation change) -> "patch".
    """
    if not has_changes and not has_breaking:
        return None
    if has_breaking:
        return "minor"
    if changelog_entries:
        return "minor"
    return "patch"


def evaluate_gate(
    *,
    has_breaking: bool,
    has_changes: bool,
    version_bump_type: str | None,
    expected_bump_type: str | None,
    breaking_approved: bool,
) -> GateDecision:
    """Apply the OpenAPI versioning gate. Returns whether the PR is allowed.

    Rules:
      * No spec changes -> allowed.
      * Breaking changes without the approval label -> blocked, full stop.
      * Any meaningful spec change without an info.version bump -> blocked.
      * A bump using the wrong segment -> blocked (names the expected segment).
      * Approved breaking change (minor bump) or non-breaking change (correct
        segment) -> allowed.
    """
    version_bumped = version_bump_type is not None

    if not has_breaking and not has_changes:
        return GateDecision(
            allowed=True,
            code="ok",
            message="No OpenAPI spec changes detected",
        )

    if has_breaking and not breaking_approved:
        return GateDecision(
            allowed=False,
            code="breaking_blocked",
            message=(
                "BLOCKED: This PR introduces breaking changes to the current API version. "
                "Breaking changes are never allowed in place.\n"
                "  - A new major version must be a new spec served from a separate URL path "
                "(it would not register as a breaking change here).\n"
                f"  - For an approved emergency override, request the '{BREAKING_CHANGE_APPROVED_LABEL}' "
                "label from engineering leadership (syntara-leads)."
            ),
        )

    if not version_bumped:
        return GateDecision(
            allowed=False,
            code="version_bump_required",
            message=(
                "BLOCKED: The OpenAPI spec changed but info.version was not bumped. "
                "Every meaningful spec change must bump info.version to signal the change "
                f"to reviewers and API consumers (expected a '{expected_bump_type}' bump)."
            ),
        )

    if expected_bump_type is not None and version_bump_type != expected_bump_type:
        return GateDecision(
            allowed=False,
            code="incorrect_version_increment",
            message=(
                f"BLOCKED: info.version was bumped by a '{version_bump_type}' segment, but this "
                f"change requires a '{expected_bump_type}' bump. "
                + (
                    "Additive changes (new endpoint, field, or enum value) require a minor bump; "
                    "spec-only edits (description, example, annotation) require a patch bump. "
                    if not has_breaking
                    else "An approved in-place breaking change requires a minor bump, not a major "
                    "one; a new major version is a new spec at a new URL path. "
                )
                + f"Set info.version to a '{expected_bump_type}' increment."
            ),
        )

    if has_breaking:
        return GateDecision(
            allowed=True,
            code="breaking_approved",
            message=(
                f"ALLOWED: Breaking change permitted via the '{BREAKING_CHANGE_APPROVED_LABEL}' "
                "label (privileged override) with a minor version bump."
            ),
        )

    return GateDecision(
        allowed=True,
        code="ok",
        message=f"Non-breaking spec change with a correct '{version_bump_type}' version bump",
    )


def read_spec_content(spec_path: str) -> str:
    """Read spec content from a file path."""
    return Path(spec_path).read_text()


def main():
    parser = argparse.ArgumentParser(description="Check OpenAPI spec for breaking changes")

    # Input options
    spec_group = parser.add_mutually_exclusive_group()
    spec_group.add_argument(
        "--base",
        help="Git reference for baseline spec (e.g., 'devel', 'HEAD~1')",
    )
    spec_group.add_argument(
        "--base-spec",
        help="Path to baseline OpenAPI spec file",
    )

    parser.add_argument(
        "--head",
        help="Git reference for current spec (e.g., 'HEAD')",
    )
    parser.add_argument(
        "--head-spec",
        help="Path to current OpenAPI spec file",
        default=DEFAULT_SPEC_PATH,
    )
    parser.add_argument(
        "--spec-path",
        help="Path to spec within git repo",
        default=DEFAULT_SPEC_PATH,
    )
    parser.add_argument(
        "--fallback-spec-path",
        help="Fallback path within git repo if --spec-path not found on base ref (e.g. after a rename)",
        default=None,
    )

    # PR labels for the breaking-change approval override
    parser.add_argument(
        "--pr-labels",
        help='JSON-encoded array of PR label names, e.g. \'["bug", "breaking-change-approved"]\'',
        default="",
    )

    # Output options
    parser.add_argument(
        "--output",
        "-o",
        help="Output file (default: stdout)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "text"],
        default="json",
        help="Output format (default: json)",
    )

    args = parser.parse_args()

    # Track spec content for version extraction
    base_spec_content = None
    head_spec_content = None

    # Determine base spec source
    if args.base_spec:
        base_spec_path = args.base_spec
        base_spec_content = read_spec_content(base_spec_path)
    elif args.base:
        base_spec_content = get_spec_from_git(args.base, args.spec_path)
        if base_spec_content is None and args.fallback_spec_path:
            print(
                f"Spec not found at '{args.spec_path}' on '{args.base}'; trying fallback '{args.fallback_spec_path}'",
                file=sys.stderr,
            )
            base_spec_content = get_spec_from_git(args.base, args.fallback_spec_path)
        if base_spec_content is None:
            # A spec that does not exist on the base ref is a *new* spec (e.g. a
            # new major version introduced at a new URL path). It has no prior
            # baseline to compare against, so the gate does not fire.
            print(
                f"Spec path not found on base ref '{args.base}' (file is new or renamed). "
                f"Skipping breaking changes check.",
                file=sys.stderr,
            )
            sys.exit(0)
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(base_spec_content)
            base_spec_path = f.name
    else:
        print("ERROR: Must specify --base or --base-spec", file=sys.stderr)
        parser.print_help()
        sys.exit(2)

    # Determine head spec source
    if args.head:
        # Get spec from git reference - write to temp file
        head_spec_content = get_spec_from_git(args.head, args.spec_path)
        if head_spec_content is None:
            print(
                f"ERROR: Spec path '{args.spec_path}' not found on head ref '{args.head}'. "
                f"If the spec was intentionally deleted, this is a breaking change.",
                file=sys.stderr,
            )
            sys.exit(2)
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(head_spec_content)
            head_spec_path = f.name
    else:
        head_spec_path = args.head_spec
        head_spec_content = read_spec_content(head_spec_path)

    # Extract versions
    base_version = extract_info_version(base_spec_content) if base_spec_content else ""
    head_version = extract_info_version(head_spec_content) if head_spec_content else ""
    version_bump_type = get_version_bump_type(base_version, head_version) if base_version and head_version else None
    version_bumped = version_bump_type is not None

    # Check for breaking changes
    has_breaking, breaking_output = check_breaking_changes(base_spec_path, head_spec_path)

    # Get all changes (human-readable) and structured entries (for classification)
    all_changes = get_all_changes(base_spec_path, head_spec_path)
    changelog_entries = get_changelog_entries(base_spec_path, head_spec_path)

    has_changes = has_meaningful_change(
        base_spec_content or "",
        head_spec_content or "",
        has_breaking=has_breaking,
    )

    expected_bump_type = classify_expected_segment(
        has_breaking=has_breaking,
        has_changes=has_changes,
        changelog_entries=changelog_entries,
    )

    # Check the breaking-change approval label
    breaking_approved = check_approval_label(args.pr_labels)

    decision = evaluate_gate(
        has_breaking=has_breaking,
        has_changes=has_changes,
        version_bump_type=version_bump_type,
        expected_bump_type=expected_bump_type,
        breaking_approved=breaking_approved,
    )

    # Build result
    result = {
        "has_breaking_changes": has_breaking,
        "breaking_changes": breaking_output,
        "all_changes": all_changes,
        "has_changes": has_changes,
        "version_bumped": version_bumped,
        "base_version": base_version or "",
        "head_version": head_version or "",
        "version_bump_type": version_bump_type,
        "expected_bump_type": expected_bump_type,
        "breaking_approved": breaking_approved,
        "spec_path": args.spec_path,
        "gate_code": decision.code,
    }

    # Output
    if args.format == "json":
        output_text = json.dumps(result, indent=2)
    else:
        lines = _format_text_output(
            has_breaking=has_breaking,
            breaking_output=breaking_output,
            all_changes=all_changes,
            decision=decision,
            base_version=base_version,
            head_version=head_version,
            version_bumped=version_bumped,
            version_bump_type=version_bump_type,
            expected_bump_type=expected_bump_type,
            spec_path=args.spec_path,
        )
        output_text = "\n".join(lines)

    # Write output
    if args.output:
        Path(args.output).write_text(output_text)
    else:
        print(output_text)

    # JSON mode writes a machine-readable file (or stdout). Always also emit an
    # actionable text error on stderr when the gate blocks, so CI job logs name
    # the spec, versions, version_bumped, and breaking changes.
    if not decision.allowed and args.format == "json":
        print(
            "\n".join(
                _format_text_output(
                    has_breaking=has_breaking,
                    breaking_output=breaking_output,
                    all_changes=all_changes,
                    decision=decision,
                    base_version=base_version,
                    head_version=head_version,
                    version_bumped=version_bumped,
                    version_bump_type=version_bump_type,
                    expected_bump_type=expected_bump_type,
                    spec_path=args.spec_path,
                )
            ),
            file=sys.stderr,
        )

    sys.exit(0 if decision.allowed else 1)


def _format_text_output(
    *,
    has_breaking: bool,
    breaking_output: str,
    all_changes: str,
    decision: GateDecision,
    base_version: str,
    head_version: str,
    version_bumped: bool,
    version_bump_type: str | None,
    expected_bump_type: str | None,
    spec_path: str,
) -> list[str]:
    """Format results as human-readable text lines."""
    lines = []

    # Version info header: always include spec path, versions, and bump state
    lines.append(f"Spec: {spec_path}")
    lines.append(f"Version: {base_version or 'unknown'} -> {head_version or 'unknown'}")
    lines.append(f"version_bumped: {str(version_bumped).lower()}")
    if version_bump_type:
        lines.append(f"Bump type: {version_bump_type}")
    if expected_bump_type:
        lines.append(f"Expected bump: {expected_bump_type}")
    lines.append("")

    if has_breaking:
        lines.append("BREAKING CHANGES DETECTED")
        lines.append("=" * 50)
        lines.append(breaking_output)
        lines.append("")

    lines.append(decision.message)

    if all_changes and all_changes != breaking_output:
        lines.append("")
        lines.append("All changes:")
        lines.append("-" * 50)
        lines.append(all_changes)

    return lines


if __name__ == "__main__":
    main()
