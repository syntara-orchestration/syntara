"""Subscribe definitions stay strict without importing broker clients."""

import ast
import inspect
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlmodel import SQLModel

from syntara.eventstreams.adapters.kafka_parameters import KafkaSubscribeDraftParameters, KafkaSubscribeParameters
from syntara.eventstreams.adapters.kafka_start_configuration import KafkaStartConfiguration
from syntara.eventstreams.adapters.subscribe_parameters import validate_event_subscribe_parameters
from syntara.eventstreams.core.subscribe_parameters import EventSubscribeParameters


@pytest.fixture
def parameters() -> dict[str, Any]:
    """A flat definition with explicit runtime resource bindings.

    Transport is NOT a client field: it is resolved from the Integration type
    passed to the validator.
    """
    return {
        "integration_id": str(uuid4()),
        "credential_id": str(uuid4()),
        "topic": "infra.alerts",
    }


def test_valid_parameters(parameters: dict[str, Any]) -> None:
    config = validate_event_subscribe_parameters(parameters, integration_type="kafka")
    assert isinstance(config, EventSubscribeParameters)
    assert isinstance(config, SQLModel)
    assert isinstance(config, KafkaSubscribeParameters)
    assert config.integration_id == UUID(parameters["integration_id"])
    assert config.credential_id == UUID(parameters["credential_id"])
    assert config.topic == parameters["topic"]
    assert config.input_schema is None
    assert config.filter is None
    assert config.start.model_dump(mode="json") == {
        "position": "latest",
        "added_partition_position": "earliest",
        "offset_gap_policy": "earliest",
    }
    assert config.group_id is None


def test_structural_pass_is_transport_neutral(parameters: dict[str, Any]) -> None:
    # Without an Integration type, only the transport-neutral base contract applies.
    config = validate_event_subscribe_parameters(parameters)
    assert isinstance(config, EventSubscribeParameters)
    assert not isinstance(config, KafkaSubscribeParameters)


@pytest.mark.parametrize("field", ["integration_id", "credential_id", "topic"])
def test_required_fields(parameters: dict[str, Any], field: str) -> None:
    parameters.pop(field)
    with pytest.raises(ValueError):
        validate_event_subscribe_parameters(parameters)


@pytest.mark.parametrize(
    "field",
    [
        "unknown",
        "transport",
        "source",
        "consumer_group",
        "execution_account_id",
        "service_account_id",
        "execution_service_account_id",
        "selected_account_id",
        "authorized_service_account_ids",
        "bootstrap_servers",
    ],
)
def test_unknown_and_account_fields_forbidden(parameters: dict[str, Any], field: str) -> None:
    # `transport` is intentionally not a field anymore — it must be rejected like any extra key.
    parameters[field] = {"topic": "nested"} if field == "source" else "forbidden"
    with pytest.raises(ValidationError):
        validate_event_subscribe_parameters(parameters)


@pytest.mark.parametrize("integration_type", [None, "kafka"])
def test_designer_cannot_supply_valid_partition_membership(
    parameters: dict[str, Any], integration_type: str | None
) -> None:
    parameters["initial_partition_ids"] = [0, 2, 5]
    with pytest.raises(ValidationError, match="extra_forbidden"):
        validate_event_subscribe_parameters(parameters, integration_type=integration_type)


@pytest.mark.parametrize("field", ["integration_id", "credential_id"])
def test_uuid_expression_references_forbidden(parameters: dict[str, Any], field: str) -> None:
    parameters[field] = "${trigger.value}"
    with pytest.raises(ValueError):
        validate_event_subscribe_parameters(parameters)


@pytest.mark.parametrize(
    "topic", ["", ".", "..", "alerts.*", "alerts,other", " a", "a/b", "a" * 250, "${trigger.value}"]
)
def test_kafka_topic_is_one_exact_name(parameters: dict[str, Any], topic: str) -> None:
    # Kafka's naming rules are enforced only once the Integration resolves to kafka.
    parameters["topic"] = topic
    with pytest.raises(ValidationError):
        validate_event_subscribe_parameters(parameters, integration_type="kafka")


def test_incompatible_integration_rejected(parameters: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="Integration type"):
        validate_event_subscribe_parameters(parameters, integration_type="mcp_server")


def test_non_object_parameters_rejected() -> None:
    with pytest.raises(TypeError):
        validate_event_subscribe_parameters(["not", "a", "dict"])


@pytest.mark.parametrize("input_schema", [None, {}, {"type": "object"}])
def test_optional_payload_schema(parameters: dict[str, Any], input_schema: dict[str, Any] | None) -> None:
    parameters["input_schema"] = input_schema
    assert validate_event_subscribe_parameters(parameters).input_schema == input_schema


