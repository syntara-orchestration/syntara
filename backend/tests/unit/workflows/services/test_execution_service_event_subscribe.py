"""Event Subscribe payload schemas preserve envelopes at execution admission."""

import copy
import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.eventstreams.adapters.kafka_metadata import KafkaSourceMetadata
from syntara.eventstreams.core.envelope import RawEvent
from syntara.eventstreams.core.serialization import EventDecodeSuccess, JsonEventDecoder, encode_envelope
from syntara.workflows.exceptions import TriggerValidationError
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.services.execution_service import ExecutionService
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType


def _decoded_envelope(value: bytes) -> dict[str, Any]:
    """Supply the same JSON-safe envelope representation used at handoff."""
    record = RawEvent(
        value=value,
        source_metadata=KafkaSourceMetadata(
            integration_id=uuid4(),
            subscription_id=uuid4(),
            source_generation=1,
            received_at=datetime.now(UTC),
            topic="alerts",
            partition=1,
            offset="9007199254740993",
        ),
    )
    decoded = JsonEventDecoder().decode(record)
    assert isinstance(decoded, EventDecodeSuccess)
    envelope: dict[str, Any] = json.loads(encode_envelope(decoded.envelope))
    return envelope


@pytest.fixture
def trigger() -> dict[str, Any]:
    return {
        "id": "incoming",
        "type": NodeType.EVENT_SUBSCRIBE_TRIGGER,
        "parameters": {"input_schema": {"type": "object", "required": ["count"]}},
    }


@pytest.fixture
def service(trigger: dict[str, Any]) -> ExecutionService:
    workflow = Mock(spec=Workflow)
    workflow.name = "Subscribe"
    version = Mock(spec=WorkflowVersion)
    version.version = 1
    version.schema_version = "2.0.0"
    version.workflow_definition = {"triggers": [trigger], "nodes": [], "edges": []}
    result = Mock()
    result.first.return_value = (workflow, version)
    session = Mock(spec=AsyncSession)
    session.exec = AsyncMock(return_value=result)
    user = Mock(spec=User)
    user.id = uuid4()
    return ExecutionService(session, user)


@pytest.mark.parametrize(
    ("value", "schema"),
    [
        (
            b'{"count":2}',
            {
                "type": "object",
                "required": ["count"],
                "properties": {"count": {"type": "integer"}},
                "additionalProperties": False,
            },
        ),
        (b"{}", {"properties": {"count": {"default": 99}}}),
        (b'{"nested":{}}', {"properties": {"nested": {"properties": {"count": {"default": 99}}}}}),
        (b"null", {"type": "null"}),
        (b"true", {"type": "boolean"}),
        (b"2", {"type": "integer"}),
        (b'"text"', {"type": "string"}),
        (b"[2]", {"type": "array", "items": {"type": "integer"}}),
    ],
)
async def test_create_execution_validates_payload_without_mutating_envelope(
    service: ExecutionService,
    trigger: dict[str, Any],
    value: bytes,
    schema: dict[str, Any],
) -> None:
    trigger["parameters"]["input_schema"] = schema
    envelope = _decoded_envelope(value)
    before = copy.deepcopy(envelope)
    with patch.object(service, "_start_temporal_and_create_execution", new_callable=AsyncMock) as start:
        await service.create_execution(uuid4(), envelope, "incoming")
    start.assert_awaited_once()
    assert start.call_args.kwargs["input_data"] is envelope
    assert envelope == before


@pytest.mark.parametrize(
    "schema",
    [
        {"required": ["count"]},
        {"properties": {"count": {"default": 99}}, "required": ["count"]},
        {"type": "invalid"},
        {"$ref": "https://example.com/schema"},
    ],
)
async def test_invalid_event_payload_stops_before_scheduling(
    service: ExecutionService,
    trigger: dict[str, Any],
    schema: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    trigger["parameters"]["input_schema"] = schema
    envelope = _decoded_envelope(b'{"private":"CUSTOMER_PAYLOAD"}')
    envelope["count"] = 2  # An envelope field must not satisfy the payload's required field.
    before = copy.deepcopy(envelope)
    with (
        patch.object(service, "_start_temporal_and_create_execution", new_callable=AsyncMock) as start,
        pytest.raises(TriggerValidationError),
    ):
        await service.create_execution(uuid4(), envelope, "incoming")
    start.assert_not_called()
    assert envelope == before
    assert "CUSTOMER_PAYLOAD" not in caplog.text


def test_missing_payload_is_not_json_null(trigger: dict[str, Any]) -> None:
    trigger["parameters"]["input_schema"] = {"type": "null"}
    envelope = _decoded_envelope(b"null")
    envelope.pop("payload")
    with pytest.raises(TriggerValidationError, match="must contain a payload"):
        ExecutionService._apply_trigger_schema_defaults(trigger, envelope)


@pytest.mark.parametrize(
    "trigger_type",
    [
        NodeType.MANUAL_TRIGGER,
        NodeType.WEBHOOK_TRIGGER,
        NodeType.EDA_TRIGGER,
        NodeType.SCHEDULED_TRIGGER,
    ],
)
def test_existing_triggers_still_fill_defaults(trigger_type: NodeType) -> None:
    trigger = {
        "id": "existing",
        "type": trigger_type,
        "parameters": {"input_schema": {"properties": {"count": {"default": 2}}, "required": ["count"]}},
    }
    inputs: dict[str, Any] = {}
    ExecutionService._apply_trigger_schema_defaults(trigger, inputs)
    assert inputs == {"count": 2}


def test_multiple_of_overflow_payload_translates_to_trigger_validation_error(trigger: dict[str, Any]) -> None:
    """A huge-digit integer with multipleOf must surface as TriggerValidationError, not OverflowError.

    Regression for a plain ``jsonschema.Draft7Validator`` raising OverflowError on a
    400-digit integer validated against ``multipleOf: 0.1`` — the event decoder's
    ``validate_payload`` helper already converts that into a schema_mismatch failure.
    """
    trigger["parameters"]["input_schema"] = {"multipleOf": 0.1}
    envelope = _decoded_envelope(("9" * 400).encode())
    with pytest.raises(TriggerValidationError):
        ExecutionService._apply_trigger_schema_defaults(trigger, envelope)


def test_large_unique_items_payload_uses_hardened_validator(trigger: dict[str, Any]) -> None:
    """Event Subscribe validation must route through validate_payload's O(n log n) uniqueness check.

    A plain ``jsonschema.Draft7Validator`` falls back to a quadratic pairwise comparison
    for ``uniqueItems``, which stalls on large mixed arrays. This exercises the same
    hardened path via ``_apply_trigger_schema_defaults`` to confirm it is wired to
    ``validate_payload`` rather than a bare ``jsonschema.Draft7Validator``.
    """
    trigger["parameters"]["input_schema"] = {"uniqueItems": True}
    payload = [item for number in range(2000) for item in (number, str(number))]

    envelope = _decoded_envelope(json.dumps(payload, separators=(",", ":")).encode())
    ExecutionService._apply_trigger_schema_defaults(trigger, envelope)  # no duplicates: passes

    payload.append(0)  # introduce a duplicate
    dup_envelope = _decoded_envelope(json.dumps(payload, separators=(",", ":")).encode())
    with pytest.raises(TriggerValidationError):
        ExecutionService._apply_trigger_schema_defaults(trigger, dup_envelope)
