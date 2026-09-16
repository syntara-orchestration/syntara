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


@pytest.mark.parametrize(
    ("base_ref", "expected_branch"),
    [("refs/heads/devel", "devel"), ("early-access", "early-access")],
)
def test_merge_queue_branch_normalizes_base_ref(base_ref: str, expected_branch: str) -> None:
    assert resolve_labels.merge_queue_branch(base_ref) == expected_branch


@pytest.mark.parametrize("base_ref", ["", "/devel", "devel/"])
def test_merge_queue_branch_rejects_invalid_base_ref(base_ref: str) -> None:
    with pytest.raises(ValueError, match="MERGE_GROUP_BASE_REF"):
        resolve_labels.merge_queue_branch(base_ref)


def test_fetch_merge_group_labels_requests_current_and_preceding_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        return subprocess.CompletedProcess(
            command,
            0,
            '{"data":{"repository":{"mergeQueue":{"entries":{"nodes":['
            '{"position":1,"pullRequest":{"number":505,"labels":{"nodes":[{"name":"breaking-change-approved"}]}}},'
            '{"position":2,"pullRequest":{"number":506,"labels":{"nodes":[{"name":"api"}]}}},'
            '{"position":3,"pullRequest":{"number":507,"labels":{"nodes":[{"name":"unrelated"}]}}}'
            "]}}}}}",
            "",
        )

    monkeypatch.setattr(resolve_labels.subprocess, "run", fake_run)

    assert resolve_labels.fetch_merge_group_labels("syntara-orchestration", "syntara", "devel", 506) == [
        "breaking-change-approved",
        "api",
    ]
    assert captured["command"][:10] == [
        "gh",
        "api",
        "graphql",
        "-F",
        "owner=syntara-orchestration",
        "-F",
        "repo=syntara",
        "-F",
        "branch=devel",
        "-f",
    ]


def test_fetch_merge_group_labels_allows_an_empty_label_list(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            0,
            '{"data":{"repository":{"mergeQueue":{"entries":{"nodes":[{"position":1,"pullRequest":{"number":506,"labels":{"nodes":[]}}}]}}}}}',
            "",
        )

    monkeypatch.setattr(resolve_labels.subprocess, "run", fake_run)

    assert resolve_labels.fetch_merge_group_labels("syntara-orchestration", "syntara", "devel", 506) == []


def test_fetch_merge_group_labels_includes_the_current_entry_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            0,
            '{"data":{"repository":{"mergeQueue":{"entries":{"nodes":['
            '{"position":1,"pullRequest":{"number":505,"labels":{"nodes":[{"name":"api"}]}}},'
            '{"position":2,"pullRequest":{"number":506,"labels":{"nodes":[{"name":"breaking-change-approved"}]}}}'
            "]}}}}}",
            "",
        )

    monkeypatch.setattr(resolve_labels.subprocess, "run", fake_run)

    assert resolve_labels.fetch_merge_group_labels("syntara-orchestration", "syntara", "devel", 506) == [
        "api",
        "breaking-change-approved",
    ]


def test_fetch_merge_group_labels_retries_transient_gh_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    command: list[str] = []
    calls: list[list[str]] = []
    responses = iter(
        [
            subprocess.CompletedProcess(command, 1, "", "HTTP 503: Service Unavailable"),
            subprocess.CompletedProcess(
                command,
                0,
                '{"data":{"repository":{"mergeQueue":{"entries":{"nodes":['
                '{"position":1,"pullRequest":{"number":506,"labels":{"nodes":[]}}}'
                "]}}}}}",
                "",
            ),
        ]
    )
    sleeps: list[int] = []

    def fake_run(run_command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(run_command)
        return next(responses)

    monkeypatch.setattr(resolve_labels.subprocess, "run", fake_run)
    monkeypatch.setattr(resolve_labels.time, "sleep", sleeps.append)

    assert resolve_labels.fetch_merge_group_labels("syntara-orchestration", "syntara", "devel", 506) == []
    assert len(calls) == 2
    assert sleeps == [1]


def test_fetch_merge_group_labels_does_not_retry_permanent_gh_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    sleeps: list[int] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(command, 1, "", "HTTP 401: Bad credentials")

    monkeypatch.setattr(resolve_labels.subprocess, "run", fake_run)
    monkeypatch.setattr(resolve_labels.time, "sleep", sleeps.append)

    with pytest.raises(RuntimeError, match="failed to fetch"):
        resolve_labels.fetch_merge_group_labels("syntara-orchestration", "syntara", "devel", 506)

    assert calls == 1
    assert sleeps == []


def test_fetch_merge_group_labels_stops_after_bounded_transient_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    sleeps: list[int] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(command, 1, "", "HTTP 503: Service Unavailable")

    monkeypatch.setattr(resolve_labels.subprocess, "run", fake_run)
    monkeypatch.setattr(resolve_labels.time, "sleep", sleeps.append)

    with pytest.raises(RuntimeError, match="failed to fetch"):
        resolve_labels.fetch_merge_group_labels("syntara-orchestration", "syntara", "devel", 506)

    assert calls == 3
    assert sleeps == [1, 2]


@pytest.mark.parametrize(
    ("returncode", "stdout", "stderr", "error"),
    [
        (1, "", "not found", "failed to fetch"),
        (0, "not JSON", "", "invalid merge-queue JSON"),
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
        resolve_labels.fetch_merge_group_labels("syntara-orchestration", "syntara", "devel", 506)


def test_main_writes_compact_json_labels_to_github_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output = tmp_path / "github-output"
    monkeypatch.setenv("GH_TOKEN", "test-token")
    monkeypatch.setenv("MERGE_GROUP_HEAD_REF", "gh-readonly-queue/devel/pr-506-bdd2ce3")
    monkeypatch.setenv("MERGE_GROUP_BASE_REF", "refs/heads/devel")
    monkeypatch.setenv("GITHUB_REPOSITORY", "syntara-orchestration/syntara")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr(resolve_labels, "fetch_merge_group_labels", lambda *_args: ["api", "$(not-executed)"])

    assert resolve_labels.main() == 0
    assert output.read_text() == 'labels=["api","$(not-executed)"]\n'


@pytest.mark.parametrize(
    "missing_environment",
    ["GH_TOKEN", "MERGE_GROUP_HEAD_REF", "MERGE_GROUP_BASE_REF", "GITHUB_REPOSITORY", "GITHUB_OUTPUT"],
)
def test_main_fails_closed_when_required_environment_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, missing_environment: str
) -> None:
    output = tmp_path / "github-output"
    environment = {
        "GH_TOKEN": "test-token",
        "MERGE_GROUP_HEAD_REF": "gh-readonly-queue/devel/pr-506-bdd2ce3",
        "MERGE_GROUP_BASE_REF": "refs/heads/devel",
        "GITHUB_REPOSITORY": "syntara-orchestration/syntara",
        "GITHUB_OUTPUT": str(output),
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv(missing_environment)

    assert resolve_labels.main() == 1
    assert not output.exists()
