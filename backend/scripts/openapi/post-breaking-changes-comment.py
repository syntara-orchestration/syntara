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


def _incorrect_bump_lines(
    *,
    spec_path: str,
    base_version: str,
    head_version: str,
    version_bump_type: str | None,
    change_kind: str,
) -> list[str]:
    """Format the blocked incorrect-bump PR comment section."""
    lines = [
        "### Incorrect Version Bump (Blocked)\n",
        (
            "This PR does **not** introduce breaking changes, but `info.version` "
            "was bumped in a way that does not match the change type.\n"
        ),
    ]
    if spec_path:
        lines.append(f"**Spec:** `{escape_markdown(spec_path)}`")
    if base_version or head_version:
        lines.append(
            f"**Version:** {escape_markdown(base_version or 'unknown')} → "
            f"{escape_markdown(head_version or 'unknown')}"
        )
        if version_bump_type:
            lines.append(f" ({escape_markdown(version_bump_type)} bump)")
        lines.append("")
    if change_kind:
        lines.append(f"**Change kind:** {escape_markdown(change_kind)}\n")
    if version_bump_type == "major":
        lines.append(
            "Major bumps are reserved for breaking changes. "
            "Use a **minor** bump for additive features/new endpoints, "
            "or a **patch** bump for fixes — or omit the bump.\n"
        )
    elif change_kind == "additive":
        lines.append(
            "Additive API changes require a **minor** version bump "
            "(for example `1.0.0` → `1.1.0`). A patch bump is not sufficient. "
            "You may also omit the bump.\n"
        )
    else:
        lines.append("See the OpenAPI versioning policy for the required bump type.\n")
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
    acknowledged = results["acknowledged"]
    ack_insufficient = results["ack_insufficient"]
    justification = results["justification"]
    base_version = results.get("base_version", "")
    head_version = results.get("head_version", "")
    version_bump_type = results.get("version_bump_type")
    cve_approved = results.get("cve_approved", False)
    spec_path = results.get("spec_path", "")
    gate_code = results.get("gate_code", "")
    change_kind = results.get("change_kind", "")

    escaped_breaking = escape_markdown(breaking_changes)
    escaped_all = escape_markdown(all_changes)
    escaped_justification = escape_markdown(justification)

    lines = [COMMENT_MARKER, ""]

    if has_breaking:
        # Determine which override path (if any) was used
        major_bump_ack = version_bump_type == "major" and acknowledged

        if cve_approved:
            lines.append("### Breaking Changes Detected (CVE Override)\n")
            lines.append(
                "The `cve-breaking-change-approved` label is present. "
                "This breaking change is permitted under the CVE escape hatch.\n"
            )
            lines.append("**Reviewer:** Please verify:")
            lines.append("1. This override was authorized by engineering leadership (Senior Director or above)")
            lines.append("2. The breaking change is necessary to address a CVE")
            lines.append("3. Frontend contracts are regenerated in this PR (`make gen-contracts`)")
            lines.append("4. Migration path is documented for API consumers\n")
        elif major_bump_ack:
            lines.append("### Breaking Changes Detected (New Major Version)\n")
            lines.append(
                f"The API version has been bumped from **{escape_markdown(base_version)}** to "
                f"**{escape_markdown(head_version)}** (major) with acknowledgment:\n"
            )
            lines.append(f"```\n{escaped_justification}\n```\n")
            lines.append("**Reviewer:** Please verify:")
            lines.append("1. The justification is valid and necessary")
            lines.append("2. The new major version is served from a separate URL path (e.g., `/api/v2/`)")
            lines.append("3. Frontend contracts are regenerated in this PR (`make gen-contracts`)")
            lines.append("4. Migration path is clear for API consumers\n")
        else:
            lines.append("### Breaking Changes Detected (Blocked)\n")
            lines.append(
                "This PR introduces **breaking changes** that are **not allowed** "
                "on the current major API version.\n"
            )

            if spec_path:
                lines.append(f"**Spec:** `{escape_markdown(spec_path)}`")
            if base_version or head_version:
                lines.append(f"**Current version:** {escape_markdown(base_version or 'unknown')}")
                lines.append(f"**PR version:** {escape_markdown(head_version or 'unknown')}\n")

            if acknowledged and version_bump_type != "major":
                lines.append(
                    "A `breaking-change-ack` is present, but breaking changes require "
                    "a **major version bump** (not just an acknowledgment).\n"
                )
            elif ack_insufficient:
                lines.append(
                    f"**Insufficient acknowledgment:**\n```\n{escaped_justification}\n```\n"
                    "Acknowledgments must be at least 20 characters.\n"
                )

            lines.append("**To resolve, choose one of:**\n")
            lines.append(
                "1. **Route to a new major version** — bump `info.version` to the next major "
                "(e.g., 2.0.0) and add to your PR description:\n"
                "   ```\n"
                "   breaking-change-ack: <detailed justification>\n"
                "   ```"
            )
            lines.append(
                "2. **CVE escape hatch** — if this is a CVE fix that cannot avoid a breaking change, "
                "request the `cve-breaking-change-approved` label from engineering leadership "
                "(Senior Director or above)\n"
            )

        lines.append("---\n")
        lines.append("### Breaking Changes Detected\n")
        lines.append(f"```\n{escaped_breaking}\n```\n")

        if all_changes and all_changes != breaking_changes:
            lines.append("<details>")
            lines.append("<summary>All Changes (including non-breaking)</summary>\n")
            lines.append(f"```\n{escaped_all}\n```")
            lines.append("</details>\n")

        if not (cve_approved or major_bump_ack):
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
    elif gate_code == "incorrect_bump":
        lines.extend(
            _incorrect_bump_lines(
                spec_path=spec_path,
                base_version=base_version,
                head_version=head_version,
                version_bump_type=version_bump_type,
                change_kind=change_kind,
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
