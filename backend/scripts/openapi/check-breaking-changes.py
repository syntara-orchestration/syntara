#!/usr/bin/env python3
"""Check OpenAPI spec for breaking changes using oasdiff.

This script compares two OpenAPI specs and detects breaking changes,
returning structured JSON output for consumption by CI or local tooling.

Usage:
    ./check-breaking-changes.py --base devel --head HEAD
    ./check-breaking-changes.py --base-spec baseline.yaml --head-spec current.yaml
    ./check-breaking-changes.py --pr-body "$(cat pr_description.txt)"

Returns:
    JSON with structure:
    {
        "has_breaking_changes": bool,
        "breaking_changes": str,
        "all_changes": str,
        "acknowledged": bool,
        "justification": str,
        "ack_insufficient": bool
    }

Exit codes:
    0 - No breaking changes OR breaking changes acknowledged
    1 - Breaking changes detected and not acknowledged
    2 - Error running oasdiff or processing specs
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple


DEFAULT_SPEC_PATH = "backend/src/syntara/schemas/openapi.yaml"


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


def get_spec_from_git(ref: str, spec_path: str) -> Optional[str]:
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


def check_breaking_changes(base_spec: str, head_spec: str) -> Tuple[bool, str]:
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


def check_acknowledgment(pr_body: str) -> Dict[str, any]:
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

    # Determine base spec source
    if args.base_spec:
        base_spec_path = args.base_spec
    elif args.base:
        spec_content = get_spec_from_git(args.base, args.spec_path)
        if spec_content is None and args.fallback_spec_path:
            print(
                f"Spec not found at '{args.spec_path}' on '{args.base}'; "
                f"trying fallback '{args.fallback_spec_path}'",
                file=sys.stderr,
            )
            spec_content = get_spec_from_git(args.base, args.fallback_spec_path)
        if spec_content is None:
            print(
                f"Spec path not found on base ref '{args.base}' (file is new or renamed). "
                f"Skipping breaking changes check.",
                file=sys.stderr,
            )
            sys.exit(0)
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(spec_content)
            base_spec_path = f.name
    else:
        print("ERROR: Must specify --base or --base-spec", file=sys.stderr)
        parser.print_help()
        sys.exit(2)

    # Determine head spec source
    if args.head:
        # Get spec from git reference - write to temp file
        spec_content = get_spec_from_git(args.head, args.spec_path)
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(spec_content)
            head_spec_path = f.name
    else:
        head_spec_path = args.head_spec

    # Check for breaking changes
    has_breaking, breaking_output = check_breaking_changes(base_spec_path, head_spec_path)

    # Get all changes
    all_changes = get_all_changes(base_spec_path, head_spec_path)

    # Check acknowledgment
    ack_result = check_acknowledgment(args.pr_body)

    # Build result
    result = {
        "has_breaking_changes": has_breaking,
        "breaking_changes": breaking_output,
        "all_changes": all_changes,
        **ack_result,
    }

    # Output
    if args.format == "json":
        output_text = json.dumps(result, indent=2)
    else:
        # Text format
        lines = []
        if has_breaking:
            lines.append("BREAKING CHANGES DETECTED")
            lines.append("=" * 50)
            lines.append(breaking_output)
            lines.append("")
            if ack_result["acknowledged"]:
                lines.append(f"Acknowledged: {ack_result['justification']}")
            elif ack_result["ack_insufficient"]:
                lines.append(f"Insufficient acknowledgment: {ack_result['justification']}")
            else:
                lines.append("NOT ACKNOWLEDGED - Add 'breaking-change-ack: <justification>' to PR")
        else:
            lines.append("No breaking changes detected")

        if all_changes and all_changes != breaking_output:
            lines.append("")
            lines.append("All changes:")
            lines.append("-" * 50)
            lines.append(all_changes)

        output_text = "\n".join(lines)

    # Write output
    if args.output:
        Path(args.output).write_text(output_text)
    else:
        print(output_text)

    # Exit with appropriate code
    if has_breaking and not ack_result["acknowledged"]:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
