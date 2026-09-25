"""Cross-platform local and remote Kubernetes environment CLI."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class EnvironmentSelectionError(RuntimeError):
    """Raised when the requested Kubernetes environment cannot be selected."""


class EnvironmentProvider(StrEnum):
    """Supported Kubernetes environment providers."""

    AUTO = "auto"
    KIND = "kind"
    MINIKUBE = "minikube"
    OPENSHIFT = "openshift"


class LocalEnvironment:
    """Marker for local Kubernetes providers."""

    @staticmethod
    def ensure_lifecycle_operation_allowed(operation: str) -> None:
        """Allow local lifecycle operations."""


class OpenShiftEnvironment:
    """Marker for a remote OpenShift environment."""

    @staticmethod
    def ensure_lifecycle_operation_allowed(operation: str) -> None:
        """Reject local lifecycle operations for remote OpenShift."""
        raise EnvironmentSelectionError(f"remote OpenShift does not support '{operation}'")


def select_provider(
    requested: str, available: Sequence[EnvironmentProvider]
) -> type[LocalEnvironment | OpenShiftEnvironment]:
    """Select an environment family from an explicit request or local providers."""
    try:
        provider = EnvironmentProvider(requested.lower())
    except ValueError as exc:
        raise EnvironmentSelectionError(f"unsupported environment provider: {requested}") from exc

    if provider is EnvironmentProvider.OPENSHIFT:
        return OpenShiftEnvironment
    if provider is EnvironmentProvider.KIND:
        if provider not in available:
            raise EnvironmentSelectionError("kind is not available; install kind or choose another provider")
        return LocalEnvironment
    if provider is EnvironmentProvider.MINIKUBE:
        if provider not in available:
            raise EnvironmentSelectionError("minikube is not available; install minikube or choose another provider")
        return LocalEnvironment
    if len(available) == 1:
        return LocalEnvironment
    if len(available) > 1:
        raise EnvironmentSelectionError("both kind and minikube are available; choose one with --provider")
    raise EnvironmentSelectionError("neither kind nor minikube is available; install kind or minikube")


@dataclass(frozen=True)
class CommandResult:
    """Portable result returned by an external command."""

    returncode: int
    stdout: str = ""
    stderr: str = ""


class CommandRunner(Protocol):
    """Run an external command without invoking a shell."""

    def run(self, args: Sequence[str]) -> CommandResult:
        """Run argv and return its result."""


class SubprocessRunner:
    """Run commands through Python's platform-neutral subprocess API."""

    def run(self, args: Sequence[str]) -> CommandResult:
        """Run argv without shell interpretation."""
        completed = subprocess.run(args, capture_output=True, text=True, check=False)  # noqa: S603
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)


ExecutableExists = Callable[[str], str | None]


def available_local_providers(executable_exists: ExecutableExists = shutil.which) -> list[EnvironmentProvider]:
    """Return installed local Kubernetes providers in stable order."""
    providers: list[EnvironmentProvider] = []
    if executable_exists("kind"):
        providers.append(EnvironmentProvider.KIND)
    if executable_exists("minikube"):
        providers.append(EnvironmentProvider.MINIKUBE)
    return providers


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage the Kubernetes environment used by Execution Plane development."
    )
    parser.add_argument(
        "--provider",
        choices=[provider.value for provider in EnvironmentProvider],
        default=os.environ.get("EP_DEV_PROVIDER", EnvironmentProvider.AUTO.value),
        help="Environment provider: auto, kind, minikube, or openshift.",
    )
    parser.add_argument("--cluster", default=os.environ.get("EP_DEV_CLUSTER", "execution-plane"))
    parser.add_argument("--namespace", default=os.environ.get("EP_DEV_NAMESPACE", "execution-plane"))
    parser.add_argument("--context", default=os.environ.get("EP_DEV_CONTEXT"))
    parser.add_argument("command", choices=["doctor", "status", "up", "down", "reset", "connect"])
    parser.add_argument("--yes", action="store_true", help="Confirm destructive local reset operations.")
    return parser


def _context_args(context: str | None) -> list[str]:
    return ["--context", context] if context else []


def _run_command(runner: CommandRunner, args: list[str]) -> CommandResult:
    result = runner.run(args)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or f"command exited with status {result.returncode}"
        raise EnvironmentSelectionError(f"{' '.join(args)} failed: {detail}")
    return result


def _run_openshift_check(runner: CommandRunner, context: str | None, namespace: str) -> None:
    context_args = _context_args(context)
    _run_command(runner, ["oc", "whoami", *context_args])
    _run_command(runner, ["oc", "get", "project", namespace, *context_args])


def _run_kind_command(runner: CommandRunner, command: str, cluster: str) -> None:
    if command in {"doctor", "status"}:
        result = _run_command(runner, ["kind", "get", "clusters"])
        clusters = {line.strip() for line in result.stdout.splitlines() if line.strip()}
        if cluster not in clusters:
            raise EnvironmentSelectionError(f"kind cluster '{cluster}' was not found; run 'up' to create it")
        print(f"kind cluster '{cluster}' is available.")
    if command in {"down", "reset"}:
        _run_command(runner, ["kind", "delete", "cluster", "--name", cluster])
    if command in {"up", "reset"}:
        _run_command(runner, ["kind", "create", "cluster", "--name", cluster])


def _run_minikube_command(runner: CommandRunner, command: str, profile: str) -> None:
    if command in {"doctor", "status"}:
        result = _run_command(runner, ["minikube", "status", "--profile", profile])
        print(result.stdout.strip() or f"minikube profile '{profile}' is available.")
    if command == "down":
        _run_command(runner, ["minikube", "stop", "--profile", profile])
        _run_command(runner, ["minikube", "delete", "--profile", profile])
    if command == "reset":
        _run_command(runner, ["minikube", "delete", "--profile", profile])
    if command in {"up", "reset"}:
        _run_command(runner, ["minikube", "start", "--profile", profile])


def _run_local_command(
    runner: CommandRunner,
    provider: EnvironmentProvider,
    command: str,
    cluster: str,
    confirmed: bool,
) -> None:
    if command == "reset" and not confirmed:
        raise EnvironmentSelectionError("reset is destructive; repeat with --yes")
    if provider is EnvironmentProvider.KIND:
        _run_kind_command(runner, command, cluster)
    else:
        _run_minikube_command(runner, command, cluster)


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: CommandRunner | None = None,
    executable_exists: ExecutableExists = shutil.which,
) -> int:
    """Run the development environment CLI."""
    args = _build_parser().parse_args(argv)
    selected = args.provider.lower()
    command_runner = runner or SubprocessRunner()
    local = available_local_providers(executable_exists)
    try:
        environment = select_provider(selected, local)
        if environment is OpenShiftEnvironment:
            if args.command in {"up", "down", "reset"}:
                environment.ensure_lifecycle_operation_allowed(args.command)
            if not executable_exists("oc"):
                raise EnvironmentSelectionError("oc is not available; install the OpenShift CLI and log in")
            if args.command in {"connect", "doctor", "status"}:
                _run_openshift_check(command_runner, args.context, args.namespace)
                print(f"Remote OpenShift is reachable in namespace {args.namespace}.")
            return 0
        provider = EnvironmentProvider(selected) if selected != EnvironmentProvider.AUTO else local[0]
        if args.command == "connect":
            raise EnvironmentSelectionError("connect is only supported for remote OpenShift; use 'status' locally")
        print(f"Local Kubernetes provider selected: {provider.value}")
        _run_local_command(command_runner, provider, args.command, args.cluster, args.yes)
        return 0
    except EnvironmentSelectionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
