"""Publish one frozen JSON record and report broker acknowledgment or uncertainty."""

import asyncio
import contextlib
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy.exc import OperationalError
from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.integrations.adapters.kafka import KafkaAdapter
from syntara.integrations.lib.kafka_producer import create_kafka_publish_producer
from syntara.integrations.models.integration_configuration import KafkaConfiguration
from syntara.workflows.workflow_engine.activities.common import HEARTBEAT_STOP_MONITOR
from syntara.workflows.workflow_engine.activities.kafka_publish_connection import (
    _session_factory,
    current_publish_resources,
)
from syntara.workflows.workflow_engine.activities.kafka_publish_errors import (
    classify_publish_error,
    fail_publish,
    publish_failure,
)
from syntara.workflows.workflow_engine.constants import ENGINE_TIMEOUT_SECONDS_KEY
from syntara.workflows.workflow_engine.models.kafka_publish import (
    KAFKA_PUBLISH_HEARTBEAT_SECONDS,
    KAFKA_PUBLISH_MAX_RECORD_BYTES,
    KAFKA_PUBLISH_REQUEST_TIMEOUT_MS,
    KafkaPublishParameters,
)
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName, KafkaPublishOutput
from syntara.workflows.workflow_engine.services.kafka_publish_message import compile_publish_message
from syntara.workflows.workflow_engine.services.kafka_publish_pool import (
    ProducerEntry,
    PublishSend,
    get_kafka_publish_pool,
)


@dataclass(repr=False)
class _Attempt:
    prior_uncertainty: bool
    send: PublishSend | None = None
    entry: ProducerEntry | None = None
    waiting_for_capacity: bool = False

    @property
    def uncertain(self) -> bool:
        return self.prior_uncertainty or (self.send is not None and self.send.may_have_delivered)


async def _heartbeat(attempt: _Attempt) -> None:
    while True:
        activity.heartbeat(
            {
                HEARTBEAT_STOP_MONITOR: True,
                "delivery_status": "unconfirmed" if attempt.uncertain else "not_sent",
            }
        )
        await asyncio.sleep(KAFKA_PUBLISH_HEARTBEAT_SECONDS)


def _producer_options(config: KafkaConfiguration, credentials: dict[str, Any]) -> dict[str, Any]:
    options = KafkaAdapter(config).connection_options(credentials, timeout_seconds=10)
    options.update(
        bootstrap_servers=list(config.bootstrap_servers),
        client_id="syntara-kafka-publish",
        acks="all",
        enable_idempotence=True,
        max_request_size=KAFKA_PUBLISH_MAX_RECORD_BYTES,
        request_timeout_ms=KAFKA_PUBLISH_REQUEST_TIMEOUT_MS,
        max_batch_size=16_384,
        retry_backoff_ms=100,
        linger_ms=0,
        compression_type=None,
    )
    return options


