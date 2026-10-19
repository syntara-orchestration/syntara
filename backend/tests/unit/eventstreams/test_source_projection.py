"""Source projection builds Kafka group identity and detects source replacement."""

from uuid import uuid4

import pytest

from syntara.eventstreams.adapters.kafka_parameters import KafkaSubscribeParameters
from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration
from syntara.eventstreams.adapters.source_projection import (
    project_source_configuration,
    source_address_identity,
)
from syntara.eventstreams.core.subscribe_parameters import EventSubscribeParameters


def _kafka_params(topic: str = "infra.alerts") -> KafkaSubscribeParameters:
    return KafkaSubscribeParameters(
        integration_id=uuid4(),
        credential_id=uuid4(),
        transport="kafka",
        topic=topic,
    )


def test_project_source_configuration_builds_stable_group_id() -> None:
    deployment_id = uuid4()
    subscription_id = uuid4()

    config = project_source_configuration(
        _kafka_params(),
        deployment_id=deployment_id,
        subscription_id=subscription_id,
        generation=3,
    )

    assert isinstance(config, KafkaSourceConfiguration)
    assert config.topic == "infra.alerts"
    assert config.group_id == f"syntara.{deployment_id}.{subscription_id}.3"


def test_group_id_changes_only_with_generation_for_same_subscription() -> None:
    deployment_id = uuid4()
    subscription_id = uuid4()
    params = _kafka_params()

    gen1 = project_source_configuration(
        params, deployment_id=deployment_id, subscription_id=subscription_id, generation=1
    )
    gen2 = project_source_configuration(
        params, deployment_id=deployment_id, subscription_id=subscription_id, generation=2
    )

    assert isinstance(gen1, KafkaSourceConfiguration)
    assert isinstance(gen2, KafkaSourceConfiguration)
    assert gen1.group_id != gen2.group_id
    assert gen1.group_id.endswith(".1")
    assert gen2.group_id.endswith(".2")


def test_source_address_identity_is_transport_and_topic() -> None:
    config = project_source_configuration(
        _kafka_params("orders"),
        deployment_id=uuid4(),
        subscription_id=uuid4(),
        generation=1,
    )

    assert source_address_identity(config) == ("kafka", "orders")


def test_same_topic_different_generation_shares_address_identity() -> None:
    subscription_id = uuid4()
    deployment_id = uuid4()
    params = _kafka_params("orders")

    first = project_source_configuration(
        params, deployment_id=deployment_id, subscription_id=subscription_id, generation=1
    )
    second = project_source_configuration(
        params, deployment_id=deployment_id, subscription_id=subscription_id, generation=5
    )

    # Address identity ignores the group id/generation, so a plain republish is "same source".
    assert source_address_identity(first) == source_address_identity(second)


def test_project_source_configuration_rejects_unsupported_transport() -> None:
    base = EventSubscribeParameters(
        integration_id=uuid4(),
        credential_id=uuid4(),
        transport="rabbitmq",
    )

    with pytest.raises(ValueError, match="Unsupported Event Subscribe transport"):
        project_source_configuration(base, deployment_id=uuid4(), subscription_id=uuid4(), generation=1)
