"""Unit tests for WorkflowVersionCreatedEvent model validation."""

import json

import pytest
from pydantic import ValidationError

from syntara.telemetry.events.workflow_version import WorkflowVersionCreatedEvent
from tests.unit.telemetry.conftest import VALID_WORKFLOW_ID


class TestWorkflowVersionCreatedEventConstruction:
    """Test valid construction of WorkflowVersionCreatedEvent."""

    def test_valid_event(self) -> None:
        event = WorkflowVersionCreatedEvent(
            workflow_id=VALID_WORKFLOW_ID,
            version=3,
            entitlement_id="",
        )
        assert event.workflow_id == VALID_WORKFLOW_ID
        assert event.version == 3

    def test_version_one(self) -> None:
        event = WorkflowVersionCreatedEvent(
            workflow_id=VALID_WORKFLOW_ID,
            version=1,
            entitlement_id="",
        )
        assert event.version == 1


class TestWorkflowVersionCreatedEventFieldConstraints:
    """Test field validation constraints."""

    def test_version_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            WorkflowVersionCreatedEvent(
                workflow_id=VALID_WORKFLOW_ID,
                version=0,
                entitlement_id="",
            )

    def test_negative_version_rejected(self) -> None:
        with pytest.raises(ValidationError):
            WorkflowVersionCreatedEvent(
                workflow_id=VALID_WORKFLOW_ID,
                version=-1,
                entitlement_id="",
            )


class TestWorkflowVersionCreatedEventImmutability:
    """Test that WorkflowVersionCreatedEvent is frozen/immutable."""

    def test_frozen_workflow_id(self) -> None:
        event = WorkflowVersionCreatedEvent(
            workflow_id=VALID_WORKFLOW_ID,
            version=1,
            entitlement_id="",
        )
        with pytest.raises(ValidationError):
            event.workflow_id = "new-id"


class TestWorkflowVersionCreatedEventSegmentConversion:
    """Test to_segment_event output."""

    def test_event_name_is_snake_case(self) -> None:
        event = WorkflowVersionCreatedEvent(
            workflow_id=VALID_WORKFLOW_ID,
            version=1,
            entitlement_id="",
        )
        segment_event = event.to_segment_event()
        assert segment_event["event"] == "workflow_version_created"

    def test_to_segment_event_contains_all_fields(self) -> None:
        event = WorkflowVersionCreatedEvent(
            workflow_id=VALID_WORKFLOW_ID,
            version=5,
            entitlement_id="ent-123",
        )
        segment_event = event.to_segment_event()
        assert segment_event["event"] == "workflow_version_created"
        props = segment_event["properties"]
        assert props == {
            "workflow_id": VALID_WORKFLOW_ID,
            "version": 5,
            "entitlement_id": "ent-123",
            "request_id": None,
        }

    def test_segment_event_is_json_serializable(self) -> None:
        event = WorkflowVersionCreatedEvent(
            workflow_id=VALID_WORKFLOW_ID,
            version=1,
            entitlement_id="",
        )
        assert json.dumps(event.to_segment_event())
