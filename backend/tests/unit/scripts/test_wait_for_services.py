"""Tests for tools/wait_for_services.py and its use in ``make services-run``.

Three layers:

* Hermetic tests drive ``wait_for_services`` with a scripted fake engine and a
  fake clock, so every readiness rule and failure path runs without containers.
* Makefile wiring tests run the ``make services-run`` recipe with stubbed
  ``podman-compose`` and wait commands. They check that the services come from
  ``podman-compose.yml`` and that the wait step runs after ``up`` with exactly
  the same services.
* Real-podman tests start throwaway compose projects and run the tool as a
  subprocess. They are opt-in (``SYNTARA_TEST_WITH_PODMAN=1``) because they
  need a podman machine and pull a small image.
"""

from __future__ import annotations

import importlib.util
import io
import os
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml

from tools.wait_for_services import (
    MIN_COMMAND_TIMEOUT_SECONDS,
    PROJECT_LABEL,
    SERVICE_LABEL,
    ComposeFileError,
    Engine,
    EngineError,
    EngineTimeoutError,
    Readiness,
    _run,
    classify_container,
    compose_services,
    main,
    parse_args,
    wait_for_services,
)

BACKEND_DIR = Path(__file__).resolve().parents[3]
REPO_ROOT = BACKEND_DIR.parent
SCRIPT = BACKEND_DIR / "tools" / "wait_for_services.py"
PROJECT = "test-project"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def container(
    status: str = "running",
    health: str | None = None,
    *,
    restart: str = "unless-stopped",
    exit_code: int = 0,
    health_output: str | None = None,
) -> dict[str, Any]:
    """Build the subset of ``podman inspect`` output the tool reads."""
    state: dict[str, Any] = {"Status": status, "ExitCode": exit_code}
    if health is not None:
        log = [{"ExitCode": 0 if health == "healthy" else 1, "Output": health_output or ""}]
        state["Health"] = {"Status": health, "FailingStreak": 0, "Log": log}
    return {
        "State": state,
        "Config": {"Healthcheck": {"Test": ["CMD", "true"]}} if health is not None else {},
        "HostConfig": {"RestartPolicy": {"Name": restart}},
    }


# One poll's view of a service: its containers by name, or an error from ps.
Poll = Mapping[str, dict[str, Any]] | EngineError


class FakeEngine(Engine):
    """Engine whose answers come from a per-service script of polls.

    Each ``find_containers`` call for a service advances that service to its
    next scripted poll; the last poll repeats forever.
    """

    def __init__(
        self,
        script: Mapping[str, Sequence[Poll]],
        binary: str = "podman",
        *,
        stalled: Sequence[tuple[str, str]] = (),
    ) -> None:
        """Serve ``script``; the fake never runs real engine commands.

        ``stalled`` lists ``(subcommand, container)`` pairs (``inspect`` or
        ``healthcheck``) that time out instead of answering.
        """
        super().__init__(binary=binary, runner=self._unexpected_runner)
        self._script = {service: list(polls) for service, polls in script.items()}
        self._current: dict[str, dict[str, Any]] = {}
        self._stalled = set(stalled)
        self.queried: list[str] = []
        self.triggered: list[str] = []
        self.timeouts: list[float | None] = []

    @staticmethod
    def _unexpected_runner(cmd: Sequence[str], timeout: float | None) -> subprocess.CompletedProcess[str]:
        message = f"unexpected engine command: {cmd} (timeout {timeout})"
        raise AssertionError(message)

    def _maybe_stall(self, subcommand: str, container: str, timeout: float | None) -> None:
        if (subcommand, container) in self._stalled:
            message = f"{self.binary} {subcommand} {container} timed out after {timeout:.0f}s"
            raise EngineTimeoutError(message)

    def find_containers(self, project: str, service: str, *, timeout: float | None = None) -> list[str]:
        assert project == PROJECT
        self.queried.append(service)
        self.timeouts.append(timeout)
        polls = self._script.get(service, [{}])
        poll = polls.pop(0) if len(polls) > 1 else polls[0]
        if isinstance(poll, EngineError):
            raise poll
        self._current.update(poll)
        return sorted(poll)

    def inspect(self, container: str, *, timeout: float | None = None) -> dict[str, Any]:
        self.timeouts.append(timeout)
        self._maybe_stall("inspect", container, timeout)
        return self._current[container]

    def trigger_healthcheck(self, container: str, *, timeout: float | None = None) -> None:
        self.timeouts.append(timeout)
        if self.supports_manual_healthcheck:
            self.triggered.append(container)
            self._maybe_stall("healthcheck", container, timeout)


