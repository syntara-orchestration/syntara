"""Local compose and configuration contracts; no live deployment or broker claims."""

import json
import re
from pathlib import Path

import yaml

from syntara.core.config.base import Settings
from syntara.core.constants import EventDeliveryDefaults
from syntara.integrations.models.integration_configuration import KafkaConfiguration

ROOT = Path(__file__).resolve().parents[4]


def example_defaults(path):
    values = re.findall(r"^# (APP_EVENT\w+)=(.+)$", path.read_text(), re.MULTILINE)
    assert len(values) == len(dict(values)), f"Duplicate event configuration in {path}"
    return dict(values)


def test_environment_examples_and_compose_match_settings_defaults():
    root = example_defaults(ROOT / ".env.example")
    assert root == example_defaults(ROOT / "backend/.env.example")
    compose = yaml.safe_load((ROOT / "podman-compose.yml").read_text())
    worker = compose["services"]["eventstream-consumer"]
    env = dict(value.split("=", 1) for value in worker["environment"] if "=" in value)
    inherited = {value for value in worker["environment"] if "=" not in value}
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
    assert int(worker["stop_grace_period"].removesuffix("s")) > float(root["APP_EVENT_DRAIN_TIMEOUT_SECONDS"])
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
