#!/usr/bin/env python3
"""Check OpenAPI spec for breaking changes using oasdiff.

This script compares two OpenAPI specs and detects breaking changes,
returning structured JSON output for consumption by CI or local tooling.

Breaking changes on the current major version are always blocked.
Two override paths exist:
  1. Major version bump + breaking-change-ack in PR body (new API version)
  2. CVE escape hatch via a protected GitHub label (emergency override)

Usage:
    ./check-breaking-changes.py --base devel --head HEAD
    ./check-breaking-changes.py --base-spec baseline.yaml --head-spec current.yaml
    ./check-breaking-changes.py --pr-body "breaking-change-ack: <justification>" --pr-labels "cve-breaking-change-approved"

Returns:
    JSON with structure:
    {
        "has_breaking_changes": bool,
        "breaking_changes": str,
        "all_changes": str,
        "acknowledged": bool,
        "justification": str,
        "ack_insufficient": bool,
        "version_bumped": bool,
        "base_version": str,
        "head_version": str,
        "version_bump_type": str | null,
        "cve_approved": bool,
        "spec_path": str,
        "change_kind": "none" | "additive" | "other",
        "gate_code": str
    }

Exit codes:
    0 - No breaking changes, or breaking changes with valid override
    1 - Breaking changes or incorrect version bump without valid override
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


DEFAULT_SPEC_PATH = "backend/src/syntara/schemas/openapi.yaml"
CVE_ESCAPE_LABEL = "cve-breaking-change-approved"

# oasdiff changelog IDs that indicate additive (non-breaking) API surface.
_ADDITIVE_CHANGE_IDS = (
    "endpoint-added",
    "request-property-added",
    "response-property-added",
    "request-parameter-added",
    "request-body-added",
    "response-added",
    "response-media-type-added",
    "request-media-type-added",
    "request-property-enum-value-added",
    "response-property-enum-value-added",
)
_ADDITIVE_CHANGE_TEXT = re.compile(
    r"\badded the (?:path|endpoint|operations?|optional |required )|"
    r"\b(?:endpoint|path) added\b|"
    r"\badded .+ (?:request|response) propert|"
    r"\badded the .+ parameter\b|"
    r"\badded .+ enum value",
    re.IGNORECASE,
)


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

    Returns None if the path does not exist on the given ref (e.g. file was
    renamed or added in this branch). Exits with code 2 on other git errors.
    """
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

    Returns "major", "minor", "patch", or None (no bump / unparseable).
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

    # Run oasdiff breaking changes check
    result = run_command(
        [
            "oasdiff",
            "breaking",
            base_spec,
            head_spec,
            "--format",
            "text",
        ]
    )

    # oasdiff returns non-zero if breaking changes found
    has_breaking = result.returncode != 0
    output = result.stdout + result.stderr

    return has_breaking, output.strip()


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


def check_acknowledgment(pr_body: str) -> dict:
    """Check if breaking changes are acknowledged in PR body.

    Args:
        pr_body: PR description text

    Returns:
        Dict with keys: acknowledged, justification, ack_insufficient
    """
    if not pr_body:
        return {
            "acknowledged": False,
            "justification": "",
            "ack_insufficient": False,
        }

    # Pattern: breaking-change-ack: <justification>
    ack_pattern = re.compile(r"breaking-change-ack\s*:\s*(.+)", re.IGNORECASE)
    match = ack_pattern.search(pr_body)

    if not match:
        return {
            "acknowledged": False,
            "justification": "",
            "ack_insufficient": False,
        }

    justification = match.group(1).strip()

    # Validate justification is substantial (minimum 20 chars)
    if len(justification) < 20:
        return {
            "acknowledged": False,
            "justification": justification,
            "ack_insufficient": True,
        }

    return {
        "acknowledged": True,
        "justification": justification,
        "ack_insufficient": False,
    }


def check_cve_label(pr_labels: str) -> bool:
    """Check if the CVE escape hatch label is present on the PR.

    Args:
        pr_labels: Comma-separated list of PR label names

    Returns:
        True if the CVE escape label is present
    """
    if not pr_labels:
        return False
    labels = [label.strip().lower() for label in pr_labels.split(",")]
    return CVE_ESCAPE_LABEL.lower() in labels


def classify_non_breaking_changes(all_changes: str) -> str:
    """Classify non-breaking changelog output as none, additive, or other.

    Additive means new endpoints, properties, parameters, or enum values.
    ``other`` covers documentation, description, and similar non-surface changes.
    """
    text = (all_changes or "").strip()
    if not text or re.match(r"^no changes\b", text, re.IGNORECASE):
        return "none"
    lowered = text.lower()
    if any(change_id in lowered for change_id in _ADDITIVE_CHANGE_IDS):
        return "additive"
    if _ADDITIVE_CHANGE_TEXT.search(text):
        return "additive"
    return "other"


