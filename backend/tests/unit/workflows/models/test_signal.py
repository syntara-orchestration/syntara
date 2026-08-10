"""Tests for signal models."""

import pytest
from pydantic import ValidationError

from syntara.workflows.models.signal import ActivitySignalPayload, SignalResponse


class TestActivitySignalPayload:
    """Tests for ActivitySignalPayload model."""

    def test_create_with_valid_signal_data(self) -> None:
        """Test creating ActivitySignalPayload with valid signal_data."""
        # Arrange & Act
        payload = ActivitySignalPayload(
            signal_data={
                "status": "completed",
                "result": {"value": 42},
            }
        )

        # Assert
        assert payload.signal_data == {"status": "completed", "result": {"value": 42}}

    def test_create_with_nested_signal_data(self) -> None:
        """Test creating ActivitySignalPayload with nested signal_data."""
        # Arrange & Act
        payload = ActivitySignalPayload(
            signal_data={
                "id": "inv-123",
                "status": "completed",
                "result": {
                    "content": "Analysis complete",
                    "response_metadata": {
                        "model": "claude-3.5-sonnet",
                        "tokens": 150,
                    },
                },
                "timestamp": "2026-01-14T12:00:00Z",
            }
        )

        # Assert
        assert payload.signal_data["id"] == "inv-123"
        assert payload.signal_data["result"]["content"] == "Analysis complete"
        assert payload.signal_data["result"]["response_metadata"]["model"] == "claude-3.5-sonnet"

    def test_create_with_error_signal_data(self) -> None:
        """Test creating ActivitySignalPayload with error signal_data."""
        # Arrange & Act
        payload = ActivitySignalPayload(
            signal_data={
                "status": "failed",
                "error": {
                    "message": "Execution failed",
                    "error_type": "AgentError",
                },
            }
        )

        # Assert
        assert payload.signal_data["status"] == "failed"
        assert payload.signal_data["error"]["message"] == "Execution failed"

    def test_create_with_empty_signal_data(self) -> None:
        """Test creating ActivitySignalPayload with empty signal_data."""
        # Arrange & Act
        payload = ActivitySignalPayload(signal_data={})

        # Assert
        assert payload.signal_data == {}

    def test_missing_signal_data_raises_validation_error(self) -> None:
        """Test that missing signal_data raises ValidationError."""
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            ActivitySignalPayload()  # type: ignore[call-arg]

        assert "signal_data" in str(exc_info.value)

    def test_json_serialization(self) -> None:
        """Test JSON serialization of ActivitySignalPayload."""
        # Arrange
        payload = ActivitySignalPayload(
            signal_data={
                "status": "completed",
                "result": {"value": 42},
            }
        )

        # Act
        json_str = payload.model_dump_json()

        # Assert
        assert '"signal_data"' in json_str
        assert '"status":"completed"' in json_str
        assert '"value":42' in json_str

    def test_from_dict(self) -> None:
        """Test creating ActivitySignalPayload from dict."""
        # Arrange
        data = {
            "signal_data": {
                "status": "completed",
                "result": {"value": 42},
            }
        }

        # Act
        payload = ActivitySignalPayload(**data)

        # Assert
        assert payload.signal_data == data["signal_data"]


class TestSignalResponse:
    """Tests for SignalResponse model."""

    def test_create_with_required_fields(self) -> None:
        """Test creating SignalResponse with only required fields."""
        # Arrange & Act
        response = SignalResponse(status="signal_sent")

        # Assert
        assert response.status == "signal_sent"
        assert response.message is None

    def test_create_with_all_fields(self) -> None:
        """Test creating SignalResponse with all fields."""
        # Arrange & Act
        response = SignalResponse(
            status="signal_sent",
            message="Signal sent to activity test_activity",
        )

        # Assert
        assert response.status == "signal_sent"
        assert response.message == "Signal sent to activity test_activity"

    def test_json_serialization(self) -> None:
        """Test JSON serialization of SignalResponse."""
        # Arrange
        response = SignalResponse(
            status="signal_sent",
            message="Signal sent successfully",
        )

        # Act
        json_str = response.model_dump_json()

        # Assert
        assert '"status":"signal_sent"' in json_str
        assert '"message":"Signal sent successfully"' in json_str

    def test_from_dict(self) -> None:
        """Test creating SignalResponse from dict."""
        # Arrange
        data = {
            "status": "signal_sent",
            "message": "Signal sent to activity test_activity",
        }

        # Act
        response = SignalResponse(**data)

        # Assert
        assert response.status == "signal_sent"
        assert response.message == "Signal sent to activity test_activity"