@pytest.mark.parametrize("integration_type", [None, "kafka"])
@pytest.mark.parametrize("position", ["latest", "earliest"])
@pytest.mark.parametrize("added_partition_position", ["latest", "earliest"])
@pytest.mark.parametrize("offset_gap_policy", ["fail", "earliest", "latest"])
def test_approved_reading_settings_survive_validation(
    parameters: dict[str, Any],
    integration_type: str | None,
    position: str,
    added_partition_position: str,
    offset_gap_policy: str,
) -> None:
    settings = {
        "position": position,
        "added_partition_position": added_partition_position,
        "offset_gap_policy": offset_gap_policy,
    }
    parameters.update(start=settings, group_id="orders-reader")

    config = validate_event_subscribe_parameters(parameters, integration_type=integration_type)

    assert isinstance(config, KafkaSubscribeParameters)
    assert config.start.model_dump(mode="json") == settings
    assert config.group_id == "orders-reader"
    assert config.model_dump(mode="json")["start"] == settings


def test_partial_reading_settings_use_defaults(parameters: dict[str, Any]) -> None:
    parameters["start"] = {"position": "earliest"}

    config = validate_event_subscribe_parameters(parameters)

    assert isinstance(config, KafkaSubscribeParameters)
    assert config.start.model_dump(mode="json") == {
        "position": "earliest",
        "added_partition_position": "earliest",
        "offset_gap_policy": "earliest",
    }


@pytest.mark.parametrize("integration_type", [None, "kafka"])
@pytest.mark.parametrize("group_id", [None, "orders-reader", "Orders.reader_01-v2", "a" * 512])
def test_optional_consumer_group(
    parameters: dict[str, Any], integration_type: str | None, group_id: str | None
) -> None:
    parameters["group_id"] = group_id

    config = validate_event_subscribe_parameters(parameters, integration_type=integration_type)

    assert isinstance(config, KafkaSubscribeParameters)
    assert config.group_id == group_id
    assert config.start == KafkaStartConfiguration()


@pytest.mark.parametrize("integration_type", [None, "kafka"])
@pytest.mark.parametrize(
    "start",
    [
        None,
        [],
        "earliest",
        {"position": "fail"},
        {"position": None},
        {"position": True},
        {"added_partition_position": "fail"},
        {"added_partition_position": None},
        {"offset_gap_policy": "ignore"},
        {"offset_gap_policy": None},
        {"auto_offset_reset": "latest"},
        {"position": "earliest", "offset": 100},
    ],
)
def test_unsupported_reading_settings_rejected(
    parameters: dict[str, Any], integration_type: str | None, start: object
) -> None:
    parameters["start"] = start

    with pytest.raises(ValidationError):
        validate_event_subscribe_parameters(parameters, integration_type=integration_type)


@pytest.mark.parametrize("integration_type", [None, "kafka"])
@pytest.mark.parametrize(
    "group_id",
    [
        "",
        "a" * 513,
        True,
        123,
        {},
        "\n",
        "\x00",
        "../x",
        "orders\\reader",
        "orders\n",
        "orders\r\n",
        "has space",
        "orders\treader",
    ],
)
def test_invalid_consumer_group_rejected(
    parameters: dict[str, Any], integration_type: str | None, group_id: object
) -> None:
    parameters["group_id"] = group_id

    with pytest.raises(ValidationError):
        validate_event_subscribe_parameters(parameters, integration_type=integration_type)


@pytest.mark.parametrize("field", ["enable_auto_commit", "auto_offset_reset", "max_poll_records", "start.position"])
def test_consumer_management_overrides_rejected(parameters: dict[str, Any], field: str) -> None:
    parameters.update(start={}, group_id="orders-reader")
    parameters[field] = "unsupported"

    with pytest.raises(ValidationError):
        validate_event_subscribe_parameters(parameters, integration_type="kafka")


def test_kafka_controls_do_not_allow_an_unsupported_integration(parameters: dict[str, Any]) -> None:
    parameters.update(start={"position": "earliest"}, group_id="orders-reader")

    with pytest.raises(ValueError, match="Integration type"):
        validate_event_subscribe_parameters(parameters, integration_type="mcp_server")


def test_base_schema_fields() -> None:
    assert set(EventSubscribeParameters.model_fields) == {
        "integration_id",
        "credential_id",
        "topic",
        "input_schema",
        "filter",
    }


def test_parameter_modules_have_no_broker_imports() -> None:
    for model in (
        EventSubscribeParameters,
        KafkaSubscribeParameters,
        KafkaSubscribeDraftParameters,
        KafkaStartConfiguration,
    ):
        module_path = Path(inspect.getfile(model))
        tree = ast.parse(module_path.read_text())
        imports = [
            node.module if isinstance(node, ast.ImportFrom) else alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        ]
        assert not any(name and name.startswith(("aiokafka", "kafka")) for name in imports)
