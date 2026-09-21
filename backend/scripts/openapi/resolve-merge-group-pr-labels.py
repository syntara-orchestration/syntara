#!/usr/bin/env python3
"""Resolve merge-group pull-request labels for GitHub Actions.

The merge queue names its candidate ref with a final ``pr-<number>-<suffix>``
component. This script extracts that PR number, collects labels for it and
preceding queue entries, and writes them as a compact JSON array to
``GITHUB_OUTPUT``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

MERGE_GROUP_PR_REF_PATTERN = re.compile(r"(?:^|/)pr-(\d+)-[^/]+$")
TRANSIENT_GH_API_ERROR_PATTERN = re.compile(
    r"\b(?:HTTP\s+(?:429|500|502|503|504)|(?:secondary )?rate limit|temporarily unavailable|timeout|connection (?:reset|refused))\b",
    re.IGNORECASE,
)
GH_API_RETRY_DELAYS_SECONDS = (1, 2)


def extract_pr_number(head_ref: str) -> int:
    """Extract the current PR number from a GitHub merge-group ref."""
    match = MERGE_GROUP_PR_REF_PATTERN.search(head_ref)
    if match is None:
        message = f"could not extract a pull-request number from merge-group ref {head_ref!r}"
        raise ValueError(message)
    return int(match.group(1))


def split_repository(repository: str) -> tuple[str, str]:
    """Split a GitHub ``owner/repository`` identifier."""
    owner, separator, name = repository.partition("/")
    if not separator or not owner or not name or "/" in name:
        message = f"GITHUB_REPOSITORY must be an owner/repository value, got {repository!r}"
        raise ValueError(message)
    return owner, name


def merge_queue_branch(base_ref: str) -> str:
    """Normalize a merge-group base ref to the branch name GraphQL expects."""
    branch = base_ref.removeprefix("refs/heads/")
    if not branch or branch.startswith("/") or branch.endswith("/"):
        message = f"MERGE_GROUP_BASE_REF must name a branch, got {base_ref!r}"
        raise ValueError(message)
    return branch


def is_transient_gh_api_error(result: subprocess.CompletedProcess[str]) -> bool:
    """Return whether a failed gh invocation can safely be retried."""
    detail = f"{result.stderr}\n{result.stdout}"
    return bool(TRANSIENT_GH_API_ERROR_PATTERN.search(detail))


def run_gh_api(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a read-only gh API command with bounded retries for transient failures."""
    for delay in (*GH_API_RETRY_DELAYS_SECONDS, None):
        result = subprocess.run(  # noqa: S603 - executable is fixed and arguments are passed as a list
            command, capture_output=True, text=True, check=False
        )
        if result.returncode == 0 or delay is None or not is_transient_gh_api_error(result):
            return result
        time.sleep(delay)
    return result


def fetch_merge_group_labels(owner: str, repository: str, branch: str, pull_number: int) -> list[str]:
    """Fetch labels for the current and preceding merge-queue entries."""
    command = [
        "gh",
        "api",
        "graphql",
        "-F",
        f"owner={owner}",
        "-F",
        f"repo={repository}",
        "-F",
        f"branch={branch}",
        "-f",
        "query="
        "query($owner: String!, $repo: String!, $branch: String!) { "
        "repository(owner: $owner, name: $repo) { "
        "mergeQueue(branch: $branch) { "
        "entries(first: 100) { nodes { position pullRequest { number labels(first: 100) { nodes { name } } } } } "
        "} "
        "} "
        "}",
    ]
    try:
        result = run_gh_api(command)
    except FileNotFoundError as exc:
        message = "gh CLI is not installed"
        raise RuntimeError(message) from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no error output"
        message = f"failed to fetch merge-queue labels for PR #{pull_number}: {detail}"
        raise RuntimeError(message)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        message = f"gh returned invalid merge-queue JSON for PR #{pull_number}"
        raise ValueError(message) from exc
    try:
        entries = payload["data"]["repository"]["mergeQueue"]["entries"]["nodes"]
    except (KeyError, TypeError) as exc:
        message = f"gh returned merge-queue entries with an invalid shape for PR #{pull_number}"
        raise ValueError(message) from exc
    if not isinstance(entries, list):
        message = f"gh returned merge-queue entries with an invalid shape for PR #{pull_number}"
        raise ValueError(message)

    if not all(isinstance(entry, dict) for entry in entries):
        message = f"gh returned merge-queue entries with an invalid shape for PR #{pull_number}"
        raise ValueError(message)
    if not all(isinstance(entry.get("pullRequest"), dict) for entry in entries):
        message = f"gh returned merge-queue entries with an invalid shape for PR #{pull_number}"
        raise ValueError(message)

    current_positions = [
        entry.get("position") for entry in entries if entry.get("pullRequest", {}).get("number") == pull_number
    ]
    if len(current_positions) != 1 or not isinstance(current_positions[0], int):
        message = f"could not find queued PR #{pull_number} in the {branch} merge queue"
        raise ValueError(message)

    labels: list[str] = []
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("position"), int)
            or entry["position"] > current_positions[0]
        ):
            continue
        pull_request = entry.get("pullRequest")
        if not isinstance(pull_request, dict):
            message = f"gh returned a merge-queue entry without a pull request for PR #{pull_number}"
            raise ValueError(message)
        labels_connection = pull_request.get("labels")
        label_nodes = labels_connection.get("nodes") if isinstance(labels_connection, dict) else None
        if not isinstance(label_nodes, list) or not all(
            isinstance(label, dict) and isinstance(label.get("name"), str) for label in label_nodes
        ):
            message = f"gh returned labels with an invalid shape for PR #{pull_number}"
            raise ValueError(message)
        labels.extend(label["name"] for label in label_nodes)
    return labels


def write_labels(labels: list[str], output_path: Path) -> None:
    """Write labels as a GitHub Actions step output."""
    serialized_labels = json.dumps(labels, separators=(",", ":"))
    with output_path.open("a", encoding="utf-8") as output:
        output.write(f"labels={serialized_labels}\n")


def require_environment(name: str) -> str:
    """Return a required environment variable or raise a clear error."""
    value = os.environ.get(name)
    if not value:
        message = f"required environment variable {name} is not set"
        raise ValueError(message)
    return value


def main() -> int:
    """Resolve merge-group labels and return a process exit code."""
    try:
        require_environment("GH_TOKEN")
        pull_number = extract_pr_number(require_environment("MERGE_GROUP_HEAD_REF"))
        owner, repository = split_repository(require_environment("GITHUB_REPOSITORY"))
        branch = merge_queue_branch(require_environment("MERGE_GROUP_BASE_REF"))
        labels = fetch_merge_group_labels(owner, repository, branch, pull_number)
        write_labels(labels, Path(require_environment("GITHUB_OUTPUT")))
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