def _reuse_profile(config: KafkaConfiguration, options: dict[str, Any]) -> str:
    fields = (
        "acks",
        "enable_idempotence",
        "max_request_size",
        "request_timeout_ms",
        "max_batch_size",
        "retry_backoff_ms",
        "linger_ms",
        "compression_type",
    )
    profile = {"connection": config.model_dump(mode="json"), "producer": {key: options[key] for key in fields}}
    return hashlib.sha256(json.dumps(profile, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


async def _recheck_connection(parameters: KafkaPublishParameters, config: KafkaConfiguration, project_id: str) -> None:
    async with _session_factory() as session:
        current, _revision = await current_publish_resources(session, parameters, project_id)
    if current.model_dump(mode="json") != config.model_dump(mode="json"):
        fail_publish("kafka_connection_settings_changed")


async def _publish_once(
    input_config: dict[str, Any], output_config: dict[str, str] | None, project_id: str, attempt: _Attempt
) -> dict[str, Any]:
    parameters = KafkaPublishParameters.model_validate(
        {key: value for key, value in input_config.items() if not key.startswith("_")}
    )
    value, key, headers, size = compile_publish_message(parameters)
    config = KafkaConfiguration.model_validate(input_config["_resolved_integration"])
    await _recheck_connection(parameters, config, project_id)
    options = _producer_options(config, input_config["_resolved_credentials"]["extra_vars"])
    identity = f"{parameters.integration_id}:{parameters.credential_id}"
    reuse_key = f"{identity}:{input_config['_kafka_revision']}:{_reuse_profile(config, options)}"
    pool = get_kafka_publish_pool()

    async def before_send() -> None:
        attempt.waiting_for_capacity = False
        await _recheck_connection(parameters, config, project_id)

    def admitted(entry: ProducerEntry) -> None:
        attempt.entry = entry
        attempt.waiting_for_capacity = False

    attempt.waiting_for_capacity = True
    async with pool.acquire(
        reuse_key, identity, lambda: create_kafka_publish_producer(**options), on_admission=admitted
    ) as entry:
        attempt.waiting_for_capacity = True
        attempt.send = await pool.submit(entry, parameters.topic, value, key, headers, size, before_send=before_send)
        attempt.waiting_for_capacity = False
        if attempt.send.task is None:
            fail_publish("kafka_producer_failed", uncertain=True)
        metadata = await asyncio.shield(attempt.send.task)
    return {
        "output": KafkaPublishOutput(
            topic=metadata.topic,
            partition=metadata.partition,
            offset=str(metadata.offset) if metadata.offset is not None and metadata.offset >= 0 else None,
            timestamp_ms=metadata.timestamp if metadata.timestamp is not None and metadata.timestamp >= 0 else None,
        ).dump(output_config)
    }


def _attempt_seconds(input_config: dict[str, Any]) -> float:
    deadline = datetime.fromisoformat(input_config["_kafka_publish_deadline"])
    remaining = (deadline - datetime.now(UTC)).total_seconds()
    seconds = min(float(input_config[ENGINE_TIMEOUT_SECONDS_KEY]), remaining - 0.1)
    if seconds <= 0:
        fail_publish("kafka_timeout")
    return seconds


@activity.defn(name=ActivityName.KAFKA_PUBLISH)
async def execute_kafka_publish_activity(
    input_config: dict[str, Any], output_config: dict[str, str] | None, project_id: str
) -> dict[str, Any]:
    """Use a frozen secret across Temporal attempts; never rerender message data."""
    attempt = _Attempt(prior_uncertainty=activity.info().attempt > 1)
    heartbeat = asyncio.create_task(_heartbeat(attempt))
    try:
        async with asyncio.timeout(_attempt_seconds(input_config)):
            return await _publish_once(input_config, output_config, project_id, attempt)
    except asyncio.CancelledError:
        # Retain send ownership and report certainty while keeping cancellation
        # in the normal Temporal cancellation path.
        activity.heartbeat({"delivery_status": "unconfirmed" if attempt.uncertain else "not_sent"})
        if attempt.send is not None:
            attempt.send.cancel_before_enqueue()
        raise
    except ApplicationError as exc:
        code = exc.type if exc.type is not None and exc.type.startswith("kafka_") else "kafka_invalid_reference"
        fail_publish(code, uncertain=attempt.uncertain, retryable=not exc.non_retryable)
    except (ValidationError, ValueError, TypeError, KeyError):
        fail_publish("kafka_invalid_message", uncertain=attempt.uncertain)
    except Exception as exc:  # noqa: BLE001 - sanitize unknown SDK/driver errors without exposing their contents
        code, retryable, fatal = classify_publish_error(exc)
        if isinstance(exc, TimeoutError) and attempt.waiting_for_capacity:
            code, retryable = "kafka_capacity_unavailable", True
        if isinstance(exc, OperationalError):
            code, retryable = "kafka_connection_failed", True
        if fatal and attempt.entry is not None:
            get_kafka_publish_pool().retire(attempt.entry)
        error = publish_failure(code, uncertain=attempt.uncertain, retryable=retryable)
        raise error from None
    finally:
        heartbeat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat
