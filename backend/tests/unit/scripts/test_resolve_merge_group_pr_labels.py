"""Tests for backend/scripts/openapi/resolve-merge-group-pr-labels.py."""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[3] / "scripts" / "openapi"
sys.path.insert(0, str(SCRIPT_DIR))

resolve_labels = importlib.import_module("resolve-merge-group-pr-labels")


def test_extract_pr_number_accepts_merge_queue_ref() -> None:
    assert resolve_labels.extract_pr_number("gh-readonly-queue/devel/pr-506-bdd2ce3") == 506


@pytest.mark.parametrize("head_ref", ["", "gh-readonly-queue/devel/pr-nope-sha", "devel/pr-506", "pr-506-sha/extra"])
def test_extract_pr_number_rejects_invalid_merge_queue_refs(head_ref: str) -> None:
    with pytest.raises(ValueError, match="could not extract"):
        resolve_labels.extract_pr_number(head_ref)


@pytest.mark.parametrize("repository", ["", "syntara", "/syntara", "owner/", "owner/repo/extra"])
def test_split_repository_rejects_invalid_repository(repository: str) -> None:
    with pytest.raises(ValueError, match="GITHUB_REPOSITORY"):
        resolve_labels.split_repository(repository)


def test_fetch_labels_requests_only_the_parsed_pull_request(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        return subprocess.CompletedProcess(command, 0, '["breaking-change-approved","api"]', "")

    monkeypatch.setattr(resolve_labels.subprocess, "run", fake_run)

    assert resolve_labels.fetch_labels("syntara-orchestration", "syntara", 506) == ["breaking-change-approved", "api"]
    assert captured["command"] == [
        "gh",
        "api",
        "repos/syntara-orchestration/syntara/pulls/506",
        "--jq",
        "[.labels[].name]",
    ]


def test_fetch_labels_allows_an_empty_label_list(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, "[]", "")

    monkeypatch.setattr(resolve_labels.subprocess, "run", fake_run)

    assert resolve_labels.fetch_labels("syntara-orchestration", "syntara", 506) == []


@pytest.mark.parametrize(
    ("returncode", "stdout", "stderr", "error"),
    [
        (1, "", "not found", "failed to fetch"),
        (0, "not JSON", "", "invalid label JSON"),
        (0, '{"name": "api"}', "", "invalid shape"),
    ],
)
def test_fetch_labels_rejects_failed_or_invalid_responses(
    monkeypatch: pytest.MonkeyPatch, returncode: int, stdout: str, stderr: str, error: str
) -> None:
    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, returncode, stdout, stderr)

    monkeypatch.setattr(resolve_labels.subprocess, "run", fake_run)

    with pytest.raises((RuntimeError, ValueError), match=error):
        resolve_labels.fetch_labels("syntara-orchestration", "syntara", 506)


def test_main_writes_compact_json_labels_to_github_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output = tmp_path / "github-output"
    monkeypatch.setenv("GH_TOKEN", "test-token")
    monkeypatch.setenv("MERGE_GROUP_HEAD_REF", "gh-readonly-queue/devel/pr-506-bdd2ce3")
    monkeypatch.setenv("GITHUB_REPOSITORY", "syntara-orchestration/syntara")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr(resolve_labels, "fetch_labels", lambda *_args: ["api", "$(not-executed)"])

    assert resolve_labels.main() == 0
    assert output.read_text() == 'labels=["api","$(not-executed)"]\n'


@pytest.mark.parametrize(
    "missing_environment",
    ["GH_TOKEN", "MERGE_GROUP_HEAD_REF", "GITHUB_REPOSITORY", "GITHUB_OUTPUT"],
)
def test_main_fails_closed_when_required_environment_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, missing_environment: str
) -> None:
    output = tmp_path / "github-output"
    environment = {
        "GH_TOKEN": "test-token",
        "MERGE_GROUP_HEAD_REF": "gh-readonly-queue/devel/pr-506-bdd2ce3",
        "GITHUB_REPOSITORY": "syntara-orchestration/syntara",
        "GITHUB_OUTPUT": str(output),
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv(missing_environment)

    assert resolve_labels.main() == 1
    assert not output.exists()
