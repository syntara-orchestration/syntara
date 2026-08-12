"""Unit tests for WorkflowSignalProcessor."""

from datetime import UTC, datetime
from typing import Any

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine.activities.common import (
    ActivityExecutionError,
)
from syntara.workflows.workflow_engine.signals.processor import WorkflowSignalProcessor


class TestWorkflowSignalProcessorProcessSignal:
    """Tests for WorkflowSignalProcessor.process_signal."""

    def test_process_signal_success_returns_signal_data(self) -> None:
        """Test that successful signal returns the signal data unchanged."""
        # Arrange
        signal_data = {
            "id": "invocation-123",
            "status": "completed",
            "result": {
                "content": "Analysis complete: The system is healthy",
                "response_metadata": {"model": "claude-3-5-sonnet-20241022"},
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }
        activity_id = "analyze_system"
        execution_id = "exec-456"

        # Act
        result = WorkflowSignalProcessor.process_signal(signal_data, activity_id, execution_id)

        # Assert
        assert result == signal_data
        assert result["status"] == "completed"
        assert "result" in result

    def test_process_signal_success_with_nested_data(self) -> None:
        """Test processing success signal with nested result data."""
        # Arrange
        signal_data = {
            "id": "invocation-789",
            "status": "completed",
            "result": {
                "content": {
                    "answer": "42",
                    "explanation": "The answer to life, the universe, and everything",
                },
                "response_metadata": {
                    "source": "streaming",
                    "model": "gpt-4",
                },
            },
        }

        # Act
        result = WorkflowSignalProcessor.process_signal(signal_data, "task_1", "exec_1")

        # Assert
        assert result == signal_data
        assert result["result"]["content"]["answer"] == "42"

    def test_process_signal_failure_raises_application_error_for_non_retryable(self) -> None:
        """Test that failed signal without retryable error code raises ApplicationError."""
        # Arrange - no error code in message, defaults to non-retryable
        signal_data = {
            "id": "invocation-error",
            "status": "failed",
            "error": {
                "message": "API key is invalid",
                "error_type": "AuthenticationError",
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Act & Assert - no error code extracted, should be non-retryable
        with pytest.raises(ApplicationError) as exc_info:
            WorkflowSignalProcessor.process_signal(signal_data, "api_call", "exec-123")

        assert exc_info.value.non_retryable is True
        assert "AuthenticationError" in str(exc_info.value)
        assert "API key is invalid" in str(exc_info.value)

    def test_process_signal_failure_with_minimal_error_info(self) -> None:
        """Test that failed signal with minimal error info uses defaults."""
        # Arrange - no error code, should be non-retryable
        signal_data = {
            "id": "invocation-minimal",
            "status": "failed",
            "error": {},  # Empty error dict
        }

        # Act & Assert - no error code, should be non-retryable
        with pytest.raises(ApplicationError) as exc_info:
            WorkflowSignalProcessor.process_signal(signal_data, "task_minimal", "exec-minimal")

        # Should use default message and type
        assert exc_info.value.non_retryable is True
        assert "UnknownError" in str(exc_info.value)
        assert "Agent execution failed" in str(exc_info.value)

    def test_process_signal_failure_without_error_dict(self) -> None:
        """Test that failed signal without error dict uses defaults."""
        # Arrange - no error code, should be non-retryable
        signal_data = {
            "id": "invocation-no-error",
            "status": "failed",
            # No 'error' key at all
        }

        # Act & Assert - no error code, should be non-retryable
        with pytest.raises(ApplicationError) as exc_info:
            WorkflowSignalProcessor.process_signal(signal_data, "task_no_error", "exec-no-error")

        assert exc_info.value.non_retryable is True
        assert "UnknownError" in str(exc_info.value)
        assert "Agent execution failed" in str(exc_info.value)

    def test_process_signal_failure_preserves_error_type(self) -> None:
        """Test that error type is preserved in the raised exception."""
        # Arrange - errors without codes are non-retryable
        error_types = ["ValueError", "TimeoutError", "LLMConfigurationError", "NetworkError"]

        for error_type in error_types:
            signal_data = {
                "status": "failed",
                "error": {
                    "message": f"Test {error_type} occurred",
                    "error_type": error_type,
                },
            }

            # Act & Assert - no error code, should be non-retryable
            with pytest.raises(ApplicationError) as exc_info:
                WorkflowSignalProcessor.process_signal(signal_data, "test_activity", "test_exec")

            assert exc_info.value.non_retryable is True
            assert error_type in str(exc_info.value)
            assert f"Test {error_type} occurred" in str(exc_info.value)

    def test_process_signal_with_unknown_status(self) -> None:
        """Test processing signal with unknown status (not 'failed')."""
        # Arrange - any status other than "failed" should be treated as success
        signal_data = {
            "id": "invocation-pending",
            "status": "pending",
            "result": {"content": "Processing..."},
        }

        # Act
        result = WorkflowSignalProcessor.process_signal(signal_data, "activity_1", "exec_1")

        # Assert - should return signal data unchanged (not raise)
        assert result == signal_data

    def test_process_signal_with_none_status(self) -> None:
        """Test processing signal with None status."""
        # Arrange
        signal_data = {
            "id": "invocation-no-status",
            "status": None,
            "result": {"content": "Done"},
        }

        # Act
        result = WorkflowSignalProcessor.process_signal(signal_data, "activity_1", "exec_1")

        # Assert - should return signal data (not raise)
        assert result == signal_data

    def test_process_signal_preserves_original_structure(self) -> None:
        """Test that process_signal preserves the original signal structure."""
        # Arrange
        signal_data = {
            "id": "inv-123",
            "status": "completed",
            "result": {
                "content": "Test result",
                "response_metadata": {
                    "model": "test-model",
                    "tokens": 150,
                },
            },
            "timestamp": "2024-01-13T12:00:00Z",
            "agent_type": "GenericAgent",
            "custom_field": "custom_value",
        }

        # Act
        result = WorkflowSignalProcessor.process_signal(signal_data, "test_activity", "test_exec")

        # Assert - all fields preserved
        assert result == signal_data
        assert result["custom_field"] == "custom_value"
        assert result["timestamp"] == "2024-01-13T12:00:00Z"

    def test_process_signal_failure_with_complex_error_message(self) -> None:
        """Test that complex error messages are preserved correctly."""
        # Arrange - no error code, should be non-retryable
        complex_message = """
        Multiple errors occurred:
        1. Connection timeout after 30s
        2. Retry limit exceeded (5 attempts)
        3. Fallback mechanism failed
        """
        signal_data = {
            "status": "failed",
            "error": {
                "message": complex_message,
                "error_type": "CompositeError",
            },
        }

        # Act & Assert - no error code, should be non-retryable
        with pytest.raises(ApplicationError) as exc_info:
            WorkflowSignalProcessor.process_signal(signal_data, "complex_task", "exec_complex")

        error_message = str(exc_info.value)
        assert exc_info.value.non_retryable is True
        assert "CompositeError" in error_message
        assert "Connection timeout" in error_message
        assert "Retry limit exceeded" in error_message

    def test_process_signal_with_empty_signal_data(self) -> None:
        """Test processing completely empty signal data."""
        # Arrange
        signal_data: dict[str, Any] = {}

        # Act
        result = WorkflowSignalProcessor.process_signal(signal_data, "empty_activity", "empty_exec")

        # Assert - should return empty dict (status is None/missing, treated as success)
        assert result == {}


class TestWorkflowSignalProcessorRetryableErrors:
    """Tests for retryable error codes (whitelist approach)."""

    def test_retryable_error_code_raises_activity_execution_error(self) -> None:
        """Test that error codes in the retryable list raise ActivityExecutionError."""
        # Arrange - 503 is in default retryable codes
        signal_data = {
            "status": "failed",
            "error": {
                "message": "Error code: 503 - Service Unavailable",
                "error_type": "ServerError",
            },
        }

        # Act & Assert - should raise ActivityExecutionError (retryable)
        with pytest.raises(ActivityExecutionError) as exc_info:
            WorkflowSignalProcessor.process_signal(signal_data, "api_call", "exec-123")

        assert "ServerError" in str(exc_info.value)
        assert "Service Unavailable" in str(exc_info.value)

    def test_non_retryable_error_code_raises_application_error(self) -> None:
        """Test that error codes NOT in the retryable list raise ApplicationError."""
        # Arrange - 400 is NOT in default retryable codes
        signal_data = {
            "status": "failed",
            "error": {
                "message": "Error code: 400 - Bad Request",
                "error_type": "ValidationError",
            },
        }

        # Act & Assert - should raise ApplicationError (non-retryable)
        with pytest.raises(ApplicationError) as exc_info:
            WorkflowSignalProcessor.process_signal(signal_data, "api_call", "exec-123")

        assert exc_info.value.non_retryable is True
        assert "ValidationError" in str(exc_info.value)

    def test_custom_retryable_codes_from_config(self) -> None:
        """Test that custom retryable codes can be specified in retry policy config."""
        # Arrange - custom config with only exit code 2 as retryable
        retry_config = {"retryableErrors": [2, 3]}
        signal_data = {
            "status": "failed",
            "error": {
                "message": "Exit code: 2",
                "error_type": "ProcessError",
            },
        }

        # Act & Assert - exit code 2 should be retryable
        with pytest.raises(ActivityExecutionError) as exc_info:
            WorkflowSignalProcessor.process_signal(signal_data, "script_task", "exec-123", retry_config)

        assert "ProcessError" in str(exc_info.value)

    def test_custom_retryable_codes_non_retryable(self) -> None:
        """Test that codes not in custom retryable list are non-retryable."""
        # Arrange - custom config with only exit code 2 as retryable
        retry_config = {"retryableErrors": [2, 3]}
        signal_data = {
            "status": "failed",
            "error": {
                "message": "Exit code: 127 - Command not found",
                "error_type": "ProcessError",
            },
        }

        # Act & Assert - exit code 127 not in custom list, should be non-retryable
        with pytest.raises(ApplicationError) as exc_info:
            WorkflowSignalProcessor.process_signal(signal_data, "script_task", "exec-123", retry_config)

        assert exc_info.value.non_retryable is True
        assert "ProcessError" in str(exc_info.value)

    def test_error_without_code_is_non_retryable(self) -> None:
        """Test that errors without extractable code are non-retryable (fail fast)."""
        # Arrange - error message with no code
        signal_data = {
            "status": "failed",
            "error": {
                "message": "Connection refused",
                "error_type": "NetworkError",
            },
        }

        # Act & Assert - no code extracted, should be non-retryable
        with pytest.raises(ApplicationError) as exc_info:
            WorkflowSignalProcessor.process_signal(signal_data, "api_call", "exec-123")

        assert exc_info.value.non_retryable is True
        assert "NetworkError" in str(exc_info.value)

    def test_rate_limit_error_is_retryable(self) -> None:
        """Test that 429 rate limit errors are retryable by default."""
        # Arrange - 429 is in default retryable codes
        signal_data = {
            "status": "failed",
            "error": {
                "message": "Error code: 429 - Too Many Requests",
                "error_type": "RateLimitError",
            },
        }

        # Act & Assert - should be retryable
        with pytest.raises(ActivityExecutionError) as exc_info:
            WorkflowSignalProcessor.process_signal(signal_data, "api_call", "exec-123")

        assert "RateLimitError" in str(exc_info.value)

    def test_unauthorized_error_is_non_retryable(self) -> None:
        """Test that 401 unauthorized errors are non-retryable."""
        # Arrange - 401 is NOT in default retryable codes
        signal_data = {
            "status": "failed",
            "error": {
                "message": "Error code: 401 - Unauthorized",
                "error_type": "AuthError",
            },
        }

        # Act & Assert - should be non-retryable
        with pytest.raises(ApplicationError) as exc_info:
            WorkflowSignalProcessor.process_signal(signal_data, "api_call", "exec-123")

        assert exc_info.value.non_retryable is True
        assert "AuthError" in str(exc_info.value)