class FakeClock:
    """Monotonic clock that only advances when ``sleep`` is called."""

    def __init__(self) -> None:
        """Start at an arbitrary non-zero time."""
        self.now = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def run_wait(
    engine: FakeEngine,
    services: Sequence[str],
    *,
    timeout: float = 30.0,
    interval: float = 1.0,
) -> tuple[int, str, FakeClock]:
    clock = FakeClock()
    out = io.StringIO()
    code = wait_for_services(
        engine,
        PROJECT,
        services,
        timeout=timeout,
        interval=interval,
        clock=clock,
        sleep=clock.sleep,
        out=out,
    )
    return code, out.getvalue(), clock


# ---------------------------------------------------------------------------
# classify_container
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "readiness", "detail"),
    [
        (container("running", "healthy"), Readiness.READY, "healthy"),
        (container("running"), Readiness.READY, "running (no healthcheck)"),
        (container("running", "starting"), Readiness.WAITING, "starting"),
        (container("running", "unhealthy"), Readiness.WAITING, "unhealthy"),
        (container("running", ""), Readiness.WAITING, "starting"),
        (container("created"), Readiness.WAITING, "created"),
        (container("restarting", "starting"), Readiness.WAITING, "restarting"),
        (container("exited", restart="no", exit_code=3), Readiness.FAILED, "exited (exit code 3)"),
        (container("exited", restart="", exit_code=1), Readiness.FAILED, "exited (exit code 1)"),
        (container("dead", restart="no", exit_code=137), Readiness.FAILED, "dead (exit code 137)"),
        (
            container("exited", restart="unless-stopped", exit_code=1),
            Readiness.WAITING,
            "exited (exit code 1), waiting for restart policy 'unless-stopped'",
        ),
    ],
)
def test_classify_container(data: dict[str, Any], readiness: Readiness, detail: str) -> None:
    status = classify_container("svc_1", data)
    assert status.readiness is readiness
    assert status.detail == detail


def test_classify_container_reads_podman_healthcheck_key() -> None:
    """Older podman versions report health under State.Healthcheck."""
    data = {"State": {"Status": "running", "Healthcheck": {"Status": "healthy"}}}
    assert classify_container("svc_1", data).readiness is Readiness.READY


def test_classify_container_without_state_is_waiting() -> None:
    assert classify_container("svc_1", {}).readiness is Readiness.WAITING


def test_classify_container_truncates_long_health_output() -> None:
    data = container("running", "unhealthy", health_output="x" * 2000)
    output = classify_container("svc_1", data).health_output
    assert output is not None
    assert len(output) <= 501
    assert output.endswith("…")


# ---------------------------------------------------------------------------
# wait_for_services: success paths
# ---------------------------------------------------------------------------


def test_returns_zero_when_all_services_are_already_healthy() -> None:
    engine = FakeEngine(
        {
            "database": [{"p_database_1": container("running", "healthy")}],
            "temporal-ui": [{"p_temporal-ui_1": container("running")}],
        }
    )

    code, out, clock = run_wait(engine, ["database", "temporal-ui"])

    assert code == 0
    assert clock.sleeps == []
    assert "database: healthy" in out
    assert "temporal-ui: running (no healthcheck)" in out
    assert "All 2 services are healthy" in out


def test_waits_until_starting_service_becomes_healthy() -> None:
    engine = FakeEngine(
        {
            "temporal": [
                {"p_temporal_1": container("running", "starting")},
                {"p_temporal_1": container("running", "starting")},
                {"p_temporal_1": container("running", "healthy")},
            ]
        }
    )

    code, out, clock = run_wait(engine, ["temporal"], interval=2.0)

    assert code == 0
    assert clock.sleeps == [2.0, 2.0]
    assert "temporal: healthy (4s)" in out


def test_waits_for_container_that_does_not_exist_yet() -> None:
    engine = FakeEngine({"moto": [{}, {}, {"p_moto_1": container("running", "healthy")}]})

    code, _, clock = run_wait(engine, ["moto"])

    assert code == 0
    assert len(clock.sleeps) == 2


