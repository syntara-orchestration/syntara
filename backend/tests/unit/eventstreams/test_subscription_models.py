"""Subscription/source model invariants, including the absence of account gates."""

from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_mock_engine

from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription

# Columns that would signal a selected-account or standing-execution gate. This
# story must not introduce any of them (scope exclusion).
_FORBIDDEN_SUBSTRINGS = ("account", "execution_principal", "selected", "service_account")
_POSTGRESQL = create_mock_engine("postgresql://", lambda *_args, **_kwargs: None).dialect


def test_subscription_has_no_account_binding_or_execution_columns() -> None:
    columns = set(EventSubscription.__table__.columns.keys())  # type: ignore[attr-defined]
    for name in columns:
        assert not any(bad in name for bad in _FORBIDDEN_SUBSTRINGS), name
    # Positive identity/lifecycle columns are present.
    assert {"workflow_id", "trigger_node_id", "published_version_id", "configuration_revision"} <= columns


def test_source_has_no_secret_columns() -> None:
    columns = set(EventSubscriptionSource.__table__.columns.keys())  # type: ignore[attr-defined]
    for forbidden in ("secret", "password", "credential_secret", "sasl"):
        assert not any(forbidden in name for name in columns), forbidden


def test_active_trigger_partial_unique_index_exists() -> None:
    indexes = EventSubscription.__table__.indexes  # type: ignore[attr-defined]
    index = next(i for i in indexes if i.name == "ix_event_subscriptions_workflow_trigger_active")
    assert index.unique is True


def test_kafka_group_id_unique_index_exists_on_source() -> None:
    indexes = EventSubscriptionSource.__table__.indexes  # type: ignore[attr-defined]
    names = {i.name for i in indexes}
    assert "ix_event_subscription_sources_kafka_group_id" in names


def test_kafka_source_configuration_rejects_reserved_topic() -> None:
    with pytest.raises(ValidationError):
        KafkaSourceConfiguration(topic=".", group_id="syntara.d.s.1")


def test_kafka_source_configuration_requires_group_id() -> None:
    with pytest.raises(ValidationError):
        KafkaSourceConfiguration(topic="orders", group_id="")


def test_source_configuration_round_trips_through_discriminated_union() -> None:
    integration_id = uuid4()
    source = EventSubscriptionSource(
        subscription_id=uuid4(),
        deployment_id=uuid4(),
        generation=1,
        integration_id=integration_id,
        integration_identity=integration_id,
        transport="kafka",
        configuration=KafkaSourceConfiguration(topic="orders", group_id="syntara.d.s.1"),
    )
    assert isinstance(source.configuration, KafkaSourceConfiguration)
    assert source.configuration.transport == "kafka"


@pytest.mark.parametrize("partition_ids", [[], [0, 0], [-1], [True], [1.0], ["1"]])
def test_initial_partition_set_rejects_invalid_ids(partition_ids: object) -> None:
    with pytest.raises(ValidationError):
        KafkaSourceConfiguration.model_validate(
            {"topic": "orders", "group_id": "syntara.d.s.1", "initial_partition_ids": partition_ids}
        )


def test_initial_partition_set_is_sorted_and_round_trips_through_jsonb() -> None:
    configuration = KafkaSourceConfiguration.model_validate(
        {"topic": "orders", "group_id": "syntara.d.s.1", "initial_partition_ids": [5, 0, 2]}
    )
    column_type = EventSubscriptionSource.__table__.c.configuration.type  # type: ignore[attr-defined]
    stored = column_type.process_bind_param(configuration, _POSTGRESQL)

    assert stored["initial_partition_ids"] == [0, 2, 5]
    restored = column_type.process_result_value(stored, _POSTGRESQL)
    assert isinstance(restored, KafkaSourceConfiguration)
    assert restored.initial_partition_ids == (0, 2, 5)


def test_old_configuration_without_partition_set_decodes_as_uncaptured() -> None:
    column_type = EventSubscriptionSource.__table__.c.configuration.type  # type: ignore[attr-defined]
    restored = column_type.process_result_value(
        {"transport": "kafka", "topic": "orders", "group_id": "syntara.d.s.1"}, _POSTGRESQL
    )

    assert isinstance(restored, KafkaSourceConfiguration)
    assert restored.initial_partition_ids is None
