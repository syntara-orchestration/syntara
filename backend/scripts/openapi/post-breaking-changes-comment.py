#!/usr/bin/env python3
"""Post or update GitHub PR comment for breaking changes check results.

This script formats the breaking changes check results and posts/updates
a PR comment using the GitHub API via gh CLI.

Usage:
    ./post-breaking-changes-comment.py --results results.json --pr-number 123
    ./post-breaking-changes-comment.py --results results.json --pr-number 123 --repo owner/repo

Environment variables:
    GITHUB_TOKEN - GitHub API token (optional, gh CLI handles auth)
"""

import argparse
import json
import subprocess
from pathlib import Path


COMMENT_MARKER = "<!-- syntara-openapi-breaking-changes -->"


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


def _json_bool(*, value: bool) -> str:
    """Return a JSON true/false string for *value*."""
    return "true" if value else "false"


def _coerce_version_bumped(results: dict) -> bool:
    """Read version_bumped from results, falling back to version_bump_type."""
    if results.get("version_bumped") is not None:
        return bool(results["version_bumped"])
    return results.get("version_bump_type") is not None


def _gate_context_lines(
    *,
    spec_path: str,
    base_version: str,
    head_version: str,
    version_bumped: bool,
    version_line_suffix: str = "",
) -> list[str]:
    """Return spec, version, and version_bumped lines for blocked PR comments."""
    lines: list[str] = []
    if spec_path:
        lines.append(f"**Spec:** `{escape_markdown(spec_path)}`")
    if base_version or head_version:
        lines.append(
            f"**Version:** {escape_markdown(base_version or 'unknown')} → "
            f"{escape_markdown(head_version or 'unknown')}{version_line_suffix}"
        )
    lines.append(f"**version_bumped:** `{_json_bool(value=version_bumped)}`")
    lines.append("")
    return lines


def _version_bump_required_lines(
    *,
    spec_path: str,
    base_version: str,
    head_version: str,
    version_bumped: bool,
    expected_bump_type: str | None,
) -> list[str]:
    """Format the blocked missing-version-bump PR comment section."""
    lines = [
        "### Version Bump Required (Blocked)\n",
        (
            "This PR changes the OpenAPI spec but does **not** bump `info.version`. "
            "Every meaningful spec change must include an `info.version` bump so reviewers can see "
            "your interpretation of the change and API consumers are aware of the update.\n"
        ),
    ]
    lines.extend(
        _gate_context_lines(
            spec_path=spec_path,
            base_version=base_version,
            head_version=head_version,
            version_bumped=version_bumped,
            version_line_suffix=" (no bump)",
        )
    )
    if expected_bump_type:
        lines.append(f"**Expected bump:** `{escape_markdown(expected_bump_type)}`\n")
    lines.append(
        "Bump `info.version` to reflect the change — a **minor** bump for additive changes "
        "(new endpoint, field, or enum value) or a **patch** bump for spec-only edits "
        "(description, example, annotation).\n"
    )
    return lines


def _incorrect_version_increment_lines(
    *,
    spec_path: str,
    base_version: str,
    head_version: str,
    version_bumped: bool,
    version_bump_type: str | None,
    expected_bump_type: str | None,
) -> list[str]:
    """Format the blocked incorrect-version-increment PR comment section."""
    lines = [
        "### Incorrect Version Increment (Blocked)\n",
        (
            f"This PR incremented `info.version` by a **{escape_markdown(version_bump_type or 'unknown')}** "
            f"segment, but the change requires a **{escape_markdown(expected_bump_type or 'unknown')}** increment.\n"
        ),
    ]
    lines.extend(
        _gate_context_lines(
            spec_path=spec_path,
            base_version=base_version,
            head_version=head_version,
            version_bumped=version_bumped,
        )
    )
    lines.append(
        "- **minor** for additive changes (new endpoint, field, or enum value)\n"
        "- **patch** for spec-only edits (description, example, annotation)\n"
        "- an approved in-place breaking change uses **minor** (not major — a new major "
        "version is a new spec at a new URL path)\n"
    )
    return lines