def test_waits_for_restart_of_container_with_restart_policy() -> None:
    engine = FakeEngine(
        {
            "worker": [
                {"p_worker_1": container("exited", "unhealthy", exit_code=1)},
                {"p_worker_1": container("running", "starting")},
                {"p_worker_1": container("running", "healthy")},
            ]
        }
    )

    code, _, _ = run_wait(engine, ["worker"])

    assert code == 0


def test_stops_polling_services_once_they_are_ready() -> None:
    engine = FakeEngine(
        {
            "database": [{"p_database_1": container("running", "healthy")}],
            "temporal": [
                {"p_temporal_1": container("running", "starting")},
                {"p_temporal_1": container("running", "healthy")},
            ],
        }
    )

    code, _, _ = run_wait(engine, ["database", "temporal"])

    assert code == 0
    assert engine.queried == ["database", "temporal", "temporal"]


def test_duplicate_service_names_are_checked_once() -> None:
    engine = FakeEngine({"redis": [{"p_redis_1": container("running", "healthy")}]})

    code, out, _ = run_wait(engine, ["redis", "redis"])

    assert code == 0
    assert engine.queried == ["redis"]
    assert "All 1 services are healthy" in out


# ---------------------------------------------------------------------------
# wait_for_services: failure paths
# ---------------------------------------------------------------------------


def test_timeout_returns_nonzero_and_reports_unhealthy_service() -> None:
    """A timeout must fail. podman-compose 1.6 `up --wait` exits 0 here."""
    engine = FakeEngine(
        {
            "database": [{"p_database_1": container("running", "healthy")}],
            "mcp-server": [
                {"p_mcp-server_1": container("running", "unhealthy", health_output="curl: (7) connection refused")}
            ],
        }
    )

    code, out, clock = run_wait(engine, ["database", "mcp-server"], timeout=10.0, interval=3.0)

    assert code == 1
    assert sum(clock.sleeps) == pytest.approx(10.0)
    assert clock.sleeps[-1] == pytest.approx(1.0), "the last sleep is clamped to the deadline"
    assert "Timed out after 10s" in out
    assert "mcp-server: unhealthy" in out
    assert "last healthcheck output: curl: (7) connection refused" in out
    assert "logs: podman logs p_mcp-server_1" in out
    assert "database" not in out.split("Timed out")[1], "only services that are not ready are reported"


def test_timeout_reports_missing_container() -> None:
    engine = FakeEngine({"moto": [{}]})

    code, out, _ = run_wait(engine, ["moto"], timeout=5.0)

    assert code == 1
    assert "moto: no container" in out


def test_exited_container_without_restart_fails_before_timeout() -> None:
    engine = FakeEngine(
        {
            "temporal": [
                {"p_temporal_1": container("running", "starting")},
                {"p_temporal_1": container("exited", "unhealthy", restart="no", exit_code=1)},
            ]
        }
    )

    code, out, clock = run_wait(engine, ["temporal"], timeout=300.0, interval=1.0)

    assert code == 1
    assert sum(clock.sleeps) == pytest.approx(1.0), "fails fast instead of waiting out the timeout"
    assert "temporal will not become healthy" in out
    assert "exited (exit code 1)" in out


def test_engine_error_fails_immediately() -> None:
    engine = FakeEngine({"database": [EngineError("podman ps failed (exit 125): cannot connect to Podman")]})

    code, out, clock = run_wait(engine, ["database"])

    assert code == 1
    assert clock.sleeps == []
    assert "cannot connect to Podman" in out


def test_engine_commands_are_bounded_by_the_remaining_deadline() -> None:
    engine = FakeEngine({"temporal": [{"temporal_1": container("running", "starting")}]})

    code, _, _ = run_wait(engine, ["temporal"], timeout=60.0, interval=10.0)

    assert code == 1
    timeouts = [t for t in engine.timeouts if t is not None]
    assert timeouts == engine.timeouts, "every engine command gets a timeout"
    # One poll is ps, inspect and healthcheck run; the clock only moves on sleep.
    assert timeouts[:3] == [60.0, 60.0, 60.0]
    assert timeouts[3:6] == [50.0, 50.0, 50.0]
    assert timeouts == sorted(timeouts, reverse=True)
    assert min(timeouts) == MIN_COMMAND_TIMEOUT_SECONDS, "a command near the deadline still gets the floor"


