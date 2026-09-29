"""Cross-platform local and remote Kubernetes environment CLI."""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from ao_registration import register_integration_record
from execution_plane.cluster.cluster_registry import (
    ClusterRegistry,
    NoopDiscoveryMechanism,
)
from execution_plane.cluster.cluster_store import ClusterStore
from execution_plane.execution_target.execution_target_registry import ExecutionTargetRegistry
from execution_plane.execution_target.execution_target_store import ExecutionTargetStore
from execution_plane.models.cluster import ClusterStatus, ClusterType
from execution_plane.models.work_item import WorkItem
from execution_plane.work_store import WorkStore
from sqlalchemy import delete
from sqlmodel import col

DEFAULT_DATABASE_URL = "postgresql+asyncpg://admin:admin@localhost:5432/syntara_api"
DEFAULT_LOCAL_NAMESPACE = "execution-plane"
CLI_ACTOR_ID = uuid.UUID(int=0)


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


@dataclass(frozen=True)
class EnvironmentDetails:
    """Connection details used to register a Kubernetes environment."""

    provider: EnvironmentProvider
    name: str
    endpoint: str
    namespace: str
    api_key: str
    labels: dict[str, str]


_CLUSTER_TYPE_BY_PROVIDER = {
    EnvironmentProvider.OPENSHIFT: ClusterType.OPENSHIFT,
    EnvironmentProvider.KIND: ClusterType.OPENSHIFT,
    EnvironmentProvider.MINIKUBE: ClusterType.OPENSHIFT,
    EnvironmentProvider.AUTO: ClusterType.OPENSHIFT,
}


def _cluster_type_for_provider(provider: EnvironmentProvider) -> ClusterType:
    """Map a CLI environment provider onto the persisted Cluster type."""
    return _CLUSTER_TYPE_BY_PROVIDER[provider]


async def _remove_target_work_items(work_store: WorkStore, target_id: uuid.UUID) -> None:
    """Delete all WorkItems for a target during a local CLI shutdown."""
    async with work_store._session_context() as session:  # noqa: SLF001
        try:
            await session.execute(delete(WorkItem).where(col(WorkItem.execution_target_id) == target_id))
            await session.commit()
        except Exception:
            await session.rollback()
            raise


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
    parser.add_argument("--namespace", default=os.environ.get("EP_DEV_NAMESPACE"))
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


def _require_output(result: CommandResult, description: str) -> str:
    """Return command output or reject an unusable connection detail."""
    value = result.stdout.strip()
    if not value:
        raise EnvironmentSelectionError(f"{description} returned no value")
    return value


def _collect_openshift_details(
    runner: CommandRunner, cluster: str, context: str | None, namespace: str
) -> EnvironmentDetails:
    """Collect the OpenShift API endpoint and current bearer token."""
    context_args = _context_args(context)
    endpoint = _require_output(
        _run_command(runner, ["oc", "whoami", "--show-server", *context_args]),
        "oc whoami --show-server",
    )
    api_key = _require_output(
        _run_command(runner, ["oc", "whoami", "--show-token", *context_args]),
        "oc whoami --show-token",
    )
    labels = {"provider": EnvironmentProvider.OPENSHIFT.value, "cluster": cluster}
    if context:
        labels["context"] = context
    return EnvironmentDetails(EnvironmentProvider.OPENSHIFT, cluster, endpoint, namespace, api_key, labels)


def _ensure_local_namespace(runner: CommandRunner, namespace: str, context: str | None) -> None:
    """Create a local Kubernetes namespace when it is not present."""
    context_args = _context_args(context)
    result = runner.run(["kubectl", "get", "namespace", namespace, *context_args])
    if result.returncode:
        _run_command(runner, ["kubectl", "create", "namespace", namespace, *context_args])


def _collect_local_details(
    runner: CommandRunner,
    provider: EnvironmentProvider,
    cluster: str,
    namespace: str,
    context: str | None,
) -> EnvironmentDetails:
    """Collect the active kubeconfig endpoint and preserve its credentials."""
    _ensure_local_namespace(runner, namespace, context)
    context_args = _context_args(context)
    endpoint = _require_output(
        _run_command(
            runner,
            [
                "kubectl",
                "config",
                "view",
                "--minify",
                "--raw",
                *context_args,
                "-o",
                "jsonpath={.clusters[0].cluster.server}",
            ],
        ),
        "kubectl config endpoint lookup",
    )
    kubeconfig = _require_output(
        _run_command(runner, ["kubectl", "config", "view", "--minify", "--raw", *context_args]),
        "kubectl config credential lookup",
    )
    labels = {"provider": provider.value, "cluster": cluster}
    if context:
        labels["context"] = context
    return EnvironmentDetails(provider, cluster, endpoint, namespace, kubeconfig, labels)


