"""Local compose and configuration contracts; no live deployment or broker claims."""

import json
import re
from pathlib import Path
from uuid import UUID

import yaml

from syntara.core.config.base import Settings
from syntara.core.constants import EventDeliveryDefaults, EventWorkerDefaults
from syntara.eventstreams.consumer_service import placement_targets
from syntara.eventstreams.models.consumer_worker import EventConsumerWorker
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.integrations.models.integration_configuration import KafkaConfiguration

ROOT = Path(__file__).resolve().parents[4]


def example_defaults(path):
    values = re.findall(r"^# (APP_EVENT\w+)=(.+)$", path.read_text(), re.MULTILINE)
    assert len(values) == len(dict(values)), f"Duplicate event configuration in {path}"
    return dict(values)


def test_environment_examples_and_compose_match_settings_defaults():
    root = example_defaults(ROOT / ".env.example")
    assert root == example_defaults(ROOT / "backend/.env.example")
    assert root["APP_EVENTSTREAM_ENABLED"] == "false"
    assert root["APP_EVENT_DELIVERY_CACHE_ENABLED"] == "false"
    compose = yaml.safe_load((ROOT / "podman-compose.yml").read_text())
    worker = compose["services"]["eventstream-consumer"]
    env = dict(value.split("=", 1) for value in worker["environment"] if "=" in value)
    inherited = {value for value in worker["environment"] if "=" not in value}
    assert inherited == {"APP_EVENT_DELIVERY_CACHE_EPOCH", "APP_EVENT_DELIVERY_CACHE_CLOCK_ERROR_BOUND_SECONDS"}
    task_queue = Settings.model_fields["task_queue"].default
    assert env["APP_TASK_QUEUE"] == task_queue
    for path in [ROOT / ".env.example", ROOT / "backend/.env.example"]:
        match = re.search(r"^APP_TASK_QUEUE=([^\s#]+)", path.read_text(), re.MULTILINE)
        assert match is not None
        assert match.group(1) == task_queue
    for key, value in root.items():
        default = Settings.model_fields[key.removeprefix("APP_").lower()].default
        if default is None:
            assert value.startswith("<")
            assert value.endswith(">")
            assert key in inherited
            continue
        assert value == str(default).lower()
        assert env[key] == "${" + key + ":-" + value + "}"
    assert worker["profiles"] == ["eventstream"]
    assert worker["stop_grace_period"] == "60s"
    cleanup_headroom = EventWorkerDefaults.PLACEMENT_TIMEOUT_SECONDS + EventWorkerDefaults.HINT_TIMEOUT_SECONDS
    assert int(worker["stop_grace_period"].removesuffix("s")) > (
        float(root["APP_EVENT_DRAIN_TIMEOUT_SECONDS"]) + cleanup_headroom
    )
    assert "redis" not in worker["depends_on"]
    assert "kafka" not in worker["depends_on"]
    assert worker["command"] == ["python", "-m", "syntara.eventstreams.consumer_entrypoint"]


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


def test_terminal_retention_and_claim_cache_lifetimes_remain_independent():
    assert Settings.model_fields["event_delivery_retention_seconds"].default == 3600
    assert EventDeliveryDefaults.CLAIM_LEASE_SECONDS == 60
    assert EventDeliveryDefaults.CLAIM_RENEWAL_INTERVAL_SECONDS == 20
    assert EventDeliveryDefaults.TERMINAL_CACHE_TTL_SECONDS == 60


def test_operating_guide_configuration_matches_environment_examples():
    guide = (ROOT / "backend/docs/kafka-worker-operations.md").read_text()
    documented = dict(re.findall(r"^\| `(APP_EVENT\w+)` \| (.+?) \|$", guide, re.MULTILINE))
    examples = example_defaults(ROOT / ".env.example")
    assert documented.keys() == examples.keys()
    for key, value in examples.items():
        if Settings.model_fields[key.removeprefix("APP_").lower()].default is None:
            assert documented[key].startswith("unset;")
        else:
            assert documented[key] == f"`{value}`"


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