@pytest.mark.parametrize("subcommand", ["inspect", "healthcheck"])
def test_stalled_engine_command_fails_instead_of_waiting(subcommand: str) -> None:
    engine = FakeEngine(
        {"temporal": [{"temporal_1": container("running", "starting")}]},
        stalled=[(subcommand, "temporal_1")],
    )

    code, out, clock = run_wait(engine, ["temporal"], timeout=300.0)

    assert code == 1
    assert clock.sleeps == [], "a timed-out command fails the wait at once"
    assert "temporal will not become healthy" in out
    assert f"podman {subcommand} temporal_1 timed out after 300s" in out


def test_scaled_service_needs_every_container_ready() -> None:
    engine = FakeEngine(
        {
            "worker": [
                {
                    "p_worker_1": container("running", "healthy"),
                    "p_worker_2": container("running", "unhealthy"),
                }
            ]
        }
    )

    code, out, _ = run_wait(engine, ["worker"], timeout=3.0)

    assert code == 1
    assert "p_worker_2: unhealthy" in out
    assert "logs: podman logs p_worker_2" in out
    assert "logs: podman logs p_worker_1" not in out


# ---------------------------------------------------------------------------
# wait_for_services: scope and healthcheck triggering
# ---------------------------------------------------------------------------


def test_only_requested_services_are_queried() -> None:
    """Unrelated unhealthy containers in the project must not block the wait.

    podman-compose 1.6 `up --wait` waits on every container in the project.
    """
    engine = FakeEngine(
        {
            "redis": [{"p_redis_1": container("running", "healthy")}],
            "never-ok": [{"p_never-ok_1": container("running", "unhealthy")}],
        }
    )

    code, _, _ = run_wait(engine, ["redis"])

    assert code == 0
    assert engine.queried == ["redis"]


def test_podman_triggers_healthcheck_for_waiting_containers() -> None:
    engine = FakeEngine(
        {
            "temporal": [
                {"p_temporal_1": container("running", "starting")},
                {"p_temporal_1": container("running", "healthy")},
            ],
            "temporal-ui": [{"p_temporal-ui_1": container("created")}, {"p_temporal-ui_1": container("running")}],
        }
    )

    code, _, _ = run_wait(engine, ["temporal", "temporal-ui"])

    assert code == 0
    assert engine.triggered == ["p_temporal_1"], "only containers with a healthcheck are triggered"


def test_docker_does_not_trigger_healthchecks() -> None:
    engine = FakeEngine(
        {
            "temporal": [
                {"p_temporal_1": container("running", "starting")},
                {"p_temporal_1": container("running", "healthy")},
            ]
        },
        binary="docker",
    )

    code, _, _ = run_wait(engine, ["temporal"])

    assert code == 0
    assert engine.triggered == []


def test_prints_progress_while_waiting() -> None:
    engine = FakeEngine(
        {
            "temporal": [{"p_temporal_1": container("running", "starting")}] * 40
            + [{"p_temporal_1": container("running", "healthy")}]
        }
    )

    code, out, _ = run_wait(engine, ["temporal"], timeout=120.0, interval=1.0)

    assert code == 0
    assert "still waiting (30s): temporal (starting)" in out


# ---------------------------------------------------------------------------
# Engine (CLI wrapper)
# ---------------------------------------------------------------------------


class RecordingRunner:
    """Runner that records commands and answers by engine subcommand."""

    def __init__(self, responses: Mapping[str, subprocess.CompletedProcess[str] | BaseException]) -> None:
        """Answer each subcommand (``ps``, ``inspect``, ...) with its canned result."""
        self.responses = responses
        self.calls: list[list[str]] = []

        self.timeouts: list[float | None] = []

    def __call__(self, cmd: Sequence[str], timeout: float | None) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(cmd))
        self.timeouts.append(timeout)
        response = self.responses[cmd[1]]
        if isinstance(response, BaseException):
            raise response
        return response


