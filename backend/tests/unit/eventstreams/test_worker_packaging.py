"""Local compose and configuration contracts; no live deployment or broker claims."""

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from uuid import UUID

import yaml

from syntara.core.config.base import Settings
from syntara.core.constants import EventWorkerDefaults
from syntara.eventstreams.consumer_service import placement_targets
from syntara.eventstreams.models.consumer_worker import EventConsumerWorker
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.integrations.models.integration_configuration import KafkaConfiguration

ROOT = Path(__file__).resolve().parents[4]


def test_environment_examples_omit_event_tuning_and_compose_uses_code_defaults():
    compose = yaml.safe_load((ROOT / "podman-compose.yml").read_text())
    worker = compose["services"]["eventstream-consumer"]
    env = dict(value.split("=", 1) for value in worker["environment"] if "=" in value)
    inherited = {value for value in worker["environment"] if "=" not in value}
    assert inherited == set()
    assert {key for key in env if key.startswith("APP_EVENT")} == {"APP_EVENTSTREAM_ENABLED"}
    assert Settings.model_fields["eventstream_enabled"].default is False
    assert env["APP_EVENTSTREAM_ENABLED"] == "${APP_EVENTSTREAM_ENABLED:-false}"
    task_queue = Settings.model_fields["task_queue"].default
    assert env["APP_TASK_QUEUE"] == task_queue
    for path in [ROOT / ".env.example", ROOT / "backend/.env.example"]:
        contents = path.read_text()
        assert re.search(r"^\s*#?\s*APP_EVENT\w*\s*=", contents, re.MULTILINE) is None
        match = re.search(r"^APP_TASK_QUEUE=([^\s#]+)", contents, re.MULTILINE)
        assert match is not None
        assert match.group(1) == task_queue
    assert worker["profiles"] == ["eventstream"]
    assert worker["stop_grace_period"] == "60s"
    cleanup_headroom = EventWorkerDefaults.PLACEMENT_TIMEOUT_SECONDS + EventWorkerDefaults.HINT_TIMEOUT_SECONDS
    assert int(worker["stop_grace_period"].removesuffix("s")) > (
        Settings.model_fields["event_drain_timeout_seconds"].default + cleanup_headroom
    )
    assert "redis" not in worker["depends_on"]
    assert "kafka" not in worker["depends_on"]
    assert worker["command"] == ["start-event-stream-worker"]
    assert worker["healthcheck"]["test"] == ["CMD", "python", "-m", "syntara.eventstreams.consumer_health", "ready"]


def test_backend_image_packages_executable_launcher_and_dependency_free_probes():
    scripts = ROOT / "backend/containers/syntara/scripts"
    launcher = scripts / "start-event-stream-worker"
    assert launcher.stat().st_mode & 0o111
    assert launcher.read_text() == '#!/bin/bash\nexec python -m syntara.eventstreams.consumer_entrypoint "$@"\n'
    containerfile = (scripts.parent / "Containerfile").read_text()
    assert (
        "COPY --chmod=755 containers/syntara/scripts/start-event-stream-worker /usr/local/bin/start-event-stream-worker"
    ) in containerfile
    assert "COPY src/ ./src/" in containerfile
    assert "COPY --from=builder /opt/app-root/ /opt/app-root/" in containerfile
    probe_module = ROOT / "backend/src/syntara/eventstreams/consumer_health.py"
    assert "from syntara." not in probe_module.read_text()


async def test_packaged_launcher_exits_cleanly_when_feature_is_disabled():
    environment = dict(os.environ, APP_EVENTSTREAM_ENABLED="false")
    environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", "")
    launcher = ROOT / "backend/containers/syntara/scripts/start-event-stream-worker"
    process = await asyncio.create_subprocess_exec(
        str(launcher), env=environment, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
    )
    try:
        assert await asyncio.wait_for(process.wait(), timeout=15) == 0
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


def test_disposable_broker_has_no_persistent_storage_or_customer_credentials():
    compose = yaml.safe_load((ROOT / "podman-compose.yml").read_text())
    broker = compose["services"]["kafka"]
    assert broker["profiles"] == ["kafka"]
    assert broker["ports"] == ["127.0.0.1:9093:9093"]
    assert broker["tmpfs"] == ["/tmp/kafka-fixture:rw,mode=1777"]  # noqa: S108 - disposable tmpfs contract
    assert all(volume.startswith("./backend/") and ":ro," in volume for volume in broker["volumes"])
    sample = json.loads((ROOT / "backend/samples/kafka/integration.example.json").read_text())
    config = KafkaConfiguration.model_validate(sample["configuration"])
    assert config.bootstrap_servers == ["kafka:9092"]
    assert not config.insecure_skip_tls_verify
    server = (ROOT / "backend/samples/kafka/server.properties").read_text()
    assert "EXTERNAL://localhost:9093" in server
    assert "INTERNAL://kafka:9092" in server
    assert "SASL_SSL" in server
    assert "auto.create.topics.enable=false" in server


def test_operating_guide_defaults_match_code_defaults():
    guide = (ROOT / "backend/docs/kafka-worker-operations.md").read_text()
    documented = dict(re.findall(r"^\| `(event\w+)` \| `(.+?)` \|$", guide, re.MULTILINE))
    defaults = {name: field.default for name, field in Settings.model_fields.items() if name.startswith("event")}
    assert documented.keys() == defaults.keys()
    for name, value in defaults.items():
        assert documented[name] == str(value).lower()


def test_documented_sizing_examples_match_provider_targets():
    guide = (ROOT / "backend/docs/kafka-worker-operations.md").read_text()
    examples = re.findall(r"^\| (\d+) \| (\d+) \| `([\d, ]+)` \|$", guide, re.MULTILINE)
    assert examples
    for subscriptions, workers, counts in examples:
        identities = [UUID(int=index + 1) for index in range(int(workers))]
        targets = placement_targets(int(subscriptions), identities)
        assert list(targets.values()) == [int(count) for count in counts.split(",")]


def test_placement_reset_example_preserves_evidence_and_other_deployments():
    """Check the example's mutation boundary; no database or restore is performed."""
    example = (ROOT / "backend/samples/kafka/reset-placement.example.sql").read_text()
    sql = re.sub(r"--[^\n]*", "", example)
    statements = [statement.strip() for statement in sql.split(";") if statement.strip()]
    assert len(statements) == 4
    assert statements[0] == "BEGIN"
    assert statements[-1] == "COMMIT"
    update, delete = statements[1:3]
    assert update.startswith(f"UPDATE {EventSubscription.__tablename__} AS subscription\n")
    assignments = update.split("SET", 1)[1].split("WHERE", 1)[0].split(",")
    assert len(assignments) == 2
    assigned = []
    for assignment in assignments:
        match = re.fullmatch(r"\s*(\w+)\s*=\s*NULL\s*", assignment)
        assert match is not None
        assigned.append(match.group(1))
    assert set(assigned) == {"assigned_worker_id", "assignment_lease_until"}
    scope = " ".join(update.split("WHERE", 1)[1].split())
    assert scope == (
        "EXISTS ( SELECT 1 FROM event_subscription_sources AS source "
        "WHERE source.subscription_id = subscription.id "
        "AND source.generation = subscription.active_source_generation "
        "AND source.deployment_id = :'deployment_id' )"
    )
    delete_target, delete_scope = delete.split("\n", 1)
    assert delete_target.split() == ["DELETE", "FROM", EventConsumerWorker.__tablename__]
    assert delete_scope == "WHERE deployment_id = :'deployment_id'"
