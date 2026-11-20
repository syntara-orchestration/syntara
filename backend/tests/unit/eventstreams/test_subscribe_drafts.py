"""Draft omissions never weaken execution or preflight validation."""

from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from syntara.eventstreams.adapters.kafka_parameters import KafkaSubscribeDraftParameters
from syntara.eventstreams.adapters.subscribe_parameters import (
    validate_event_subscribe_draft_parameters,
    validate_event_subscribe_parameters,
)
from syntara.workflows.validators.workflow_definition import collect_event_subscribe_config_findings


@pytest.mark.parametrize("parameters", [{}, {"topic": "orders"}, {"integration_id": str(uuid4())}])
def test_draft_omissions_stay_invalid_for_execution(parameters: dict[str, Any]) -> None:
    config = validate_event_subscribe_draft_parameters(parameters)
    assert config.model_dump(mode="json", exclude_none=True) == parameters
    with pytest.raises(ValidationError):
        validate_event_subscribe_parameters(parameters)
    definition = {"triggers": [{"id": "draft", "type": "event_subscribe_trigger", "parameters": parameters}]}
    assert collect_event_subscribe_config_findings(definition, allow_incomplete=True) == []
    assert collect_event_subscribe_config_findings(definition)


@pytest.mark.parametrize(
    "parameters",
    [
        {"integration_id": "${trigger.id}"},
        {"credential_id": "not-a-uuid"},
        {"topic": "orders.*"},
        {"topic": "."},
        {"transport": "kafka"},
        {"service_account_id": str(uuid4())},
        {"group_id": ""},
        {"group_id": "a" * 513},
        {"start": None},
        {"start": {"position": "invalid"}},
        {"start": {"added_partition_position": "fail"}},
        {"start": {"offset_gap_policy": "ignore"}},
        {"start": {"max_poll_records": 100}},
    ],
)
def test_supplied_draft_fields_remain_validated(parameters: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        validate_event_subscribe_draft_parameters(parameters, integration_type="kafka")


def test_incompatible_draft_transport_is_rejected() -> None:
    with pytest.raises(ValueError, match="transport"):
        validate_event_subscribe_draft_parameters({}, integration_type="mcp_server")


@pytest.mark.parametrize("integration_type", [None, "kafka"])
@pytest.mark.parametrize("group_id", ["\n", "\x00", "../x", "orders\\reader", "orders\n", "has space"])
def test_draft_rejects_unsafe_consumer_group(integration_type: str | None, group_id: str) -> None:
    with pytest.raises(ValidationError):
        validate_event_subscribe_draft_parameters({"group_id": group_id}, integration_type=integration_type)


@pytest.mark.parametrize("integration_type", [None, "kafka"])
@pytest.mark.parametrize("group_id", [None, "orders-reader"])
def test_draft_consumption_settings_do_not_require_complete_bindings(
    integration_type: str | None, group_id: str | None
) -> None:
    parameters = {"start": {"position": "earliest"}, "group_id": group_id}

    config = validate_event_subscribe_draft_parameters(parameters, integration_type=integration_type)

    assert isinstance(config, KafkaSubscribeDraftParameters)
    assert config.integration_id is None
    assert config.credential_id is None
    assert config.topic is None
    assert config.group_id == group_id
    assert config.start.model_dump(mode="json") == {
        "position": "earliest",
        "added_partition_position": "earliest",
        "offset_gap_policy": "earliest",
    }
    with pytest.raises(ValidationError):
        validate_event_subscribe_parameters(parameters, integration_type=integration_type)
    definition = {"triggers": [{"id": "draft", "type": "event_subscribe_trigger", "parameters": parameters}]}
    assert collect_event_subscribe_config_findings(definition, allow_incomplete=True) == []
    assert collect_event_subscribe_config_findings(definition)


@pytest.mark.parametrize("allow_incomplete", [False, True])
@pytest.mark.parametrize(
    "controls",
    [
        {"start": {"position": "invalid"}},
        {"start": {"offset_gap_policy": "ignore"}},
        {"start": {"enable_auto_commit": True}},
        {"group_id": ""},
        {"group_id": 123},
        {"group_id": "\n"},
        {"group_id": "\x00"},
        {"group_id": "../x"},
    ],
)
def test_workflow_findings_reject_invalid_consumption_controls(
    *, allow_incomplete: bool, controls: dict[str, Any]
) -> None:
    parameters = {
        "integration_id": str(uuid4()),
        "credential_id": str(uuid4()),
        "topic": "orders",
        **controls,
    }
    definition = {"triggers": [{"id": "incoming", "type": "event_subscribe_trigger", "parameters": parameters}]}

    findings = collect_event_subscribe_config_findings(definition, allow_incomplete=allow_incomplete)

    assert len(findings) == 1
    assert findings[0].node_id == "incoming"
    assert findings[0].field_path == "parameters"
