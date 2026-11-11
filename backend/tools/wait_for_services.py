#!/usr/bin/env python3
"""Wait until compose services are running and healthy.

`make services-run` starts the stack with `podman-compose up -d`. That command
returns as soon as the last container starts, so services started late (the
Temporal workers and MCP servers) may still be starting, and a service that
never becomes healthy goes unreported. This tool polls the container engine
until every requested service is ready, and exits non-zero with diagnostics if
one is not ready before the timeout.

A service is ready when each of its containers is running and, if it defines a
healthcheck, reports healthy.

podman-compose's own `up --wait` is not used because, in podman-compose 1.6,
it exits 0 when `--wait-timeout` expires and it waits on every container in the
project rather than only the requested services.

Usage:
    uv run python tools/wait_for_services.py --project syntara database redis temporal
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TextIO

PROJECT_LABEL = "com.docker.compose.project"
SERVICE_LABEL = "com.docker.compose.service"

DEFAULT_TIMEOUT_SECONDS = 300.0
DEFAULT_INTERVAL_SECONDS = 3.0
PROGRESS_EVERY_SECONDS = 30.0
HEALTH_OUTPUT_LIMIT = 500

# Restart policies under which an exited container stays exited.
_NO_RESTART_POLICIES = frozenset({"", "no"})
_STOPPED_STATES = frozenset({"exited", "dead", "stopped"})

Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


class EngineError(RuntimeError):
    """The container engine could not be queried."""


class Readiness(StrEnum):
    """Whether a container or service is ready, still coming up, or stuck."""

    READY = "ready"
    WAITING = "waiting"
    FAILED = "failed"  # Will not become ready without intervention.


@dataclass(frozen=True)
class ContainerStatus:
    """Readiness of one container, with the details shown on failure."""

    name: str
    readiness: Readiness
    detail: str
    has_healthcheck: bool = False
    health_output: str | None = None


@dataclass(frozen=True)
class ServiceStatus:
    """Readiness of a compose service across all of its containers."""

    service: str
    readiness: Readiness
    detail: str
    containers: tuple[ContainerStatus, ...] = ()


def _run(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
    # The command is built from our own arguments, never from external input.
    return subprocess.run(list(cmd), capture_output=True, text=True, check=False)  # noqa: S603


class Engine:
    """Thin wrapper over the podman (or docker) CLI."""

    def __init__(self, binary: str = "podman", runner: Runner = _run) -> None:
        """Use ``binary`` as the engine CLI; ``runner`` executes commands (replaceable in tests)."""
        self.binary = binary
        self._runner = runner

    @property
    def supports_manual_healthcheck(self) -> bool:
        """Whether the engine can run a healthcheck on demand (podman only)."""
        return self.binary.rsplit("/", 1)[-1] == "podman"

    def _check(self, args: Sequence[str]) -> str:
        cmd = [self.binary, *args]
        try:
            result = self._runner(cmd)
        except OSError as exc:
            raise EngineError(f"could not run {' '.join(cmd)}: {exc}") from exc
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "").strip()
            raise EngineError(f"{' '.join(cmd)} failed (exit {result.returncode}): {message}")
        return result.stdout

    def find_containers(self, project: str, service: str) -> list[str]:
        """Return the names of all containers (any state) of ``service`` in ``project``."""
        out = self._check(
            [
                "ps",
                "--all",
                "--filter",
                f"label={PROJECT_LABEL}={project}",
                "--filter",
                f"label={SERVICE_LABEL}={service}",
                "--format",
                "{{.Names}}",
            ]
        )
        return sorted(line.strip() for line in out.splitlines() if line.strip())

    def inspect(self, container: str) -> dict[str, Any]:
        """Return the ``inspect`` object for ``container``."""
        out = self._check(["inspect", container])
        try:
            data = json.loads(out)
        except json.JSONDecodeError as exc:
            raise EngineError(f"{self.binary} inspect {container} returned invalid JSON") from exc
        if isinstance(data, list):
            data = data[0] if data else {}
        if not isinstance(data, dict):
            raise EngineError(f"{self.binary} inspect {container} returned unexpected data")
        return data

    def trigger_healthcheck(self, container: str) -> None:
        """Run the container's healthcheck now instead of waiting for its timer.

        Some podman setups (for example ``events_logger=file``) never fire the
        healthcheck timer, so the status would stay ``starting`` forever. The
        result is ignored: the next ``inspect`` reports the new status.
        """
        if not self.supports_manual_healthcheck:
            return
        try:
            self._runner([self.binary, "healthcheck", "run", container])
        except OSError:
            return


def _health(state: dict[str, Any]) -> dict[str, Any]:
    health = state.get("Health") or state.get("Healthcheck") or {}
    return health if isinstance(health, dict) else {}


def _last_health_output(health: dict[str, Any]) -> str | None:
    log = health.get("Log") or []
    if not isinstance(log, list) or not log:
        return None
    last = log[-1]
    if not isinstance(last, dict):
        return None
    output = str(last.get("Output") or "").strip()
    if not output:
        return None
    if len(output) > HEALTH_OUTPUT_LIMIT:
        output = output[:HEALTH_OUTPUT_LIMIT] + "…"
    return output


def classify_container(name: str, data: dict[str, Any]) -> ContainerStatus:
    """Decide whether one container is ready from its ``inspect`` data."""
    state = data.get("State") or {}
    status = str(state.get("Status") or "unknown").lower()
    health = _health(state)
    health_status = str(health.get("Status") or "").lower()
    config_healthcheck = (data.get("Config") or {}).get("Healthcheck")
    has_healthcheck = bool(health_status) or bool(config_healthcheck)
    health_output = _last_health_output(health)

    if status == "running":
        if not has_healthcheck:
            return ContainerStatus(name, Readiness.READY, "running (no healthcheck)")
        if health_status == "healthy":
            return ContainerStatus(name, Readiness.READY, "healthy", has_healthcheck=True)
        return ContainerStatus(
            name,
            Readiness.WAITING,
            health_status or "starting",
            has_healthcheck=True,
            health_output=health_output,
        )

    if status in _STOPPED_STATES:
        exit_code = state.get("ExitCode")
        detail = f"{status} (exit code {exit_code})"
        restart_policy = str(((data.get("HostConfig") or {}).get("RestartPolicy") or {}).get("Name") or "")
        if restart_policy in _NO_RESTART_POLICIES:
            return ContainerStatus(name, Readiness.FAILED, detail, has_healthcheck, health_output)
        return ContainerStatus(
            name,
            Readiness.WAITING,
            f"{detail}, waiting for restart policy '{restart_policy}'",
            has_healthcheck,
            health_output,
        )

    # created, configured, restarting, paused, ...
    return ContainerStatus(name, Readiness.WAITING, status, has_healthcheck, health_output)


def check_service(engine: Engine, project: str, service: str) -> ServiceStatus:
    """Check every container that belongs to ``service`` in ``project``."""
    try:
        names = engine.find_containers(project, service)
    except EngineError as exc:
        return ServiceStatus(service, Readiness.FAILED, str(exc))
    if not names:
        return ServiceStatus(service, Readiness.WAITING, "no container")

    containers: list[ContainerStatus] = []
    for name in names:
        try:
            container = classify_container(name, engine.inspect(name))
        except EngineError as exc:
            # The container can disappear between ps and inspect while it is
            # being recreated, so treat this as transient.
            container = ContainerStatus(name, Readiness.WAITING, f"not inspectable: {exc}")
        if container.readiness is Readiness.WAITING and container.has_healthcheck:
            engine.trigger_healthcheck(name)
        containers.append(container)

    for readiness in (Readiness.FAILED, Readiness.WAITING):
        blocking = [c for c in containers if c.readiness is readiness]
        if blocking:
            detail = ", ".join(f"{c.name}: {c.detail}" for c in blocking) if len(names) > 1 else blocking[0].detail
            return ServiceStatus(service, readiness, detail, tuple(containers))
    return ServiceStatus(
        service, Readiness.READY, containers[0].detail if len(names) == 1 else "all healthy", tuple(containers)
    )


def _report(statuses: Sequence[ServiceStatus], engine: Engine, out: TextIO) -> None:
    for status in statuses:
        print(f"   • {status.service}: {status.detail}", file=out)
        for container in status.containers:
            if container.readiness is Readiness.READY:
                continue
            if container.health_output:
                print(f"     last healthcheck output: {container.health_output}", file=out)
            print(f"     logs: {engine.binary} logs {container.name}", file=out)


def wait_for_services(
    engine: Engine,
    project: str,
    services: Sequence[str],
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    interval: float = DEFAULT_INTERVAL_SECONDS,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    out: TextIO | None = None,
) -> int:
    """Poll until every service is ready. Returns a process exit code."""
    out = out or sys.stdout
    services = list(dict.fromkeys(services))
    start = clock()
    deadline = start + timeout
    next_progress = start + PROGRESS_EVERY_SECONDS
    pending = list(services)
    last: dict[str, ServiceStatus] = {}

    print(f"⏳ Waiting up to {timeout:.0f}s for {len(services)} services to be healthy...", file=out)
    while True:
        for service in list(pending):
            status = check_service(engine, project, service)
            if status.readiness is Readiness.READY:
                print(f"   ✅ {service}: {status.detail} ({clock() - start:.0f}s)", file=out)
                pending.remove(service)
                last.pop(service, None)
            elif status.readiness is Readiness.FAILED:
                print(f"❌ {service} will not become healthy:", file=out)
                _report([status], engine, out)
                return 1
            else:
                last[service] = status

        if not pending:
            print(f"✅ All {len(services)} services are healthy ({clock() - start:.0f}s)", file=out)
            return 0

        now = clock()
        if now >= deadline:
            print(f"❌ Timed out after {timeout:.0f}s. Not ready:", file=out)
            _report([last[s] for s in pending], engine, out)
            print("   Run 'make services-logs' to follow every service's logs.", file=out)
            return 1

        if now >= next_progress:
            waiting = ", ".join(f"{s} ({last[s].detail})" for s in pending)
            print(f"   … still waiting ({now - start:.0f}s): {waiting}", file=out)
            next_progress = now + PROGRESS_EVERY_SECONDS

        sleep(min(interval, max(deadline - now, 0.0)))


def _positive_float(value: str) -> float:
    number = float(value)
    if number <= 0:
        message = "must be greater than 0"
        raise argparse.ArgumentTypeError(message)
    return number


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("services", nargs="+", help="Compose service names to wait for")
    parser.add_argument("--project", required=True, help="Compose project name (com.docker.compose.project label)")
    parser.add_argument("--engine", default="podman", help="Container engine CLI (default: podman)")
    parser.add_argument(
        "--timeout",
        type=_positive_float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Seconds to wait before failing (default: {DEFAULT_TIMEOUT_SECONDS:.0f})",
    )
    parser.add_argument(
        "--interval",
        type=_positive_float,
        default=DEFAULT_INTERVAL_SECONDS,
        help=f"Seconds between polls (default: {DEFAULT_INTERVAL_SECONDS:.0f})",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return its exit code."""
    args = parse_args(argv)
    return wait_for_services(
        Engine(args.engine),
        args.project,
        args.services,
        timeout=args.timeout,
        interval=args.interval,
    )


if __name__ == "__main__":
    sys.exit(main())