def completed(stdout: str = "", returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_engine_find_containers_filters_by_compose_labels() -> None:
    runner = RecordingRunner({"ps": completed("syntara_temporal_1\n\n")})

    names = Engine("podman", runner).find_containers("syntara", "temporal")

    assert names == ["syntara_temporal_1"]
    assert runner.calls == [
        [
            "podman",
            "ps",
            "--all",
            "--filter",
            f"label={PROJECT_LABEL}=syntara",
            "--filter",
            f"label={SERVICE_LABEL}=temporal",
            "--format",
            "{{.Names}}",
        ]
    ]


def test_engine_inspect_returns_first_object() -> None:
    runner = RecordingRunner({"inspect": completed('[{"State": {"Status": "running"}}]')})

    assert Engine("podman", runner).inspect("c1") == {"State": {"Status": "running"}}


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (completed(returncode=125, stderr="Error: cannot connect"), "exit 125): Error: cannot connect"),
        (completed("not json"), "returned invalid JSON"),
        (completed('"a string"'), "returned unexpected data"),
    ],
)
def test_engine_inspect_errors(response: subprocess.CompletedProcess[str], message: str) -> None:
    engine = Engine("podman", RecordingRunner({"inspect": response}))

    with pytest.raises(EngineError, match=message.replace("(", r"\(").replace(")", r"\)")):
        engine.inspect("c1")


def test_engine_passes_timeout_to_runner() -> None:
    runner = RecordingRunner({"ps": completed(""), "inspect": completed("{}"), "healthcheck": completed()})
    engine = Engine("podman", runner)

    engine.find_containers("p", "s", timeout=12.0)
    engine.inspect("c1", timeout=7.0)
    engine.trigger_healthcheck("c1", timeout=3.0)

    assert runner.timeouts == [12.0, 7.0, 3.0]


@pytest.mark.parametrize(
    "call",
    [
        lambda e: e.find_containers("p", "s", timeout=4.0),
        lambda e: e.inspect("c1", timeout=4.0),
        lambda e: e.trigger_healthcheck("c1", timeout=4.0),
    ],
    ids=["ps", "inspect", "healthcheck"],
)
def test_engine_raises_timeout_error_when_command_times_out(call: Callable[[Engine], object]) -> None:
    stalled = subprocess.TimeoutExpired(cmd="podman", timeout=4.0)
    engine = Engine("podman", RecordingRunner(dict.fromkeys(("ps", "inspect", "healthcheck"), stalled)))

    with pytest.raises(EngineTimeoutError, match="timed out after 4s"):
        call(engine)


def test_engine_trigger_healthcheck_ignores_other_errors() -> None:
    def runner(cmd: Sequence[str], timeout: float | None) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(cmd[0])

    Engine("podman", runner).trigger_healthcheck("c1", timeout=1.0)


def test_run_kills_command_and_its_children_on_timeout(tmp_path: Path) -> None:
    # The child sleep inherits the output pipes. Killing only the shell would
    # leave them open and reading the output would block for the full minute.
    stalled = tmp_path / "stalled-engine"
    stalled.write_text("#!/bin/sh\nsleep 60\necho never\n")
    stalled.chmod(0o755)

    start = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        _run([str(stalled)], 0.5)
    elapsed = time.monotonic() - start

    # Well under the grace period _run allows for reading output after a kill,
    # so this fails if the child sleep survives and keeps the pipes open.
    assert elapsed < 3, f"took {elapsed:.1f}s"


