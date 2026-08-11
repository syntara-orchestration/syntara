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
        assert "Authentication failed" in str(exc_info.value)
        assert "credentials" in str(exc_info.value)

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

        # Should use generic fallback with default message
        assert exc_info.value.non_retryable is True
        assert "An unexpected error occurred" in str(exc_info.value)
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
        assert "An unexpected error occurred" in str(exc_info.value)

    def test_process_signal_failure_maps_known_error_types(self) -> None:
        """Test that known error types produce user-friendly messages without raw type names."""
        known_types_and_expected = {
            "TimeoutError": "timed out",
            "LLMConfigurationError": "AI model configuration",
            "NetworkError": "network error",
        }

        for error_type, expected_fragment in known_types_and_expected.items():
            signal_data = {
                "status": "failed",
                "error": {
                    "message": f"Test {error_type} occurred",
                    "error_type": error_type,
                },
            }

            with pytest.raises(ApplicationError) as exc_info:
                WorkflowSignalProcessor.process_signal(signal_data, "test_activity", "test_exec")

            error_msg = exc_info.value.message
            assert exc_info.value.non_retryable is True
            assert expected_fragment.lower() in error_msg.lower()
            assert f"{error_type}:" not in error_msg

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
        assert "An unexpected error occurred" in error_message
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

        assert "internal error" in str(exc_info.value).lower()

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
        assert "request was invalid" in str(exc_info.value).lower()

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
        with pytest.raises(ActivityExecutionError):
            WorkflowSignalProcessor.process_signal(signal_data, "script_task", "exec-123", retry_config)

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
        assert "An unexpected error occurred" in str(exc_info.value)

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
        assert "network error" in str(exc_info.value).lower()

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

        assert "rate-limited" in str(exc_info.value).lower()

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
        assert "Authentication failed" in str(exc_info.value)


# ---------------------------------------------------------------------------
# AAP-87136: User-facing errors must not expose raw exception class names
# ---------------------------------------------------------------------------


class TestUserFacingErrorMessages:
    """Regression tests for AAP-87136: no raw exception types in user-facing messages."""

    def test_no_error_type_colon_prefix_for_known_types(self) -> None:
        """Known error types must not appear as 'ErrorType:' prefix in the message."""
        known_types = [
            "AuthenticationError",
            "RateLimitError",
            "NetworkError",
            "TimeoutError",
            "ServerError",
            "ValidationError",
            "LLMConfigurationError",
        ]

        for error_type in known_types:
            signal_data = {
                "status": "failed",
                "error": {
                    "message": "Some error detail",
                    "error_type": error_type,
                },
            }

            with pytest.raises((ApplicationError, ActivityExecutionError)) as exc_info:
                WorkflowSignalProcessor.process_signal(signal_data, "act", "exec")

            error_msg = exc_info.value.message if hasattr(exc_info.value, "message") else str(exc_info.value)
            assert f"{error_type}:" not in error_msg, (
                f"Raw exception prefix '{error_type}:' must not appear in user-facing message"
            )

    def test_unknown_error_type_uses_generic_fallback(self) -> None:
        """Unknown error types use a generic fallback without the raw class name prefix."""
        signal_data = {
            "status": "failed",
            "error": {
                "message": "Something broke",
                "error_type": "SomeInternalException",
            },
        }

        with pytest.raises(ApplicationError) as exc_info:
            WorkflowSignalProcessor.process_signal(signal_data, "act", "exec")

        error_msg = exc_info.value.message
        assert "SomeInternalException:" not in error_msg
        assert "An unexpected error occurred" in error_msg
        assert "Something broke" in error_msg

    def test_auth_error_provides_credential_guidance(self) -> None:
        """Authentication errors must include actionable credential guidance."""
        signal_data = {
            "status": "failed",
            "error": {
                "message": "API key is invalid",
                "error_type": "AuthenticationError",
            },
        }

        with pytest.raises(ApplicationError) as exc_info:
            WorkflowSignalProcessor.process_signal(signal_data, "act", "exec")

        error_msg = str(exc_info.value)
        assert "credentials" in error_msg.lower()

    def test_network_error_provides_connectivity_guidance(self) -> None:
        """Network errors must include actionable connectivity guidance."""
        signal_data = {
            "status": "failed",
            "error": {
                "message": "Connection refused",
                "error_type": "NetworkError",
            },
        }

        with pytest.raises(ApplicationError) as exc_info:
            WorkflowSignalProcessor.process_signal(signal_data, "act", "exec")

        error_msg = str(exc_info.value)
        assert "connection" in error_msg.lower()
        assert "reachable" in error_msg.lower()

    def test_known_error_type_preserves_original_error_details(self) -> None:
        """Known error types should keep contextual details from the original message."""
        detail = "DNS resolution failed for api.example.com"
        signal_data = {
            "status": "failed",
            "error": {
                "message": detail,
                "error_type": "NetworkError",
            },
        }

        with pytest.raises(ApplicationError) as exc_info:
            WorkflowSignalProcessor.process_signal(signal_data, "act", "exec")

        error_msg = str(exc_info.value)
        assert "network error" in error_msg.lower()
        assert detail in error_msg
