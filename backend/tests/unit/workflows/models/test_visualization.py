"""Tests for visualization streaming models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from syntara.workflows.models.visualization import (
    ActivityPatchMessage,
    ExecutionSnapshotMessage,
    JsonPatchOperation,
)


class TestJsonPatchOperation:
    """Tests for JsonPatchOperation model."""

    def test_from_alias_in_serialization(self) -> None:
        """Test that 'from' alias works correctly in both directions."""
        # Arrange & Act
        op = JsonPatchOperation(op="move", path="/activities/1", **{"from": "/activities/0"})
        serialized = op.model_dump(by_alias=True)

        # Assert
        assert op.from_ == "/activities/0"
        assert serialized.get("from") == "/activities/0"

    def test_invalid_operation_type_raises_validation_error(self) -> None:
        """Test that invalid operation type raises ValidationError."""
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            JsonPatchOperation(
                op="invalid",  # type: ignore[arg-type]
                path="/activities/0/status",
            )

        assert "op" in str(exc_info.value).lower()

    def test_missing_required_fields_raises_validation_error(self) -> None:
        """Test that missing required fields raises ValidationError."""
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            JsonPatchOperation(op="replace")  # type: ignore[call-arg]

        assert "path" in str(exc_info.value).lower()


class TestExecutionSnapshotMessage:
    """Tests for ExecutionSnapshotMessage model."""

    def test_type_field_validates_literal_values(self) -> None:
        """Test that type field only accepts 'initial_snapshot' or 'final_snapshot'."""
        # Test valid values
        ExecutionSnapshotMessage(
            type="initial_snapshot",
            execution_id="123e4567-e89b-12d3-a456-426614174000",
            event_id="1642680000000-0",
            execution={},
            timestamp=datetime(2024, 1, 20, 10, 30, 0, tzinfo=UTC),
        )

        ExecutionSnapshotMessage(
            type="final_snapshot",
            execution_id="123e4567-e89b-12d3-a456-426614174000",
            event_id="1642680000000-0",
            execution={},
            timestamp=datetime(2024, 1, 20, 10, 30, 0, tzinfo=UTC),
        )

        # Test invalid value
        with pytest.raises(ValidationError) as exc_info:
            ExecutionSnapshotMessage(
                type="invalid_snapshot",  # type: ignore[arg-type]
                execution_id="123e4567-e89b-12d3-a456-426614174000",
                event_id="1642680000000-0",
                execution={},
                timestamp=datetime(2024, 1, 20, 10, 30, 0, tzinfo=UTC),
            )

        assert "type" in str(exc_info.value).lower()

    def test_execution_field_accepts_arbitrary_dict(self) -> None:
        """Test that execution field can contain arbitrary nested structures."""
        # Arrange
        complex_execution = {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "status": "running",
            "workflow": {
                "id": "workflow-123",
                "version": {"id": "v1", "definition": {"activities": []}},
            },
            "activities": [
                {
                    "activity_id": "step1",
                    "nested": {"deeply": {"nested": {"value": 123}}},
                }
            ],
        }

        # Act
        message = ExecutionSnapshotMessage(
            type="initial_snapshot",
            execution_id="123e4567-e89b-12d3-a456-426614174000",
            event_id="1642680000000-0",
            execution=complex_execution,
            timestamp=datetime(2024, 1, 20, 10, 30, 0, tzinfo=UTC),
        )

        # Assert
        assert message.execution["workflow"]["version"]["id"] == "v1"
        assert message.execution["activities"][0]["nested"]["deeply"]["nested"]["value"] == 123

    def test_deserialization_from_json_string(self) -> None:
        """Test deserializing ExecutionSnapshotMessage from JSON string."""
        # Arrange
        json_str = """
        {
            "type": "initial_snapshot",
            "execution_id": "123e4567-e89b-12d3-a456-426614174000",
            "event_id": "1642680000000-0",
            "execution": {"id": "123", "status": "running"},
            "timestamp": "2024-01-20T10:30:00Z"
        }
        """

        # Act
        message = ExecutionSnapshotMessage.model_validate_json(json_str)

        # Assert
        assert message.type == "initial_snapshot"
        assert message.execution["status"] == "running"


class TestActivityPatchMessage:
    """Tests for ActivityPatchMessage model."""

    def test_type_field_only_accepts_activity_patch(self) -> None:
        """Test that type field only accepts 'activity_patch'."""
        # Test valid value
        ActivityPatchMessage(
            type="activity_patch",
            execution_id="123e4567-e89b-12d3-a456-426614174000",
            event_id="1642680123456-1",
            ops=[],
            timestamp=datetime(2024, 1, 20, 10, 35, 0, tzinfo=UTC),
        )

        # Test invalid value
        with pytest.raises(ValidationError) as exc_info:
            ActivityPatchMessage(
                type="invalid_type",  # type: ignore[arg-type]
                execution_id="123e4567-e89b-12d3-a456-426614174000",
                event_id="1642680123456-1",
                ops=[],
                timestamp=datetime(2024, 1, 20, 10, 35, 0, tzinfo=UTC),
            )

        assert "type" in str(exc_info.value).lower()

    def test_ops_can_be_empty_list(self) -> None:
        """Test that ops field can be an empty list."""
        # Act
        message = ActivityPatchMessage(
            type="activity_patch",
            execution_id="123e4567-e89b-12d3-a456-426614174000",
            event_id="1642680123456-1",
            ops=[],
            timestamp=datetime(2024, 1, 20, 10, 35, 0, tzinfo=UTC),
        )

        # Assert
        assert message.ops == []

    def test_deserialization_from_dict_with_nested_ops(self) -> None:
        """Test deserializing ActivityPatchMessage from dict with nested operations."""
        # Arrange
        data = {
            "type": "activity_patch",
            "execution_id": "123e4567-e89b-12d3-a456-426614174000",
            "event_id": "1642680123456-1",
            "ops": [
                {"op": "replace", "path": "/activities/0/status", "value": "completed"},
                {"op": "add", "path": "/activities/0/completed_at", "value": "2024-01-20T10:35:00Z"},
                {"op": "move", "path": "/activities/1", "from": "/activities/0"},
            ],
            "timestamp": "2024-01-20T10:35:00Z",
        }

        # Act
        message = ActivityPatchMessage.model_validate(data)

        # Assert
        assert len(message.ops) == 3
        assert message.ops[0].op == "replace"
        assert message.ops[1].op == "add"
        assert message.ops[2].op == "move"
        assert message.ops[2].from_ == "/activities/0"

    def test_invalid_operation_in_ops_raises_validation_error(self) -> None:
        """Test that invalid operation in ops list raises ValidationError."""
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            ActivityPatchMessage(
                type="activity_patch",
                execution_id="123e4567-e89b-12d3-a456-426614174000",
                event_id="1642680123456-1",
                ops=[
                    JsonPatchOperation(op="replace", path="/status", value="done"),
                    JsonPatchOperation(op="invalid", path="/status"),  # type: ignore[arg-type]
                ],
                timestamp=datetime(2024, 1, 20, 10, 35, 0, tzinfo=UTC),
            )

        assert "op" in str(exc_info.value).lower()
