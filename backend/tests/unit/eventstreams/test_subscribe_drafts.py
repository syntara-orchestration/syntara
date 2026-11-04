"""Draft omissions never weaken execution or preflight validation."""

from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

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
        {"group_id": "custom"},
    ],
)
def test_supplied_draft_fields_remain_validated(parameters: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        validate_event_subscribe_draft_parameters(parameters, integration_type="kafka")


def test_incompatible_draft_transport_is_rejected() -> None:
    with pytest.raises(ValueError, match="transport"):
        validate_event_subscribe_draft_parameters({}, integration_type="mcp_server")
