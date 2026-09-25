"""Tests for the cross-platform Execution Plane development CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
from dev_cli import (
    CommandResult,
    EnvironmentProvider,
    EnvironmentSelectionError,
    LocalEnvironment,
    OpenShiftEnvironment,
    available_local_providers,
    main,
    select_provider,
)


class FakeRunner:
    def __init__(self, *results: CommandResult) -> None:
        self.results = list(results)
        self.commands: list[tuple[str, ...]] = []

    def run(self, args: Sequence[str]) -> CommandResult:
        self.commands.append(tuple(args))
        return self.results.pop(0) if self.results else CommandResult(0)


def executable_checker(*installed: str) -> Callable[[str], str | None]:
    """Return a typed executable lookup for CLI tests."""
    installed_set = set(installed)
    return lambda name: name if name in installed_set else None


def test_auto_selects_the_only_available_local_provider() -> None:
    assert select_provider("auto", [EnvironmentProvider.KIND]) is LocalEnvironment


def test_auto_rejects_ambiguous_local_providers() -> None:
    with pytest.raises(EnvironmentSelectionError, match="both kind and minikube"):
        select_provider("auto", [EnvironmentProvider.KIND, EnvironmentProvider.MINIKUBE])


def test_auto_explains_how_to_install_a_local_provider_when_none_is_available() -> None:
    with pytest.raises(EnvironmentSelectionError, match="install kind or minikube"):
        select_provider("auto", [])


def test_explicit_openshift_selects_remote_environment() -> None:
    assert select_provider("openshift", []) is OpenShiftEnvironment


def test_remote_openshift_does_not_support_local_lifecycle_operations() -> None:
    with pytest.raises(EnvironmentSelectionError, match="does not support 'up'"):
        OpenShiftEnvironment.ensure_lifecycle_operation_allowed("up")


def test_detects_installed_local_providers_without_shell_commands() -> None:
    assert available_local_providers(executable_checker("kind", "oc")) == [EnvironmentProvider.KIND]


def test_kind_up_creates_the_requested_cluster() -> None:
    runner = FakeRunner()

    assert main(["--provider", "kind", "up"], runner=runner, executable_exists=executable_checker("kind")) == 0

    assert runner.commands == [("kind", "create", "cluster", "--name", "execution-plane")]


def test_mixed_case_provider_environment_value_is_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EP_DEV_PROVIDER", "KIND")
    runner = FakeRunner()

    assert main(["up"], runner=runner, executable_exists=executable_checker("kind")) == 0

    assert runner.commands == [("kind", "create", "cluster", "--name", "execution-plane")]


def test_minikube_down_stops_and_deletes_the_requested_profile() -> None:
    runner = FakeRunner()

    assert (
        main(["--provider", "minikube", "down"], runner=runner, executable_exists=executable_checker("minikube")) == 0
    )

    assert runner.commands == [
        ("minikube", "stop", "--profile", "execution-plane"),
        ("minikube", "delete", "--profile", "execution-plane"),
    ]


def test_kind_status_lists_clusters() -> None:
    runner = FakeRunner(CommandResult(0, "execution-plane\n"))

    assert main(["--provider", "kind", "status"], runner=runner, executable_exists=executable_checker("kind")) == 0

    assert runner.commands == [("kind", "get", "clusters")]


def test_kind_status_fails_when_the_requested_cluster_is_missing() -> None:
    runner = FakeRunner(CommandResult(0, "other-cluster\n"))

    assert main(["--provider", "kind", "status"], runner=runner, executable_exists=executable_checker("kind")) == 1


def test_local_doctor_checks_the_selected_environment() -> None:
    runner = FakeRunner(CommandResult(0, "execution-plane\n"))

    assert main(["--provider", "kind", "doctor"], runner=runner, executable_exists=executable_checker("kind")) == 0

    assert runner.commands == [("kind", "get", "clusters")]


def test_local_connect_is_rejected() -> None:
    runner = FakeRunner()

    assert main(["--provider", "kind", "connect"], runner=runner, executable_exists=executable_checker("kind")) == 1

    assert runner.commands == []


def test_minikube_reset_recreates_the_requested_profile() -> None:
    runner = FakeRunner()

    assert (
        main(
            ["--provider", "minikube", "reset", "--yes"],
            runner=runner,
            executable_exists=executable_checker("minikube"),
        )
        == 0
    )

    assert runner.commands == [
        ("minikube", "delete", "--profile", "execution-plane"),
        ("minikube", "start", "--profile", "execution-plane"),
    ]


def test_openshift_connect_validates_the_selected_context_and_namespace() -> None:
    runner = FakeRunner(CommandResult(0, "developer\n"), CommandResult(0, "execution-plane\n"))

    assert (
        main(
            [
                "--provider",
                "openshift",
                "--context",
                "remote-dev",
                "--namespace",
                "execution-plane",
                "connect",
            ],
            runner=runner,
            executable_exists=executable_checker("oc"),
        )
        == 0
    )

    assert runner.commands == [
        ("oc", "whoami", "--context", "remote-dev"),
        ("oc", "get", "project", "execution-plane", "--context", "remote-dev"),
    ]


def test_openshift_connect_fails_when_namespace_is_not_accessible() -> None:
    runner = FakeRunner(CommandResult(0, "developer\n"), CommandResult(1, stderr="forbidden"))

    assert (
        main(
            ["--provider", "openshift", "--context", "remote-dev", "--namespace", "execution-plane", "connect"],
            runner=runner,
            executable_exists=executable_checker("oc"),
        )
        == 1
    )
