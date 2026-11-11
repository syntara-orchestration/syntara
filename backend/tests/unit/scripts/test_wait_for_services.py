"""Tests for tools/wait_for_services.py and its use in ``make services-run``.

Three layers:

* Hermetic tests drive ``wait_for_services`` with a scripted fake engine and a
  fake clock, so every readiness rule and failure path runs without containers.
* A Makefile wiring test dry-runs ``make services-run`` and checks that the wait
  step runs after ``up`` with exactly the same services.
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
    PROJECT_LABEL,
    SERVICE_LABEL,
    Engine,
    EngineError,
    Readiness,
    classify_container,
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

    def __init__(self, script: Mapping[str, Sequence[Poll]], binary: str = "podman") -> None:
        """Serve ``script``; the fake never runs real engine commands."""
        super().__init__(binary=binary, runner=self._unexpected_runner)
        self._script = {service: list(polls) for service, polls in script.items()}
        self._current: dict[str, dict[str, Any]] = {}
        self.queried: list[str] = []
        self.triggered: list[str] = []

    @staticmethod
    def _unexpected_runner(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
        message = f"unexpected engine command: {cmd}"
        raise AssertionError(message)

    def find_containers(self, project: str, service: str) -> list[str]:
        assert project == PROJECT
        self.queried.append(service)
        polls = self._script.get(service, [{}])
        poll = polls.pop(0) if len(polls) > 1 else polls[0]
        if isinstance(poll, EngineError):
            raise poll
        self._current.update(poll)
        return sorted(poll)

    def inspect(self, container: str) -> dict[str, Any]:
        return self._current[container]

    def trigger_healthcheck(self, container: str) -> None:
        if self.supports_manual_healthcheck:
            self.triggered.append(container)


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

    def __init__(self, responses: Mapping[str, subprocess.CompletedProcess[str]]) -> None:
        """Answer each subcommand (``ps``, ``inspect``, ...) with its canned result."""
        self.responses = responses
        self.calls: list[list[str]] = []

    def __call__(self, cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(cmd))
        return self.responses[cmd[1]]


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


def test_engine_reports_missing_binary() -> None:
    def runner(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
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


@pytest.mark.parametrize("argv", [["--project", "p"], ["db"], ["--project", "p", "--timeout", "0", "db"]])
def test_parse_args_rejects_invalid_input(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        parse_args(argv)
    assert exc_info.value.code == 2


def test_main_exits_nonzero_when_engine_is_missing(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--engine", "definitely-not-a-container-engine", "--project", "p", "--timeout", "1", "db"])

    assert code == 1
    assert "could not run definitely-not-a-container-engine" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Makefile wiring
# ---------------------------------------------------------------------------


def _dry_run_services_run() -> list[list[str]]:
    make = shutil.which("make")
    if make is None:
        pytest.skip("make is not installed")
    result = subprocess.run(  # noqa: S603
        # -o keeps make from generating secrets/certs just to print the recipe.
        [make, "--no-print-directory", "-n", "-o", "_ensure-secrets", "-o", "_ensure-certs", "services-run"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PODMAN_PROJECT": "wiring-test", "SERVICES_WAIT_TIMEOUT": "123"},
    )
    return [shlex.split(line) for line in result.stdout.splitlines() if line.strip()]


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


def test_services_run_waits_for_the_same_services_it_starts() -> None:
    commands = _dry_run_services_run()
    up_index = next(i for i, c in enumerate(commands) if "up" in c and "podman-compose" in " ".join(c))
    wait_index = next(i for i, c in enumerate(commands) if any(t.endswith("wait_for_services.py") for t in c))
    up, wait = commands[up_index], commands[wait_index]

    started = _services_after(up, "-d")
    waited = _services_after(
        wait,
        next(t for t in wait if t.endswith("wait_for_services.py")),
        skip_options_with_values=("--project", "--timeout", "--interval", "--engine"),
    )

    assert wait_index > up_index, "the wait must run after the services are started"
    assert started, "services-run must name the services it starts"
    assert waited == started
    assert wait[wait.index("--project") + 1] == "wiring-test", "waits on the same compose project"
    assert wait[wait.index("--timeout") + 1] == "123", "SERVICES_WAIT_TIMEOUT is honored"
    assert "-p" in up
    assert up[up.index("-p") + 1] == "wiring-test"


def test_services_run_starts_only_services_defined_in_compose_file() -> None:
    commands = _dry_run_services_run()
    up = next(c for c in commands if "up" in c and "podman-compose" in " ".join(c))
    compose = yaml.safe_load((REPO_ROOT / "podman-compose.yml").read_text())
    enabled_profiles = {up[i + 1] for i, arg in enumerate(up) if arg == "--profile"}

    for service in _services_after(up, "-d"):
        assert service in compose["services"], f"{service} is not defined in podman-compose.yml"
        profiles = set(compose["services"][service].get("profiles") or [])
        assert not profiles or profiles & enabled_profiles, (
            f"{service} needs one of profiles {sorted(profiles)} enabled"
        )


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
