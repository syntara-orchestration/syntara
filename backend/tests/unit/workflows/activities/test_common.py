"""Unit tests for common activity utilities."""

import pytest

from syntara.workflows.workflow_engine.activities.common import (
    DEFAULT_RETRYABLE_ERROR_CODES,
    ActivityExecutionError,
    extract_error_code,
    is_retryable_http_status,
)


class TestActivityExecutionError:
    """Test base exception class."""

    def test_exception_inheritance(self) -> None:
        """Test ActivityExecutionError is a subclass of Exception."""
        assert issubclass(ActivityExecutionError, Exception)


class TestDefaultRetryableErrorCodes:
    """Test default retryable error codes constant."""

    def test_default_codes_exist(self) -> None:
        """Test that default retryable codes constant is defined."""
        assert DEFAULT_RETRYABLE_ERROR_CODES is not None
        assert isinstance(DEFAULT_RETRYABLE_ERROR_CODES, frozenset)
        assert len(DEFAULT_RETRYABLE_ERROR_CODES) > 0

    def test_default_codes_include_transient_errors(self) -> None:
        """Test that default codes include common transient server errors."""
        assert 429 in DEFAULT_RETRYABLE_ERROR_CODES  # Too Many Requests
        assert 502 in DEFAULT_RETRYABLE_ERROR_CODES  # Bad Gateway
        assert 503 in DEFAULT_RETRYABLE_ERROR_CODES  # Service Unavailable
        assert 504 in DEFAULT_RETRYABLE_ERROR_CODES  # Gateway Timeout

    def test_default_codes_exclude_generic_server_errors(self) -> None:
        """Test that 500 and 408 are NOT in the default list."""
        assert 500 not in DEFAULT_RETRYABLE_ERROR_CODES  # Too generic
        assert 408 not in DEFAULT_RETRYABLE_ERROR_CODES  # Rare in server-to-server

    def test_default_codes_exclude_client_errors(self) -> None:
        """Test that default codes don't include client errors."""
        assert 400 not in DEFAULT_RETRYABLE_ERROR_CODES  # Bad Request
        assert 401 not in DEFAULT_RETRYABLE_ERROR_CODES  # Unauthorized
        assert 403 not in DEFAULT_RETRYABLE_ERROR_CODES  # Forbidden
        assert 404 not in DEFAULT_RETRYABLE_ERROR_CODES  # Not Found


class TestIsRetryableHttpStatus:
    """Test is_retryable_http_status helper."""

    @pytest.mark.parametrize("code", [429, 502, 503, 504])
    def test_retryable_codes(self, code: int) -> None:
        assert is_retryable_http_status(code) is True

    @pytest.mark.parametrize("code", [400, 401, 403, 404, 408, 500])
    def test_non_retryable_codes(self, code: int) -> None:
        assert is_retryable_http_status(code) is False


class TestExtractErrorCode:
    """Test error code extraction from error messages."""

    def test_http_status_code_401(self) -> None:
        """Test extraction of HTTP 401 status code."""
        error_msg = "Error code: 401 - {'error': {'message': 'User not found.', 'code': 401}}"
        assert extract_error_code(error_msg) == 401

    def test_http_status_code_with_status_prefix(self) -> None:
        """Test extraction with 'status code' prefix."""
        error_msg = "status code: 404 - Not Found"
        assert extract_error_code(error_msg) == 404

    def test_exit_code_pattern(self) -> None:
        """Test extraction of process exit code."""
        error_msg = "Exit code: 127 - Command not found"
        assert extract_error_code(error_msg) == 127

    def test_exited_with_code_pattern(self) -> None:
        """Test 'exited with code' pattern."""
        error_msg = "Process exited with code 1"
        assert extract_error_code(error_msg) == 1

    def test_exited_without_code_keyword(self) -> None:
        """Test 'exited with' pattern without 'code' keyword."""
        error_msg = "Script exited with 126"
        assert extract_error_code(error_msg) == 126

    def test_code_with_colon(self) -> None:
        """Test simple 'code:' pattern."""
        error_msg = "Failed with code: 500"
        assert extract_error_code(error_msg) == 500

    def test_code_with_equals(self) -> None:
        """Test 'code=' pattern."""
        error_msg = "Error code=503"
        assert extract_error_code(error_msg) == 503

    def test_code_in_json_like_format(self) -> None:
        """Test code in JSON-like format with quotes."""
        error_msg = "AgentError: Execution error: Error code': 403"
        assert extract_error_code(error_msg) == 403

    def test_case_insensitive_matching(self) -> None:
        """Test case-insensitive pattern matching."""
        error_msg = "ERROR CODE: 400"
        assert extract_error_code(error_msg) == 400

    def test_no_error_code_returns_none(self) -> None:
        """Test that messages without error codes return None."""
        error_msg = "Connection timeout"
        assert extract_error_code(error_msg) is None

    def test_first_match_is_returned(self) -> None:
        """Test that first matching code is returned when multiple codes present."""
        error_msg = "Error code: 401 with exit code: 1"
        assert extract_error_code(error_msg) == 401  # First match

    def test_real_world_agent_error(self) -> None:
        """Test extraction from real agent error message."""
        error_msg = (
            "AgentError: Execution error: Error code: 401 - {'error': {'message': 'User not found.', 'code': 401}}"
        )
        assert extract_error_code(error_msg) == 401