async def _register_environment_record(details: EnvironmentDetails, database_url: str) -> None:
    """Create or refresh the Cluster and its default target."""
    async with (
        ClusterStore.from_database_url(database_url) as cluster_store,
        ExecutionTargetStore.from_database_url(database_url) as target_store,
    ):
        target_registry = ExecutionTargetRegistry(target_store)
        cluster_registry = ClusterRegistry(cluster_store, target_registry, NoopDiscoveryMechanism())
        existing = await cluster_registry.get_by_name(details.name)
        if existing is not None and existing.status is not ClusterStatus.DRAINING:
            await cluster_registry.sync_update(
                existing.id,
                updated_by=CLI_ACTOR_ID,
                endpoint=details.endpoint,
                api_key=details.api_key,
                namespace=details.namespace,
            )
        else:
            await cluster_registry.provision(
                details.name,
                details.endpoint,
                details.api_key,
                details.namespace,
                CLI_ACTOR_ID,
                details.labels,
                cluster_type=_cluster_type_for_provider(details.provider),
            )


async def _register_environment_and_integration(details: EnvironmentDetails, database_url: str) -> None:
    """Register the Cluster/ExecutionTarget and then the Credential/Integration."""
    await _register_environment_record(details, database_url)
    await register_integration_record(
        name=details.name,
        endpoint=details.endpoint,
        namespace=details.namespace,
        api_key=details.api_key,
        actor_id=CLI_ACTOR_ID,
        database_url=database_url,
    )


async def _remove_environment_record(provider: EnvironmentProvider, cluster_name: str, database_url: str) -> None:
    """Remove the local CLI registration matching the selected provider and cluster."""
    async with (
        ClusterStore.from_database_url(database_url) as cluster_store,
        ExecutionTargetStore.from_database_url(database_url) as target_store,
        WorkStore.from_database_url(database_url) as work_store,
    ):
        cluster = next(
            (
                candidate
                for candidate in await cluster_store.list()
                if candidate.name == cluster_name
                and candidate.labels.get("provider") == provider.value
                and candidate.labels.get("cluster") == cluster_name
            ),
            None,
        )
        if cluster is not None:
            await cluster_store.request_delete(cluster.id, CLI_ACTOR_ID)
            for target in await target_store.list(cluster_id=cluster.id):
                await _remove_target_work_items(work_store, target.id)
                await target_store.finalize_delete(target.id)
            await cluster_store.finalize_delete(cluster.id)
            if await cluster_store.get(cluster.id) is not None:
                raise EnvironmentSelectionError(f"Cluster '{cluster.name}' could not be removed")


def _register_environment(
    *,
    provider: EnvironmentProvider,
    cluster: str,
    namespace: str,
    context: str | None,
    runner: CommandRunner,
) -> None:
    """Resolve provider credentials and persist the selected environment."""
    if provider is EnvironmentProvider.OPENSHIFT:
        details = _collect_openshift_details(runner, cluster, context, namespace)
    else:
        if not shutil.which("kubectl"):
            raise EnvironmentSelectionError("kubectl is not available; install kubectl")
        details = _collect_local_details(runner, provider, cluster, namespace, context)
    database_url = os.environ.get("APP_DATABASE_URL") or os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL
    try:
        asyncio.run(_register_environment_and_integration(details, database_url))
    except EnvironmentSelectionError:
        raise
    except Exception as exc:
        raise EnvironmentSelectionError(f"failed to register the {provider.value} environment: {exc}") from exc


def _remove_environment(*, provider: EnvironmentProvider, cluster: str) -> None:
    """Remove a local CLI registration from the development database."""
    database_url = os.environ.get("APP_DATABASE_URL") or os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL
    try:
        asyncio.run(_remove_environment_record(provider, cluster, database_url))
    except Exception as exc:
        raise EnvironmentSelectionError(f"failed to remove the {provider.value} environment: {exc}") from exc


def _run_local_environment(
    provider: EnvironmentProvider,
    command: str,
    cluster: str,
    namespace: str,
    context: str | None,
    confirmed: bool,
    runner: CommandRunner,
) -> None:
    """Run a local provider lifecycle command and synchronize its registration."""
    if command == "connect":
        raise EnvironmentSelectionError("connect is only supported for remote OpenShift; use 'status' locally")
    print(f"Local Kubernetes provider selected: {provider.value}")
    _run_local_command(runner, provider, command, cluster, confirmed)
    if command in {"up", "reset"}:
        _register_environment(
            provider=provider,
            cluster=cluster,
            namespace=namespace,
            context=context,
            runner=runner,
        )
    elif command == "down":
        _remove_environment(provider=provider, cluster=cluster)


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
            if not args.namespace:
                raise EnvironmentSelectionError("OpenShift requires --namespace or EP_DEV_NAMESPACE")
            if args.command in {"up", "down", "reset"}:
                environment.ensure_lifecycle_operation_allowed(args.command)
            if not executable_exists("oc"):
                raise EnvironmentSelectionError("oc is not available; install the OpenShift CLI and log in")
            if args.command in {"connect", "doctor", "status"}:
                _run_openshift_check(command_runner, args.context, args.namespace)
                print(f"Remote OpenShift is reachable in namespace {args.namespace}.")
                if args.command == "connect":
                    _register_environment(
                        provider=EnvironmentProvider.OPENSHIFT,
                        cluster=args.cluster,
                        namespace=args.namespace,
                        context=args.context,
                        runner=command_runner,
                    )
            return 0
        provider = EnvironmentProvider(selected) if selected != EnvironmentProvider.AUTO else local[0]
        namespace = args.namespace or DEFAULT_LOCAL_NAMESPACE
        _run_local_environment(provider, args.command, args.cluster, namespace, args.context, args.yes, command_runner)
        return 0
    except EnvironmentSelectionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
