"""Kafka Publish uses real Temporal retries, namespaces and workflow failure routing."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from aiokafka import TopicPartition
from aiokafka.errors import KafkaConnectionError, TopicAuthorizationFailedError
from aiokafka.structs import RecordMetadata
from temporalio import activity
from temporalio.client import WorkflowFailureError, WorkflowHandle
from temporalio.exceptions import CancelledError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from syntara.integrations.models.integration_configuration import KafkaConfiguration
from syntara.workflows.workflow_engine.activities import kafka_publish_activity as sender
from syntara.workflows.workflow_engine.activities import kafka_publish_connection as preparation
from syntara.workflows.workflow_engine.activities.manual_trigger import manual_trigger
from syntara.workflows.workflow_engine.activities.runtime_settings_activity import fetch_workflow_runtime_settings
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.services.kafka_publish_pool import KafkaPublishPool, set_kafka_publish_pool


def _mock_connection(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    config = KafkaConfiguration(bootstrap_servers=["broker.example:9093"])
    context = MagicMock()
    context.return_value.__aenter__ = AsyncMock()
    context.return_value.__aexit__ = AsyncMock(return_value=False)
    for module in (sender, preparation):
        monkeypatch.setattr(module, "_session_factory", context)
        monkeypatch.setattr(module, "current_publish_resources", AsyncMock(return_value=(config, "revision")))
    monkeypatch.setattr(preparation, "create_secret_service", MagicMock())
    resolve = AsyncMock(
        return_value={
            "extra_vars": {"kafka_username": "runtime", "kafka_password": "frozen"},
            "_secret_values": ["frozen"],
        }
    )
    monkeypatch.setattr(preparation, "_resolve_single_credential", resolve)
    monkeypatch.setattr(preparation, "check_publish_topic", AsyncMock())
    return resolve


async def _check_cancellation(
    handle: WorkflowHandle[Any, Any],
    started: asyncio.Event,
    stopped: asyncio.Event,
    pending: list[asyncio.Future[RecordMetadata]],
    attempts: list[tuple[int, bytes]],
) -> None:
    await asyncio.wait_for(started.wait(), timeout=10)
    await handle.cancel()
    with pytest.raises(WorkflowFailureError) as cancelled:
        await handle.result()
    assert isinstance(cancelled.value.cause, CancelledError)
    await asyncio.wait_for(stopped.wait(), timeout=12)
    assert len(attempts) == 1
    assert not pending[0].cancelled()
    pending[0].set_result(RecordMetadata("outcomes", 0, TopicPartition("outcomes", 0), 99, 123, 0, 0))


def _observe_activity_stop(monkeypatch: pytest.MonkeyPatch) -> asyncio.Event:
    stopped = asyncio.Event()
    original_heartbeat = sender._heartbeat

    async def heartbeat(attempt: sender._Attempt) -> None:
        try:
            await original_heartbeat(attempt)
        finally:
            stopped.set()

    monkeypatch.setattr(sender, "_heartbeat", heartbeat)
    return stopped


@pytest.mark.parametrize(
    ("failure", "max_retries", "expected_attempts", "status"),
    [
        (KafkaConnectionError, 1, 2, "completed"),
        (KafkaConnectionError, 0, 1, "failed"),
        (TopicAuthorizationFailedError, 3, 1, "failed"),
        (None, 3, 1, "cancelled"),
    ],
)
async def test_publish_retries_and_downstream_execution(
    temporal_env: WorkflowEnvironment,
    monkeypatch: pytest.MonkeyPatch,
    failure: type[Exception] | None,
    max_retries: int,
    expected_attempts: int,
    status: str,
) -> None:
    resolve = _mock_connection(monkeypatch)
    attempts: list[tuple[int, bytes]] = []
    pending: list[asyncio.Future[RecordMetadata]] = []
    started, stopped = asyncio.Event(), _observe_activity_stop(monkeypatch)

    async def send(topic: str, *, value: bytes, **kwargs: object) -> asyncio.Future[RecordMetadata]:
        attempts.append((activity.info().attempt, value))
        if len(attempts) == 1 and failure is not None:
            message = "sensitive-broker-message"
            raise failure(message)
        future: asyncio.Future[RecordMetadata] = asyncio.get_running_loop().create_future()
        if failure is None:
            pending.append(future)
            started.set()
            return future
        future.set_result(RecordMetadata(topic, 0, TopicPartition(topic, 0), 99, 123, 0, 0))
        return future

    producer = MagicMock(start=AsyncMock(), stop=AsyncMock(), send=AsyncMock(side_effect=send))
    monkeypatch.setattr(sender, "AIOKafkaProducer", MagicMock(return_value=producer))
    pool = KafkaPublishPool(2)
    set_kafka_publish_pool(pool)
    parameters = {
        "integration_id": str(uuid4()),
        "credential_id": str(uuid4()),
        "topic": "outcomes",
        "payload": "${trigger.payload}",
    }
    definition = {
        "schema_version": "2.0.0",
        "name": "Publish execution",
        "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {
                "id": "publish",
                "type": "kafka_publish",
                "parameters": parameters,
                "settings": {"retry_policy": {"max_retries": max_retries}},
            },
            {"id": "downstream", "type": "kafka_publish", "parameters": {**parameters, "payload": "${publish.offset}"}},
        ],
        "edges": [{"from": "trigger", "to": "publish"}, {"from": "publish", "to": "downstream"}],
    }
    queue = f"publish-{uuid4()}"
    try:
        async with Worker(
            temporal_env.client,
            task_queue=queue,
            workflows=[OrchestratorWorkflow],
            activities=[
                manual_trigger,
                fetch_workflow_runtime_settings,
                preparation.prepare_kafka_publish,
                sender.execute_kafka_publish_activity,
            ],
        ):
            handle = await temporal_env.client.start_workflow(
                OrchestratorWorkflow.run,
                args=[
                    definition,
                    str(uuid4()),
                    "trigger",
                    {"payload": {"literal": "${do.not.evaluate}"}},
                    True,
                    None,
                    None,
                    None,
                    {"workflow_context": {"workflow": {"project_id": str(uuid4())}}},
                ],
                id=f"publish-{uuid4()}",
                task_queue=queue,
            )
            if status == "cancelled":
                await _check_cancellation(handle, started, stopped, pending, attempts)
                return
            result = await handle.result()
        assert result["status"] == status
        assert [attempt for attempt, _value in attempts[:expected_attempts]] == list(range(1, expected_attempts + 1))
        assert all(value == b'{"literal":"${do.not.evaluate}"}' for _attempt, value in attempts[:expected_attempts])
        if status == "completed":
            assert result["activity_outputs"]["downstream"]["offset"] == "99"
            assert attempts[-1][1] == b'"99"'
            assert resolve.await_count == 2  # One snapshot per invocation, not per attempt.
        else:
            assert "downstream" not in result["completed_activities"]
            assert resolve.await_count == 1
            assert result["activity_outputs"]["publish"]["delivery_status"] == (
                "unconfirmed" if expected_attempts > 1 else "not_sent"
            )
        assert "sensitive-broker-message" not in str(result)
    finally:
        for future in pending:
            if not future.done():
                future.set_result(RecordMetadata("outcomes", 0, TopicPartition("outcomes", 0), 99, 123, 0, 0))
        await pool.close()
        set_kafka_publish_pool(None)
