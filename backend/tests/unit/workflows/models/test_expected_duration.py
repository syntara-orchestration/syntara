"""Expected duration is a persisted advisory setting, independent of execution limits."""

import pytest
from pydantic import ValidationError

from syntara.workflows.workflow_engine.graph import ActivityNode
from syntara.workflows.workflow_engine.models.workflow_definition import (
    NodeSettingsCof,
    NodeSettingsCofDisabled,
    NodeSettingsFull,
    NodeSettingsNoRetry,
)
from syntara.workflows.workflow_engine.node_settings_resolver import resolve_retry_policy, resolve_timeout


@pytest.mark.parametrize("model", [NodeSettingsCof, NodeSettingsCofDisabled, NodeSettingsNoRetry, NodeSettingsFull])
def test_expected_duration_round_trip(model: type[NodeSettingsCof]) -> None:
    """All supported shared settings retain a positive threshold and allow clearing it."""
    assert model.model_validate({"expected_duration": 12}).model_dump(exclude_none=True)["expected_duration"] == 12
    assert "expected_duration" not in model.model_validate({"expected_duration": None}).model_dump(exclude_none=True)


@pytest.mark.parametrize("value", [0, -1, 1.5])
def test_expected_duration_requires_positive_integer(value: float) -> None:
    """Reject thresholds that cannot be represented as a positive whole second."""
    with pytest.raises(ValidationError):
        NodeSettingsFull.model_validate({"expected_duration": value})


def test_expected_duration_does_not_change_timeout_or_retries() -> None:
    """A warning threshold must never become a scheduling or cancellation deadline."""
    settings = {"timeout": 30, "retry_policy": {"max_retries": 0}}
    original = ActivityNode.from_dict(
        {"id": "publish", "type": "kafka_publish", "parameters": {}, "settings": settings}
    )
    warning = ActivityNode.from_dict(
        {
            "id": "publish",
            "type": "kafka_publish",
            "parameters": {},
            "settings": {**settings, "expected_duration": 1},
        }
    )
    assert warning.to_dict()["settings"]["expected_duration"] == 1
    assert resolve_timeout(warning, {}) == resolve_timeout(original, {}) == 30
    assert resolve_retry_policy(warning, {}) == resolve_retry_policy(original, {})
