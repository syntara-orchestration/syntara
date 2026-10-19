"""SubscriptionSnapshot is an immutable projection of a subscription and source."""

from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot


def _subscription(**overrides: object) -> EventSubscription:
    defaults: dict[str, object] = {
        "workflow_id": uuid4(),
        "project_id": uuid4(),
        "trigger_node_id": "incoming",
        "published_version_id": uuid4(),
        "active_source_generation": 1,
        "configuration_revision": 1,
        "runtime_credential_id": uuid4(),
        "input_schema": {"type": "object"},
        "desired_enabled": True,
        "paused": False,
        "retired": False,
        "enabled_by": uuid4(),
        "created_by": uuid4(),
    }
    defaults.update(overrides)
    return EventSubscription(**defaults)


def _source(subscription: EventSubscription, *, generation: int = 1) -> EventSubscriptionSource:
    integration_id = uuid4()
    return EventSubscriptionSource(
        subscription_id=subscription.id,
        deployment_id=uuid4(),
        generation=generation,
        integration_id=integration_id,
        integration_identity=integration_id,
        transport="kafka",
        configuration=KafkaSourceConfiguration(
            topic="infra.alerts", group_id=f"syntara.d.{subscription.id}.{generation}"
        ),
    )


def test_from_models_maps_identity_and_configuration() -> None:
    subscription = _subscription()
    source = _source(subscription, generation=2)
    subscription.active_source_generation = 2

    snapshot = SubscriptionSnapshot.from_models(subscription, source)

    assert snapshot.subscription_id == subscription.id
    assert snapshot.workflow_id == subscription.workflow_id
    assert snapshot.trigger_node_id == "incoming"
    assert snapshot.published_version_id == subscription.published_version_id
    assert snapshot.configuration_revision == 1
    assert snapshot.source_id == source.id
    assert snapshot.source_generation == 2
    assert snapshot.transport == "kafka"
    assert snapshot.integration_identity == source.integration_identity
    assert snapshot.configuration.group_id == source.configuration.group_id
    assert snapshot.runtime_credential_id == subscription.runtime_credential_id
    assert snapshot.enabled_by == subscription.enabled_by


def test_snapshot_reflects_lifecycle_flags() -> None:
    subscription = _subscription(desired_enabled=False, paused=True, retired=True)
    source = _source(subscription)

    snapshot = SubscriptionSnapshot.from_models(subscription, source)

    assert snapshot.desired_enabled is False
    assert snapshot.paused is True
    assert snapshot.retired is True


def test_snapshot_is_frozen() -> None:
    subscription = _subscription()
    snapshot = SubscriptionSnapshot.from_models(subscription, _source(subscription))

    with pytest.raises(ValidationError):
        snapshot.configuration_revision = 99


def test_input_schema_is_deeply_immutable() -> None:
    schema = {"type": "object", "properties": {"sev": {"enum": ["high", "low"]}}, "required": ["sev"]}
    subscription = _subscription(input_schema=schema)
    snapshot = SubscriptionSnapshot.from_models(subscription, _source(subscription))

    assert snapshot.input_schema is not None
    with pytest.raises(TypeError):
        snapshot.input_schema["type"] = "array"  # type: ignore[index]
    nested = snapshot.input_schema["properties"]["sev"]
    with pytest.raises(TypeError):
        nested["enum"] = []
    # Lists are frozen to tuples at every depth.
    assert snapshot.input_schema["required"] == ("sev",)


def test_input_schema_detached_from_source_definition() -> None:
    schema: dict[str, Any] = {"type": "object", "properties": {"a": {"x": 1}}}
    subscription = _subscription(input_schema=schema)
    snapshot = SubscriptionSnapshot.from_models(subscription, _source(subscription))

    # Mutating the original definition after snapshot creation must not leak in.
    schema["type"] = "array"
    schema["properties"]["a"]["x"] = 999

    assert snapshot.input_schema is not None
    assert snapshot.input_schema["type"] == "object"
    assert snapshot.input_schema["properties"]["a"]["x"] == 1


def test_input_schema_serializes_to_plain_json() -> None:
    import json

    subscription = _subscription(input_schema={"type": "object", "required": ["a"]})
    snapshot = SubscriptionSnapshot.from_models(subscription, _source(subscription))

    dumped = json.loads(json.dumps(snapshot.model_dump(mode="json")))
    assert dumped["input_schema"] == {"type": "object", "required": ["a"]}


def test_none_input_schema_is_preserved() -> None:
    subscription = _subscription(input_schema=None)
    snapshot = SubscriptionSnapshot.from_models(subscription, _source(subscription))

    assert snapshot.input_schema is None