def format_breaking_changes_comment(results: dict, repo_owner: str, repo_name: str) -> str:
    """Format breaking changes results as a GitHub comment.

    Args:
        results: Output from check-breaking-changes.py
        repo_owner: Repository owner
        repo_name: Repository name

    Returns:
        Formatted markdown comment
    """
    has_breaking = results["has_breaking_changes"]
    breaking_changes = results["breaking_changes"]
    all_changes = results["all_changes"]
    base_version = results.get("base_version", "")
    head_version = results.get("head_version", "")
    version_bump_type = results.get("version_bump_type")
    expected_bump_type = results.get("expected_bump_type")
    version_bumped = _coerce_version_bumped(results)
    breaking_approved = results.get("breaking_approved", False)
    spec_path = results.get("spec_path", "")
    gate_code = results.get("gate_code", "")

    escaped_breaking = escape_markdown(breaking_changes)
    escaped_all = escape_markdown(all_changes)

    lines = [COMMENT_MARKER, ""]

    if has_breaking:
        if breaking_approved:
            lines.append("### Breaking Changes Detected (Approved Override)\n")
            lines.append(
                "The `breaking-change-approved` label is present. "
                "This breaking change is permitted via a privileged override.\n"
            )
            lines.append("**Reviewer:** Please verify:")
            lines.append("1. This override was authorized by engineering leadership")
            lines.append("2. The breaking change is genuinely necessary")
            lines.append("3. Frontend contracts are regenerated in this PR (`make gen-contracts`)")
            lines.append("4. Migration path is documented for API consumers\n")
        else:
            lines.append("### Breaking Changes Detected (Blocked)\n")
            lines.append(
                "This PR introduces **breaking changes** that are **not allowed** on the current API version.\n"
            )

            if spec_path:
                lines.append(f"**Spec:** `{escape_markdown(spec_path)}`")
            if base_version or head_version:
                lines.append(f"**Current version:** {escape_markdown(base_version or 'unknown')}")
                lines.append(f"**PR version:** {escape_markdown(head_version or 'unknown')}")
            lines.append(f"**version_bumped:** `{_json_bool(value=version_bumped)}`\n")

            lines.append("**To resolve, choose one of:**\n")
            lines.append(
                "1. **Route to a new major version** — a new major version is a new spec served "
                "from a separate URL path (e.g., `/api/v2/`), so it is not a breaking change to "
                "the current spec."
            )
            lines.append(
                "2. **Approved override** — if this breaking change is unavoidable, request the "
                "`breaking-change-approved` label from engineering leadership.\n"
            )

        lines.append("---\n")
        lines.append("### Breaking Changes Detected\n")
        lines.append(f"```\n{escaped_breaking}\n```\n")

        if all_changes and all_changes != breaking_changes:
            lines.append("<details>")
            lines.append("<summary>All Changes (including non-breaking)</summary>\n")
            lines.append(f"```\n{escaped_all}\n```")
            lines.append("</details>\n")

        if not breaking_approved:
            lines.append("---\n")
            lines.append("### What This Means\n")
            lines.append(
                "Per the **AO REST API Versioning and Deprecation Policy**, breaking changes "
                "never apply in place — v1 and v2 are separate specs served from different URL paths."
            )
            lines.append("- Removed endpoints or fields")
            lines.append("- Changed field types (e.g., string → number)")
            lines.append("- Changed required/optional status")
            lines.append("- Removed enum values\n")
    elif gate_code == "version_bump_required":
        lines.extend(
            _version_bump_required_lines(
                spec_path=spec_path,
                base_version=base_version,
                head_version=head_version,
                version_bumped=version_bumped,
                expected_bump_type=expected_bump_type,
            )
        )
    elif gate_code == "incorrect_version_increment":
        lines.extend(
            _incorrect_version_increment_lines(
                spec_path=spec_path,
                base_version=base_version,
                head_version=head_version,
                version_bumped=version_bumped,
                version_bump_type=version_bump_type,
                expected_bump_type=expected_bump_type,
            )
        )
    else:
        lines.append("### No Breaking Changes Detected\n")
        lines.append("This PR modifies the OpenAPI spec but does **not** introduce breaking changes.\n")

        if base_version and head_version:
            lines.append(f"**Version:** {escape_markdown(base_version)} → {escape_markdown(head_version)}")
            if version_bump_type:
                lines.append(f" ({version_bump_type} bump)\n")
            else:
                lines.append("\n")

        if all_changes and all_changes.strip():
            lines.append("**Changes detected:**")
            lines.append(f"```\n{escaped_all}\n```\n")

        lines.append("**Reminder:** Even for non-breaking changes, run `make gen-contracts` to update ")
        lines.append("the frontend TypeScript types. See the **OpenAPI Contract Regeneration Check** for guidance.\n")

    lines.append("---")
    lines.append(
        f"*Automated check from [`openapi-breaking-changes.yml`]"
        f"(https://github.com/{repo_owner}/{repo_name}/blob/devel/.github/workflows/openapi-breaking-changes.yml)*"
    )

    return "\n".join(lines)


def post_or_update_comment(pr_number: str, comment_body: str, repo: str) -> None:
    """Post or update PR comment using gh CLI.

    Args:
        pr_number: Pull request number
        comment_body: Comment markdown content
        repo: Repository in owner/repo format
    """
    # Find existing comment
    list_cmd = [
        "gh",
        "api",
        f"repos/{repo}/issues/{pr_number}/comments",
        "--paginate",
        "--jq",
        '.[] | select(.body | contains("syntara-openapi-breaking-changes")) | .id',
    ]

    result = subprocess.run(list_cmd, capture_output=True, text=True)

    if result.returncode == 0 and result.stdout.strip():
        # Update existing comment
        comment_id = result.stdout.strip().split("\n")[0]  # Take first match
        update_cmd = [
            "gh",
            "api",
            f"repos/{repo}/issues/comments/{comment_id}",
            "-X",
            "PATCH",
            "-f",
            f"body={comment_body}",
        ]
        subprocess.run(update_cmd, check=True)
        print(f"Updated comment {comment_id} on PR #{pr_number}")
    else:
        # Create new comment
        create_cmd = [
            "gh",
            "pr",
            "comment",
            pr_number,
            "--repo",
            repo,
            "--body",
            comment_body,
        ]
        subprocess.run(create_cmd, check=True)
        print(f"Created new comment on PR #{pr_number}")


def main():
    parser = argparse.ArgumentParser(description="Post breaking changes check results as GitHub PR comment")

    parser.add_argument(
        "--results",
        required=True,
        help="Path to JSON results file from check-breaking-changes.py",
    )
    parser.add_argument(
        "--pr-number",
        required=True,
        help="Pull request number",
    )
    parser.add_argument(
        "--repo",
        help="Repository in owner/repo format (auto-detected from gh if not provided)",
    )

    args = parser.parse_args()

    # Load results
    results = json.loads(Path(args.results).read_text())

    # Get repo if not provided
    if args.repo:
        repo = args.repo
    else:
        # Auto-detect from gh
        result = subprocess.run(
            ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
            capture_output=True,
            text=True,
            check=True,
        )
        repo = result.stdout.strip()

    repo_owner, repo_name = repo.split("/")

    # Format comment
    comment_body = format_breaking_changes_comment(results, repo_owner, repo_name)

    # Post or update comment
    post_or_update_comment(args.pr_number, comment_body, repo)


if __name__ == "__main__":
    main()
