"""Verify Publish preparation and Temporal scheduling use one bounded invocation."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from temporalio import workflow
from temporalio.exceptions import ApplicationError

from syntara.workflows.utils.namespace_resolver import NamespaceResolver
from syntara.workflows.workflow_engine.activities.kafka_publish_connection import prepare_kafka_publish
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.graph import ActivityNode

PARAMETERS: dict[str, Any] = {
    "integration_id": "11111111-1111-4111-8111-111111111111",
    "credential_id": "22222222-2222-4222-8222-222222222222",
    "topic": "outcomes",
    "payload": "${trigger.payload}",
    "headers": "${trigger.headers}",
}


@pytest.fixture
def dispatch(monkeypatch: pytest.MonkeyPatch) -> tuple[OrchestratorWorkflow, AsyncMock]:
    """Isolate scheduling while retaining real validation, encoding and settings."""
    engine = OrchestratorWorkflow()
    engine._project_id = "project"
    engine._runtime_settings = {}
    engine._secret_values = set()
    engine.node_inputs = {}
    monkeypatch.setattr(workflow, "now", lambda: datetime(2026, 1, 1, tzinfo=UTC))
    call = AsyncMock()
    monkeypatch.setattr(workflow, "execute_activity", call)
    return engine, call


@pytest.mark.asyncio
async def test_temporal_retries_reuse_prepared_arguments_and_bounded_schedule(
    dispatch: tuple[OrchestratorWorkflow, AsyncMock],
) -> None:
    engine, call = dispatch
    resolved = {**PARAMETERS, "payload": None, "headers": []}
    prepared = {**resolved, "_resolved_credentials": {"_secret_values": ["synthetic-secret"]}}
    call.side_effect = [prepared, {"output": {"offset": "99"}}]
    result = await engine._dispatch_kafka_publish(ActivityNode("publish", "kafka_publish", PARAMETERS), resolved, 30)
    assert result == {"output": {"offset": "99"}}
    assert call.await_count == 2
    assert call.await_args_list[0].args[0] == prepare_kafka_publish
    scheduling = call.await_args_list[1].kwargs
    assert scheduling["heartbeat_timeout"].total_seconds() == 10
    assert scheduling["schedule_to_close_timeout"].total_seconds() == 180
    assert scheduling["retry_policy"].maximum_attempts == 4
    assert "synthetic-secret" in engine._secret_values


@pytest.mark.asyncio
async def test_serialized_argument_limit_fails_before_preparation(
    dispatch: tuple[OrchestratorWorkflow, AsyncMock],
) -> None:
    engine, call = dispatch
    resolved = {**PARAMETERS, "payload": "é" * 350_000, "headers": []}
    with pytest.raises(ApplicationError) as error:
        await engine._dispatch_kafka_publish(ActivityNode("publish", "kafka_publish", PARAMETERS), resolved, 30)
    assert error.value.type == "kafka_arguments_too_large"
    assert error.value.non_retryable
    call.assert_not_awaited()


@pytest.mark.asyncio
async def test_stored_destination_template_cannot_bypass_validation(
    dispatch: tuple[OrchestratorWorkflow, AsyncMock],
) -> None:
    engine, call = dispatch
    node = ActivityNode("publish", "kafka_publish", {**PARAMETERS, "topic": "${trigger.topic}"})
    with pytest.raises(ApplicationError) as error:
        await engine._dispatch_kafka_publish(
            node, {**PARAMETERS, "topic": "resolved-topic", "payload": None, "headers": []}, 30
        )
    assert error.value.type == "kafka_invalid_message"
    call.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_template_reference_fails_safely_before_preparation(
    dispatch: tuple[OrchestratorWorkflow, AsyncMock],
) -> None:
    engine, call = dispatch
    engine.resolver = NamespaceResolver()
    engine.loop_body_map = {}
    with pytest.raises(ApplicationError) as error:
        await engine._dispatch_kafka_publish(ActivityNode("publish", "kafka_publish", PARAMETERS), None, 30)
    assert error.value.type == "kafka_invalid_message"
    assert error.value.details[0]["output"]["delivery_status"] == "not_sent"
    call.assert_not_awaited()
