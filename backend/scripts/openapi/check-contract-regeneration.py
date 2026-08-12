#!/usr/bin/env python3
"""Check that frontend contracts are regenerated when OpenAPI spec changes.

In the monorepo, when backend/src/syntara/schemas/openapi.yaml changes,
the generated TypeScript contracts in frontend/packages/syntara-contracts/src/
must also be updated (via `make gen-contracts`).

Usage:
    ./check-contract-regeneration.py --changed-files-from devel
    ./check-contract-regeneration.py --changed-files file1.ts file2.ts ...
    ./check-contract-regeneration.py --changed-files-stdin < changed_files.txt

Returns:
    JSON with structure:
    {
        "spec_changed": bool,
        "contracts_updated": bool,
        "has_exception": bool,
        "exception_justification": str | null,
        "exception_valid": bool,
        "severity": "notice" | "warning",
        "message": str
    }

Exit codes:
    0 - Always succeeds (contract check is informational, not blocking)
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict


OPENAPI_SPEC = "backend/src/syntara/schemas/openapi.yaml"
CONTRACTS_DIR = "frontend/packages/syntara-contracts/src/"
EXCEPTION_PATTERN = re.compile(
    r"no-(?:contract-regen|ui-pr)\s*:\s*(.+)",
    re.IGNORECASE,
)


def escape_markdown(text: str) -> str:
    """Escape markdown/HTML to prevent injection attacks."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#039;")
        .replace("`", "&#96;")
    )


def get_changed_files_from_ref(base_ref: str) -> list[str]:
    """Get list of changed files compared to a base reference."""
    result = subprocess.run(
        ["git", "diff", "--name-only", f"origin/{base_ref}...HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    if result.returncode != 0:
        print(f"WARNING: Could not get changed files vs {base_ref}", file=sys.stderr)
        return []
    return [f for f in result.stdout.strip().split("\n") if f]


def check_contracts_updated(changed_files: list[str], pr_body: str = "") -> Dict[str, any]:
    """Check if frontend contracts were regenerated alongside spec changes.

    Args:
        changed_files: List of files changed in the PR/branch
        pr_body: PR description text (for exception justification)

    Returns:
        Dict with detection results and formatted message
    """
    spec_changed = OPENAPI_SPEC in changed_files
    if not spec_changed:
        return _build_no_spec_change_result()

    contracts_updated = any(f.startswith(CONTRACTS_DIR) for f in changed_files)
    exception_match = EXCEPTION_PATTERN.search(pr_body) if pr_body else None

    if contracts_updated:
        return _build_contracts_updated_result()
    elif exception_match:
        justification = exception_match.group(1).strip()
        return _build_exception_result(justification)
    else:
        return _build_contracts_stale_result()


def _build_no_spec_change_result() -> Dict[str, any]:
    """Build result when the OpenAPI bundled spec was not modified."""
    message = (
        "**No OpenAPI spec changes detected** — contract regeneration check skipped.\n\n"
        f"This check applies when `{OPENAPI_SPEC}` is modified in the change set."
    )

    return {
        "spec_changed": False,
        "contracts_updated": False,
        "has_exception": False,
        "exception_justification": None,
        "exception_valid": False,
        "severity": "notice",
        "message": message,
    }


def _build_contracts_updated_result() -> Dict[str, any]:
    """Build result when contracts are updated in the same PR."""
    message = (
        "**Frontend contracts updated** alongside OpenAPI spec changes.\n\n"
        "The generated TypeScript types in `frontend/packages/syntara-contracts/src/` "
        "are included in this change set."
    )

    return {
        "spec_changed": True,
        "contracts_updated": True,
        "has_exception": False,
        "exception_justification": None,
        "exception_valid": False,
        "severity": "notice",
        "message": message,
    }


def _build_exception_result(justification: str) -> Dict[str, any]:
    """Build result when exception is claimed."""
    escaped_justification = escape_markdown(justification)

    if len(justification) < 10:
        message = (
            "**Exception claimed but justification is too brief**\n\n"
            "You've marked this as `no-contract-regen` but the justification is insufficient:\n"
            f"```\n{escaped_justification}\n```\n\n"
            'Please provide a detailed explanation (e.g., "description-only change, '
            'no type impact — verified via contract regen").'
        )

        return {
            "spec_changed": True,
            "contracts_updated": False,
            "has_exception": True,
            "exception_justification": justification,
            "exception_valid": False,
            "severity": "warning",
            "message": message,
        }

    message = (
        "**Exception: No contract regeneration needed**\n\n"
        f"Justification provided:\n```\n{escaped_justification}\n```\n\n"
        "Reviewer: Please verify this justification is valid."
    )

    return {
        "spec_changed": True,
        "contracts_updated": False,
        "has_exception": True,
        "exception_justification": justification,
        "exception_valid": True,
        "severity": "notice",
        "message": message,
    }


def _build_contracts_stale_result() -> Dict[str, any]:
    """Build result when contracts are not updated and no exception given."""
    message = (
        "**OpenAPI spec changed — frontend contracts not updated**\n\n"
        "This PR modifies `backend/src/syntara/schemas/openapi.yaml` but the generated "
        "TypeScript types in `frontend/packages/syntara-contracts/src/` were not updated.\n\n"
        "### Action Required\n\n"
        "1. **Regenerate frontend contracts** from the updated spec:\n"
        "   ```bash\n"
        "   make gen-contracts\n"
        "   ```\n"
        "   Then commit the regenerated files in this PR.\n\n"
        "2. **OR, if this is a spec-only change** (description, examples, metadata) "
        "with no type impact:\n"
        "   - Add to PR description: `no-contract-regen: <justification>`\n"
        "   - Example: `no-contract-regen: description-only change, no type impact`\n\n"
        "### Why This Matters\n\n"
        "- **Additive changes** (new endpoints, new fields) make types available to "
        "UI developers\n"
        "- **Breaking changes** (removed/changed fields) cause TypeScript errors or "
        "runtime failures\n"
        "- Keeping contracts in sync prevents drift between backend API and frontend "
        "types\n\n"
        "---\n"
        "This is an **informational warning**, not a blocker. "
        "The reviewer will verify the decision."
    )

    return {
        "spec_changed": True,
        "contracts_updated": False,
        "has_exception": False,
        "exception_justification": None,
        "exception_valid": False,
        "severity": "warning",
        "message": message,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Check that frontend contracts are regenerated when OpenAPI spec changes"
    )

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--changed-files",
        nargs="*",
        help="List of changed file paths",
    )
    input_group.add_argument(
        "--changed-files-from",
        help="Git ref to compare against (e.g., 'devel') — computes changed files automatically",
    )
    input_group.add_argument(
        "--changed-files-stdin",
        action="store_true",
        help="Read changed file paths from stdin (one per line)",
    )

    parser.add_argument(
        "--pr-body",
        help="PR description text to check for exception justification",
        default="",
    )

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

    if args.changed_files is not None:
        changed_files = args.changed_files
    elif args.changed_files_from:
        changed_files = get_changed_files_from_ref(args.changed_files_from)
    else:
        changed_files = [line.strip() for line in sys.stdin if line.strip()]

    result = check_contracts_updated(changed_files, args.pr_body)

    if args.format == "json":
        output_text = json.dumps(result, indent=2)
    else:
        output_text = result["message"]

    if args.output:
        Path(args.output).write_text(output_text)
    else:
        print(output_text)

    sys.exit(0)


if __name__ == "__main__":
    main()