def test_run_captures_output_and_exit_code() -> None:
    result = _run([sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"], 30)

    assert (result.returncode, result.stdout, result.stderr) == (3, "out\n", "err\n")


def test_main_fails_within_timeout_when_engine_stalls(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    stalled = tmp_path / "stalled-engine"
    stalled.write_text("#!/bin/sh\nexec sleep 60\n")
    stalled.chmod(0o755)

    start = time.monotonic()
    code = main(["--engine", str(stalled), "--project", "p", "--timeout", "1", "db"])
    elapsed = time.monotonic() - start

    assert code == 1
    assert elapsed < MIN_COMMAND_TIMEOUT_SECONDS + 5, f"took {elapsed:.1f}s"
    assert "timed out after" in capsys.readouterr().out


def test_engine_reports_missing_binary() -> None:
    def runner(cmd: Sequence[str], timeout: float | None) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(cmd[0])

    with pytest.raises(EngineError, match="could not run podman ps"):
        Engine("podman", runner).find_containers("p", "s")


def test_engine_trigger_healthcheck_only_runs_for_podman() -> None:
    podman_runner = RecordingRunner({"healthcheck": completed(returncode=1)})
    docker_runner = RecordingRunner({})

    Engine("/usr/bin/podman", podman_runner).trigger_healthcheck("c1")
    Engine("docker", docker_runner).trigger_healthcheck("c1")

    assert podman_runner.calls == [["/usr/bin/podman", "healthcheck", "run", "c1"]]
    assert docker_runner.calls == []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_parse_args_defaults() -> None:
    args = parse_args(["--project", "syntara", "database", "redis"])

    assert args.services == ["database", "redis"]
    assert args.engine == "podman"
    assert args.timeout == 300.0
    assert args.interval == 3.0


@pytest.mark.parametrize(
    "argv",
    [
        ["--project", "p"],
        ["db"],
        ["--project", "p", "--timeout", "0", "db"],
        ["--print-services"],
        ["--print-services", "--compose-file", "c.yml", "db"],
        ["--project", "p", "--compose-file", "c.yml", "db"],
        ["--project", "p", "--exclude", "x", "db"],
    ],
)
def test_parse_args_rejects_invalid_input(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        parse_args(argv)
    assert exc_info.value.code == 2


def test_main_exits_nonzero_when_engine_is_missing(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--engine", "definitely-not-a-container-engine", "--project", "p", "--timeout", "1", "db"])

    assert code == 1
    assert "could not run definitely-not-a-container-engine" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# compose_services
# ---------------------------------------------------------------------------

COMPOSE_FIXTURE = {
    "services": {
        "database": {"image": "db"},
        "api": {"image": "api"},
        "scenarios": {"image": "s", "profiles": ["scenarios"]},
        "telemetry": {"image": "t", "profiles": ["telemetry"]},
        "worker": {"image": "w"},
    }
}


@pytest.fixture
def compose_file(tmp_path: Path) -> Path:
    path = tmp_path / "compose.yml"
    path.write_text(yaml.safe_dump(COMPOSE_FIXTURE, sort_keys=False))
    return path


@pytest.mark.parametrize(
    ("profiles", "exclude", "expected"),
    [
        ((), (), ["database", "api", "worker"]),
        (["scenarios"], (), ["database", "api", "scenarios", "worker"]),
        (["scenarios", "telemetry"], ["api"], ["database", "scenarios", "telemetry", "worker"]),
        ((), ["api", "database"], ["worker"]),
    ],
)
def test_compose_services_filters_by_profile_and_exclude(
    compose_file: Path, profiles: Sequence[str], exclude: Sequence[str], expected: list[str]
) -> None:
    assert compose_services(compose_file, profiles=profiles, exclude=exclude) == expected


@pytest.mark.parametrize(
    ("content", "exclude", "message"),
    [
        (None, (), "excluded services are not defined in .*: apii"),
        ("services: {}\n", (), "defines no services"),
        ("volumes: {}\n", (), "defines no services"),
        ("services: [unclosed\n", (), "cannot read"),
        ("services:\n  api: {}\n", ["api"], "no services .* are left to start"),
    ],
)
def test_compose_services_rejects_bad_input(
    compose_file: Path, content: str | None, exclude: Sequence[str], message: str
) -> None:
    if content is not None:
        compose_file.write_text(content)

    with pytest.raises(ComposeFileError, match=message):
        compose_services(compose_file, exclude=exclude or ["apii"])


def test_compose_services_reports_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ComposeFileError, match="cannot read"):
        compose_services(tmp_path / "missing.yml")


def test_main_prints_services(compose_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--print-services", "--compose-file", str(compose_file), "--profile", "scenarios", "--exclude", "api"])

    assert code == 0
    assert capsys.readouterr().out == "database scenarios worker\n"


def test_main_print_services_fails_on_bad_compose_file(compose_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--print-services", "--compose-file", str(compose_file), "--exclude", "nope"])

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == "", "nothing is printed for make to start"
    assert "nope" in captured.err


# ---------------------------------------------------------------------------
# Makefile wiring
# ---------------------------------------------------------------------------

# Stands in for tools/wait_for_services.py: --print-services runs the real
# tool, anything else (the wait) is printed instead of run.
WAIT_STUB = """\
import os, subprocess, sys
if "--print-services" in sys.argv:
    if os.environ.get("STUB_LIST_FAILS") == "1":
        sys.exit(1)
    sys.exit(subprocess.call([sys.executable, {script!r}, *sys.argv[1:]]))
print("WAIT", *sys.argv[1:])
"""


def _run_services_run(tmp_path: Path, **env: str) -> subprocess.CompletedProcess[str]:
    make = shutil.which("make")
    if make is None:
        pytest.skip("make is not installed")
    stub = tmp_path / "wait_stub.py"
    stub.write_text(WAIT_STUB.format(script=str(SCRIPT)))
    return subprocess.run(  # noqa: S603
        [
            make,
            "--no-print-directory",
            # -o keeps make from generating secrets/certs for a stubbed run.
            "-o",
            "_ensure-secrets",
            "-o",
            "_ensure-certs",
            "services-run",
            "COMPOSE_CMD=echo COMPOSE",
            f"WAIT_FOR_SERVICES={sys.executable} {stub}",
        ],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PODMAN_PROJECT": "wiring-test", "SERVICES_WAIT_TIMEOUT": "123", **env},
    )


def _commands(result: subprocess.CompletedProcess[str], prefix: str) -> list[list[str]]:
    return [shlex.split(line)[1:] for line in result.stdout.splitlines() if line.startswith(f"{prefix} ")]


def _services_after(command: list[str], marker: str, *, skip_options_with_values: Sequence[str] = ()) -> list[str]:
    rest = command[command.index(marker) + 1 :]
    services: list[str] = []
    skip_next = False
    for token in rest:
        if skip_next:
            skip_next = False
        elif token in skip_options_with_values:
            skip_next = True
        elif not token.startswith("-"):
            services.append(token)
    return services


def _expected_services(profiles: set[str], exclude: set[str]) -> list[str]:
    """Services ``podman-compose --profile`` would enable, computed independently."""
    services = yaml.safe_load((REPO_ROOT / "podman-compose.yml").read_text())["services"]
    return [
        name
        for name, definition in services.items()
        if name not in exclude and (not definition.get("profiles") or set(definition["profiles"]) & profiles)
    ]


def test_services_run_waits_for_the_same_services_it_starts(tmp_path: Path) -> None:
    result = _run_services_run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    [up] = _commands(result, "COMPOSE")
    [wait] = _commands(result, "WAIT")
    prefixes = [line.split(" ", 1)[0] for line in result.stdout.splitlines()]

    started = _services_after(up, "-d")
    waited = _services_after(wait, "--timeout")[1:]  # drop the timeout value

    assert prefixes.index("WAIT") > prefixes.index("COMPOSE"), "the wait must run after the services are started"
    assert started, "services-run must name the services it starts"
    assert waited == started
    assert wait[wait.index("--project") + 1] == "wiring-test", "waits on the same compose project"
    assert wait[wait.index("--timeout") + 1] == "123", "SERVICES_WAIT_TIMEOUT is honored"
    assert up[up.index("-p") + 1] == "wiring-test"


def test_services_run_starts_services_from_the_compose_file(tmp_path: Path) -> None:
    result = _run_services_run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    [up] = _commands(result, "COMPOSE")
    enabled_profiles = {up[i + 1] for i, arg in enumerate(up) if arg == "--profile"}

    started = _services_after(up, "-d", skip_options_with_values=("-p", "-f", "--profile"))

    assert started == _expected_services(enabled_profiles, {"syntara", "syntara-ui"})
    # Spot-check against the compose file as it is today.
    assert {"database", "redis", "temporal", "temporal-worker", "moto", "mcp-server-scenarios"} <= set(started)
    assert not {"syntara", "syntara-ui"} & set(started), "make dev runs the API and UI locally"
    assert "mock-segment" not in started, "services behind other profiles stay off"


def test_services_run_does_not_start_anything_when_the_list_fails(tmp_path: Path) -> None:
    # An empty list would make `up -d` start every service, API and UI included.
    result = _run_services_run(tmp_path, STUB_LIST_FAILS="1")

    assert result.returncode != 0
    assert _commands(result, "COMPOSE") == []
    assert _commands(result, "WAIT") == []
    assert "All services started" not in result.stdout


def test_root_services_up_delegates_to_services_run() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text()
    recipe = makefile.split("\nservices-up:", 1)[1].split("\n\n", 1)[0]
    assert "$(MAKE) -C backend services-run" in recipe


# ---------------------------------------------------------------------------
# Real podman (opt-in)
# ---------------------------------------------------------------------------

PODMAN_IMAGE = os.environ.get("SYNTARA_TEST_PODMAN_IMAGE", "registry.access.redhat.com/ubi9/ubi-minimal:latest")


def _podman_available() -> bool:
    if os.environ.get("SYNTARA_TEST_WITH_PODMAN") != "1" or shutil.which("podman") is None:
        return False
    if importlib.util.find_spec("podman_compose") is None:
        return False
    return subprocess.run(["podman", "info"], capture_output=True, check=False).returncode == 0  # noqa: S607


requires_podman = pytest.mark.skipif(
    not _podman_available(),
    reason="set SYNTARA_TEST_WITH_PODMAN=1 with a working podman to run real-container tests",
)


def _healthcheck(test: str) -> dict[str, Any]:
    return {"test": ["CMD-SHELL", test], "interval": "2s", "timeout": "2s", "retries": 3}


SERVICES: dict[str, dict[str, Any]] = {
    # Becomes healthy after five seconds.
    "slow-ok": {
        "command": ["sh", "-c", "sleep 5; touch /tmp/ready; sleep infinity"],
        "healthcheck": {**_healthcheck("test -f /tmp/ready"), "retries": 30},
    },
    # Running, but its healthcheck always fails.
    "never-ok": {"command": ["sleep", "infinity"], "healthcheck": _healthcheck("false")},
    # Running, no healthcheck.
    "plain": {"command": ["sleep", "infinity"]},
    # Exits immediately and is never restarted.
    "crashes": {"command": ["sh", "-c", "exit 3"], "restart": "no"},
}


@pytest.fixture
def compose_project(tmp_path: Path) -> Iterator[Callable[..., str]]:
    """Factory that starts the given services in a throwaway compose project."""
    project = f"wfs-test-{uuid.uuid4().hex[:8]}"
    compose_file = tmp_path / "compose.yml"
    compose_file.write_text(
        yaml.safe_dump({"services": {name: {"image": PODMAN_IMAGE, **spec} for name, spec in SERVICES.items()}})
    )
    base = [sys.executable, "-m", "podman_compose", "-p", project, "-f", str(compose_file)]

    def start(*services: str) -> str:
        subprocess.run([*base, "up", "-d", *services], check=True, capture_output=True, timeout=300)  # noqa: S603
        return project

    yield start
    subprocess.run([*base, "down", "-t", "0"], check=False, capture_output=True, timeout=120)  # noqa: S603


def _run_tool(project: str, *services: str, timeout: int) -> tuple[subprocess.CompletedProcess[str], float]:
    started = time.monotonic()
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(SCRIPT), "--project", project, "--timeout", str(timeout), "--interval", "1", *services],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout + 60,
    )
    return result, time.monotonic() - started


@pytest.mark.integration
@pytest.mark.slow
@requires_podman
class TestWithRealPodman:
    """Run the tool as a subprocess against real containers."""

    def test_waits_until_service_is_healthy(self, compose_project: Callable[..., str]) -> None:
        project = compose_project("slow-ok", "plain")

        result, _ = _run_tool(project, "slow-ok", "plain", timeout=60)

        assert result.returncode == 0, result.stdout + result.stderr
        assert "slow-ok: healthy" in result.stdout
        assert "plain: running (no healthcheck)" in result.stdout
        state = subprocess.run(  # noqa: S603
            ["podman", "inspect", "--format", "{{.State.Health.Status}}", f"{project}_slow-ok_1"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
        )
        assert state.stdout.strip() == "healthy"

    def test_fails_when_service_never_becomes_healthy(self, compose_project: Callable[..., str]) -> None:
        project = compose_project("never-ok")

        result, elapsed = _run_tool(project, "never-ok", timeout=12)

        assert result.returncode == 1, result.stdout + result.stderr
        assert "Timed out after 12s" in result.stdout
        assert "never-ok: unhealthy" in result.stdout
        assert elapsed >= 12

    def test_ignores_unrelated_unhealthy_service(self, compose_project: Callable[..., str]) -> None:
        project = compose_project("never-ok", "plain")

        result, elapsed = _run_tool(project, "plain", timeout=30)

        assert result.returncode == 0, result.stdout + result.stderr
        assert elapsed < 15, "must not wait on never-ok, which was not requested"

    def test_fails_fast_when_container_exits_without_restart(self, compose_project: Callable[..., str]) -> None:
        project = compose_project("crashes")

        result, elapsed = _run_tool(project, "crashes", timeout=120)

        assert result.returncode == 1, result.stdout + result.stderr
        assert "crashes will not become healthy" in result.stdout
        assert "exit code 3" in result.stdout
        assert elapsed < 60, "an exited container with no restart policy should fail before the timeout"
