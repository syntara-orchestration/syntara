#!/usr/bin/env python3
"""Resolve the current merge-group pull request's labels for GitHub Actions.

The merge queue names its candidate ref with a final ``pr-<number>-<suffix>``
component. This script extracts that PR number, fetches only that pull request,
and writes its labels as a compact JSON array to ``GITHUB_OUTPUT``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

MERGE_GROUP_PR_REF_PATTERN = re.compile(r"(?:^|/)pr-(\d+)-[^/]+$")


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


def fetch_labels(owner: str, repository: str, pull_number: int) -> list[str]:
    """Fetch labels for one pull request using the GitHub CLI."""
    command = [
        "gh",
        "api",
        f"repos/{owner}/{repository}/pulls/{pull_number}",
        "--jq",
        "[.labels[].name]",
    ]
    try:
        result = subprocess.run(  # noqa: S603 - executable is fixed and arguments are passed as a list
            command, capture_output=True, text=True, check=False
        )
    except FileNotFoundError as exc:
        message = "gh CLI is not installed"
        raise RuntimeError(message) from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no error output"
        message = f"failed to fetch labels for PR #{pull_number}: {detail}"
        raise RuntimeError(message)
    try:
        labels = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        message = f"gh returned invalid label JSON for PR #{pull_number}"
        raise ValueError(message) from exc
    if not isinstance(labels, list) or not all(isinstance(label, str) for label in labels):
        message = f"gh returned labels with an invalid shape for PR #{pull_number}"
        raise ValueError(message)
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
        labels = fetch_labels(owner, repository, pull_number)
        write_labels(labels, Path(require_environment("GITHUB_OUTPUT")))
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
