"""Subscribe definitions stay strict without importing broker clients."""

import ast
import inspect
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlmodel import SQLModel

from syntara.eventstreams.adapters.kafka_parameters import KafkaSubscribeParameters
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
        "group_id",
        "consumer_group",
        "execution_account_id",
        "service_account_id",
        "execution_service_account_id",
        "selected_account_id",
        "authorized_service_account_ids",
        "filter",
        "bootstrap_servers",
    ],
)
def test_unknown_and_account_fields_forbidden(parameters: dict[str, Any], field: str) -> None:
    # `transport` is intentionally not a field anymore — it must be rejected like any extra key.
    parameters[field] = {"topic": "nested"} if field == "source" else "forbidden"
    with pytest.raises(ValidationError):
        validate_event_subscribe_parameters(parameters)


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


def test_base_schema_fields() -> None:
    assert set(EventSubscribeParameters.model_fields) == {
        "integration_id",
        "credential_id",
        "topic",
        "input_schema",
    }


def test_parameter_modules_have_no_broker_imports() -> None:
    for model in (EventSubscribeParameters, KafkaSubscribeParameters):
        module_path = Path(inspect.getfile(model))
        tree = ast.parse(module_path.read_text())
        imports = [
            node.module if isinstance(node, ast.ImportFrom) else alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        ]
        assert not any(name and name.startswith(("aiokafka", "kafka")) for name in imports)