def evaluate_gate(
    *,
    has_breaking: bool,
    version_bump_type: str | None,
    acknowledged: bool,
    ack_insufficient: bool,
    justification: str,
    cve_approved: bool,
    change_kind: str,
) -> GateDecision:
    """Apply the OpenAPI versioning gate. Returns whether the PR is allowed."""
    allowed = True
    code = "ok"
    message = "No breaking changes detected"

    if has_breaking:
        if cve_approved:
            allowed = True
            code = "cve_override"
            message = "ALLOWED: CVE escape hatch label present"
        elif version_bump_type == "major" and acknowledged:
            allowed = True
            code = "major_ack"
            message = f"ALLOWED: Major version bump with acknowledgment: {justification}"
        elif acknowledged:
            allowed = False
            code = "ack_without_major"
            message = (
                "BLOCKED: Breaking changes require a major version bump. "
                "An acknowledgment alone is not sufficient."
            )
        elif ack_insufficient:
            allowed = False
            code = "ack_insufficient"
            message = f"BLOCKED: Insufficient acknowledgment: {justification}"
        else:
            allowed = False
            code = "breaking_blocked"
            message = (
                "BLOCKED: Breaking changes on the current major version are not allowed. "
                "Options:\n"
                "  1. Bump info.version to the next major version and add "
                "'breaking-change-ack: <justification>' to the PR body\n"
                "  2. For CVE fixes only: request the 'cve-breaking-change-approved' label "
                "from engineering leadership (Senior Director or above)"
            )
    elif version_bump_type == "major":
        allowed = False
        code = "incorrect_bump"
        message = (
            "BLOCKED: Major version bumps are reserved for breaking changes. "
            "Use a minor bump for additive features or a patch bump for fixes, "
            "or omit the bump."
        )
    elif change_kind == "additive" and version_bump_type == "patch":
        allowed = False
        code = "incorrect_bump"
        message = (
            "BLOCKED: Additive API changes require a minor version bump, not patch. "
            "Bump info.version minor (for example 1.0.0 -> 1.1.0), or omit the bump."
        )

    return GateDecision(allowed=allowed, code=code, message=message)


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

    # PR body for acknowledgment check
    parser.add_argument(
        "--pr-body",
        help="PR description text to check for acknowledgment",
        default="",
    )

    # PR labels for CVE escape hatch
    parser.add_argument(
        "--pr-labels",
        help="Comma-separated list of PR label names",
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
                f"Spec not found at '{args.spec_path}' on '{args.base}'; "
                f"trying fallback '{args.fallback_spec_path}'",
                file=sys.stderr,
            )
            base_spec_content = get_spec_from_git(args.base, args.fallback_spec_path)
        if base_spec_content is None:
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

    # Get all changes
    all_changes = get_all_changes(base_spec_path, head_spec_path)

    # Check acknowledgment and CVE label
    ack_result = check_acknowledgment(args.pr_body)
    cve_approved = check_cve_label(args.pr_labels)
    change_kind = classify_non_breaking_changes(all_changes) if not has_breaking else "none"
    decision = evaluate_gate(
        has_breaking=has_breaking,
        version_bump_type=version_bump_type,
        acknowledged=ack_result["acknowledged"],
        ack_insufficient=ack_result["ack_insufficient"],
        justification=ack_result["justification"],
        cve_approved=cve_approved,
        change_kind=change_kind,
    )

    # Build result
    result = {
        "has_breaking_changes": has_breaking,
        "breaking_changes": breaking_output,
        "all_changes": all_changes,
        **ack_result,
        "version_bumped": version_bumped,
        "base_version": base_version or "",
        "head_version": head_version or "",
        "version_bump_type": version_bump_type,
        "cve_approved": cve_approved,
        "spec_path": args.spec_path,
        "change_kind": change_kind,
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
            version_bump_type=version_bump_type,
            spec_path=args.spec_path,
        )
        output_text = "\n".join(lines)

    # Write output
    if args.output:
        Path(args.output).write_text(output_text)
    else:
        print(output_text)

    sys.exit(0 if decision.allowed else 1)


def _format_text_output(
    *,
    has_breaking: bool,
    breaking_output: str,
    all_changes: str,
    decision: GateDecision,
    base_version: str,
    head_version: str,
    version_bump_type: str | None,
    spec_path: str,
) -> list[str]:
    """Format results as human-readable text lines."""
    lines = []

    # Version info header — always include spec path and versions for CI errors
    lines.append(f"Spec: {spec_path}")
    lines.append(f"Version: {base_version or 'unknown'} -> {head_version or 'unknown'}")
    if version_bump_type:
        lines.append(f"Bump type: {version_bump_type}")
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
