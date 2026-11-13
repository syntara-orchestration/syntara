#!/usr/bin/env python3
"""Wait until compose services are running and healthy.

`make services-run` starts the stack with `podman-compose up -d`. That command
returns as soon as the last container starts, so services started late (the
Temporal workers and MCP servers) may still be starting, and a service that
never becomes healthy goes unreported. This tool polls the container engine
until every requested service is ready, and exits non-zero with diagnostics if
one is not ready before the timeout.

A service is ready when each of its containers is running and, if it defines a
healthcheck, reports healthy. Every engine command is bounded by the time left
before the deadline, so a stalled engine cannot hold the wait past the timeout.

With ``--print-services`` the tool instead prints the services that a compose
file enables for the given profiles, minus ``--exclude``. ``make services-run``
uses this so the list of services to start is not maintained by hand.

podman-compose's own `up --wait` is not used because, in podman-compose 1.6,
it exits 0 when `--wait-timeout` expires and it waits on every container in the
project rather than only the requested services.

Usage:
    uv run python tools/wait_for_services.py --project syntara database redis temporal
    uv run python tools/wait_for_services.py --print-services \
        --compose-file ../podman-compose.yml --profile mcp-scenarios --exclude syntara
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, TextIO

import yaml

PROJECT_LABEL = "com.docker.compose.project"
SERVICE_LABEL = "com.docker.compose.service"

DEFAULT_TIMEOUT_SECONDS = 300.0
DEFAULT_INTERVAL_SECONDS = 3.0
PROGRESS_EVERY_SECONDS = 30.0
HEALTH_OUTPUT_LIMIT = 500
# Floor for an engine command's timeout, so a command issued just before the
# deadline still gets a fair chance to finish instead of being killed at once.
MIN_COMMAND_TIMEOUT_SECONDS = 5.0

# Restart policies under which an exited container stays exited.
_NO_RESTART_POLICIES = frozenset({"", "no"})
_STOPPED_STATES = frozenset({"exited", "dead", "stopped"})

# Runs a command with an optional timeout in seconds. Raises
# subprocess.TimeoutExpired when the command does not finish in time.
Runner = Callable[[Sequence[str], float | None], subprocess.CompletedProcess[str]]


class EngineError(RuntimeError):
    """The container engine could not be queried."""


class EngineTimeoutError(EngineError):
    """An engine command did not finish before its timeout."""


class ComposeFileError(ValueError):
    """The compose file cannot be read or does not match the request."""


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


def _kill_process_group(proc: subprocess.Popen[str]) -> None:
    if hasattr(os, "killpg"):
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGKILL)
    else:  # pragma: no cover - Windows
        proc.kill()


def _run(cmd: Sequence[str], timeout: float | None) -> subprocess.CompletedProcess[str]:
    """Run ``cmd`` and capture its output, killing it after ``timeout`` seconds.

    The command runs in its own session so that, on timeout, its children are
    killed too. Otherwise a child that inherited the output pipes keeps them
    open and reading the output blocks after the timeout.
    """
    # The command is built from our own arguments, never from external input.
    with subprocess.Popen(  # noqa: S603
        list(cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    ) as proc:
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_process_group(proc)
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.communicate(timeout=MIN_COMMAND_TIMEOUT_SECONDS)
            raise
        return subprocess.CompletedProcess(list(cmd), proc.returncode, stdout, stderr)


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

    def _execute(self, args: Sequence[str], timeout: float | None) -> subprocess.CompletedProcess[str]:
        cmd = [self.binary, *args]
        try:
            return self._runner(cmd, timeout)
        except subprocess.TimeoutExpired as exc:
            raise EngineTimeoutError(f"{' '.join(cmd)} timed out after {timeout:.0f}s") from exc
        except OSError as exc:
            raise EngineError(f"could not run {' '.join(cmd)}: {exc}") from exc

    def _check(self, args: Sequence[str], timeout: float | None) -> str:
        result = self._execute(args, timeout)
        cmd = [self.binary, *args]
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "").strip()
            raise EngineError(f"{' '.join(cmd)} failed (exit {result.returncode}): {message}")
        return result.stdout

    def find_containers(self, project: str, service: str, *, timeout: float | None = None) -> list[str]:
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
            ],
            timeout,
        )
        return sorted(line.strip() for line in out.splitlines() if line.strip())

    def inspect(self, container: str, *, timeout: float | None = None) -> dict[str, Any]:
        """Return the ``inspect`` object for ``container``."""
        out = self._check(["inspect", container], timeout)
        try:
            data = json.loads(out)
        except json.JSONDecodeError as exc:
            raise EngineError(f"{self.binary} inspect {container} returned invalid JSON") from exc
        if isinstance(data, list):
            data = data[0] if data else {}
        if not isinstance(data, dict):
            raise EngineError(f"{self.binary} inspect {container} returned unexpected data")
        return data

    def trigger_healthcheck(self, container: str, *, timeout: float | None = None) -> None:
        """Run the container's healthcheck now instead of waiting for its timer.

        Some podman setups (for example ``events_logger=file``) never fire the
        healthcheck timer, so the status would stay ``starting`` forever. The
        result is ignored: the next ``inspect`` reports the new status. Only a
        timeout is raised (as ``EngineTimeoutError``).
        """
        if not self.supports_manual_healthcheck:
            return
        try:
            self._execute(["healthcheck", "run", container], timeout)
        except EngineTimeoutError:
            raise
        except EngineError:
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


def _no_timeout() -> float | None:
    return None


def check_service(
    engine: Engine,
    project: str,
    service: str,
    *,
    command_timeout: Callable[[], float | None] = _no_timeout,
) -> ServiceStatus:
    """Check every container that belongs to ``service`` in ``project``.

    ``command_timeout`` is called before each engine command and returns that
    command's timeout. A command that times out fails the service.
    """
    try:
        names = engine.find_containers(project, service, timeout=command_timeout())
    except EngineError as exc:
        return ServiceStatus(service, Readiness.FAILED, str(exc))
    if not names:
        return ServiceStatus(service, Readiness.WAITING, "no container")

    containers: list[ContainerStatus] = []
    for name in names:
        try:
            container = classify_container(name, engine.inspect(name, timeout=command_timeout()))
        except EngineTimeoutError as exc:
            container = ContainerStatus(name, Readiness.FAILED, str(exc))
        except EngineError as exc:
            # The container can disappear between ps and inspect while it is
            # being recreated, so treat this as transient.
            container = ContainerStatus(name, Readiness.WAITING, f"not inspectable: {exc}")
        if container.readiness is Readiness.WAITING and container.has_healthcheck:
            try:
                engine.trigger_healthcheck(name, timeout=command_timeout())
            except EngineTimeoutError as exc:
                container = ContainerStatus(
                    name, Readiness.FAILED, str(exc), container.has_healthcheck, container.health_output
                )
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

    def command_timeout() -> float:
        return max(deadline - clock(), MIN_COMMAND_TIMEOUT_SECONDS)

    print(f"⏳ Waiting up to {timeout:.0f}s for {len(services)} services to be healthy...", file=out)
    while True:
        for service in list(pending):
            status = check_service(engine, project, service, command_timeout=command_timeout)
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


def compose_services(
    compose_file: Path,
    *,
    profiles: Iterable[str] = (),
    exclude: Iterable[str] = (),
) -> list[str]:
    """Return the services ``compose_file`` enables for ``profiles``, minus ``exclude``.

    A service is enabled when it lists no profiles or one of ``profiles``, as
    in ``podman-compose --profile``. Services keep their order in the file.
    Every name in ``exclude`` must be a service in the file, so a renamed
    service cannot silently slip back into the list.
    """
    try:
        data = yaml.safe_load(compose_file.read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise ComposeFileError(f"cannot read {compose_file}: {exc}") from exc
    services = data.get("services") if isinstance(data, dict) else None
    if not isinstance(services, dict) or not services:
        raise ComposeFileError(f"{compose_file} defines no services")

    excluded = set(exclude)
    unknown = sorted(excluded - set(services))
    if unknown:
        raise ComposeFileError(f"excluded services are not defined in {compose_file}: {', '.join(unknown)}")

    enabled_profiles = set(profiles)
    selected: list[str] = []
    for name, definition in services.items():
        service_profiles = set((definition or {}).get("profiles") or [])
        if name in excluded or (service_profiles and not service_profiles & enabled_profiles):
            continue
        selected.append(str(name))
    if not selected:
        raise ComposeFileError(f"no services in {compose_file} are left to start")
    return selected


def _positive_float(value: str) -> float:
    number = float(value)
    if number <= 0:
        message = "must be greater than 0"
        raise argparse.ArgumentTypeError(message)
    return number


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("services", nargs="*", help="Compose service names to wait for")
    parser.add_argument("--project", help="Compose project name (com.docker.compose.project label)")
    parser.add_argument(
        "--print-services",
        action="store_true",
        help="Print the services --compose-file enables for --profile, minus --exclude, and exit",
    )
    parser.add_argument("--compose-file", type=Path, help="Compose file to read services from")
    parser.add_argument("--profile", action="append", default=[], help="Compose profile to enable (repeatable)")
    parser.add_argument("--exclude", action="append", default=[], help="Service to leave out (repeatable)")
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
    args = parser.parse_args(argv)
    if args.print_services:
        if args.compose_file is None:
            parser.error("--print-services requires --compose-file")
        if args.services:
            parser.error("--print-services does not take service names")
    else:
        if args.project is None:
            parser.error("--project is required")
        if not args.services:
            parser.error("name at least one service to wait for")
        if args.compose_file is not None or args.profile or args.exclude:
            parser.error("--compose-file, --profile and --exclude only apply to --print-services")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return its exit code."""
    args = parse_args(argv)
    if args.print_services:
        try:
            services = compose_services(args.compose_file, profiles=args.profile, exclude=args.exclude)
        except ComposeFileError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 1
        print(" ".join(services))
        return 0
    return wait_for_services(
        Engine(args.engine),
        args.project,
        args.services,
        timeout=args.timeout,
        interval=args.interval,
    )


if __name__ == "__main__":
    sys.exit(main())
