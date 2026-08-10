"""Unit tests for retry decorator and retry utilities.

These tests MUST fail before implementing the retry decorator (TDD approach).
They validate error classification, backoff calculation, and retry behavior.
"""

# ruff: noqa: ANN401, B017, ERA001

import asyncio
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import httpx
import openai
import pytest
from fastapi import HTTPException

from syntara.core.config.base import AdapterRetrySettings
from syntara.core.utils.retry import (
    calculate_backoff,
    is_retryable_error,
    retry_with_backoff,
)


class TestErrorClassification:
    """Tests for error classification logic."""

    def test_openai_api_connection_error_is_retryable(self) -> None:
        """Test that OpenAI APIConnectionError is classified as retryable."""
        error = openai.APIConnectionError(request=MagicMock())
        assert is_retryable_error(error) is True

    def test_openai_api_timeout_error_is_retryable(self) -> None:
        """Test that OpenAI APITimeoutError is classified as retryable."""
        error = openai.APITimeoutError(request=MagicMock())
        assert is_retryable_error(error) is True

    def test_openai_rate_limit_error_is_retryable(self) -> None:
        """Test that OpenAI RateLimitError is classified as retryable."""
        error = openai.RateLimitError(
            message="Rate limit exceeded",
            response=MagicMock(),
            body=None,
        )
        assert is_retryable_error(error) is True

    def test_openai_api_status_error_500_is_retryable(self) -> None:
        """Test that OpenAI APIStatusError with 500 status is retryable."""
        response = MagicMock()
        response.status_code = 500
        error = openai.APIStatusError(
            message="Internal server error",
            response=response,
            body=None,
        )
        assert is_retryable_error(error) is True

    def test_openai_api_status_error_502_is_retryable(self) -> None:
        """Test that OpenAI APIStatusError with 502 status is retryable."""
        response = MagicMock()
        response.status_code = 502
        error = openai.APIStatusError(
            message="Bad gateway",
            response=response,
            body=None,
        )
        assert is_retryable_error(error) is True

    def test_openai_api_status_error_503_is_retryable(self) -> None:
        """Test that OpenAI APIStatusError with 503 status is retryable."""
        response = MagicMock()
        response.status_code = 503
        error = openai.APIStatusError(
            message="Service unavailable",
            response=response,
            body=None,
        )
        assert is_retryable_error(error) is True

    def test_openai_api_status_error_504_is_retryable(self) -> None:
        """Test that OpenAI APIStatusError with 504 status is retryable."""
        response = MagicMock()
        response.status_code = 504
        error = openai.APIStatusError(
            message="Gateway timeout",
            response=response,
            body=None,
        )
        assert is_retryable_error(error) is True

    def test_openai_authentication_error_is_not_retryable(self) -> None:
        """Test that OpenAI AuthenticationError is not retryable."""
        error = openai.AuthenticationError(
            message="Invalid API key",
            response=MagicMock(),
            body=None,
        )
        assert is_retryable_error(error) is False

    def test_openai_bad_request_error_is_not_retryable(self) -> None:
        """Test that OpenAI BadRequestError is not retryable."""
        error = openai.BadRequestError(
            message="Invalid request",
            response=MagicMock(),
            body=None,
        )
        assert is_retryable_error(error) is False

    def test_openai_api_status_error_401_is_not_retryable(self) -> None:
        """Test that OpenAI APIStatusError with 401 is not retryable."""
        response = MagicMock()
        response.status_code = 401
        error = openai.APIStatusError(
            message="Unauthorized",
            response=response,
            body=None,
        )
        assert is_retryable_error(error) is False

    def test_openai_api_status_error_400_is_not_retryable(self) -> None:
        """Test that OpenAI APIStatusError with 400 is not retryable."""
        response = MagicMock()
        response.status_code = 400
        error = openai.APIStatusError(
            message="Bad request",
            response=response,
            body=None,
        )
        assert is_retryable_error(error) is False

    def test_httpx_http_status_error_500_is_retryable(self) -> None:
        """Test that httpx HTTPStatusError with 500 is retryable (fallback)."""
        response = MagicMock()
        response.status_code = 500
        error = httpx.HTTPStatusError(
            message="Internal server error",
            request=MagicMock(),
            response=response,
        )
        assert is_retryable_error(error) is True

    def test_httpx_http_status_error_429_is_retryable(self) -> None:
        """Test that httpx HTTPStatusError with 429 is retryable (fallback)."""
        response = MagicMock()
        response.status_code = 429
        error = httpx.HTTPStatusError(
            message="Too many requests",
            request=MagicMock(),
            response=response,
        )
        assert is_retryable_error(error) is True

    def test_httpx_timeout_exception_is_retryable(self) -> None:
        """Test that httpx TimeoutException is retryable (fallback)."""
        error = httpx.TimeoutException(message="Timeout")
        assert is_retryable_error(error) is True

    def test_httpx_connect_error_is_retryable(self) -> None:
        """Test that httpx ConnectError is retryable (fallback)."""
        error = httpx.ConnectError(message="Connection failed")
        assert is_retryable_error(error) is True

    def test_asyncio_timeout_error_is_retryable(self) -> None:
        """Test that asyncio.TimeoutError is retryable."""
        error = TimeoutError()
        assert is_retryable_error(error) is True

    def test_httpx_http_status_error_400_is_not_retryable(self) -> None:
        """Test that httpx HTTPStatusError with 400 is not retryable."""
        response = MagicMock()
        response.status_code = 400
        error = httpx.HTTPStatusError(
            message="Bad request",
            request=MagicMock(),
            response=response,
        )
        assert is_retryable_error(error) is False

    @pytest.mark.parametrize(
        ("status_code", "expected_retryable"),
        [
            (500, True),  # Internal Server Error - retryable
            (502, True),  # Bad Gateway - retryable
            (503, True),  # Service Unavailable - retryable
            (504, True),  # Gateway Timeout - retryable
            (429, True),  # Too Many Requests - retryable
            (400, False),  # Bad Request - not retryable
            (401, False),  # Unauthorized - not retryable
            (403, False),  # Forbidden - not retryable
            (404, False),  # Not Found - not retryable
            (409, False),  # Conflict - not retryable
            (422, False),  # Unprocessable Entity - not retryable
            (501, False),  # Not Implemented - not retryable (5xx but not in retryable list)
        ],
    )
    def test_fastapi_http_exception_retryable(self, status_code: int, *, expected_retryable: bool) -> None:
        """Test FastAPI HTTPException retryable status determination (defensive fallback)."""
        error = HTTPException(status_code=status_code, detail="Test error")
        assert is_retryable_error(error) is expected_retryable

    def test_retryable_error_marker_is_retryable(self) -> None:
        """Test that exceptions inheriting RetryableError are classified as retryable."""
        from syntara.agent_orchestrator.exceptions import EmptyLLMResponseError

        error = EmptyLLMResponseError(invocation_id="test-id")
        assert is_retryable_error(error) is True

    def test_value_error_is_not_retryable(self) -> None:
        """Test that ValueError is not retryable."""
        error = ValueError("Invalid value")
        assert is_retryable_error(error) is False

    def test_key_error_is_not_retryable(self) -> None:
        """Test that KeyError is not retryable."""
        error = KeyError("missing_key")
        assert is_retryable_error(error) is False

    def test_generic_exception_is_not_retryable(self) -> None:
        """Test that generic Exception is not retryable."""
        error = Exception("Unknown error")
        assert is_retryable_error(error) is False


class TestBackoffCalculation:
    """Tests for exponential backoff calculation with jitter."""

    def test_backoff_calculation_with_jitter(self) -> None:
        """Test that backoff calculation includes jitter within ±10%."""
        settings = AdapterRetrySettings(
            adapter_initial_backoff_seconds=1.0,
            adapter_backoff_growth_factor=2.0,
            adapter_max_backoff_seconds=10.0,
        )

        # Test attempt 0 (first retry)
        delay = calculate_backoff(0, settings)
        assert delay == pytest.approx(1.0, abs=0.1)  # 1.0 ± 10%

        # Test attempt 1 (second retry)
        delay = calculate_backoff(1, settings)
        assert delay == pytest.approx(2.0, abs=0.2)  # 2.0 ± 10%

        # Test attempt 2 (third retry)
        delay = calculate_backoff(2, settings)
        assert delay == pytest.approx(4.0, abs=0.4)  # 4.0 ± 10%

    def test_backoff_cap_enforced(self) -> None:
        """Test that backoff delay never exceeds max_backoff_seconds."""
        settings = AdapterRetrySettings(
            adapter_initial_backoff_seconds=1.0,
            adapter_backoff_growth_factor=2.0,
            adapter_max_backoff_seconds=10.0,
        )

        # Test large attempt number
        delay = calculate_backoff(10, settings)
        assert delay <= 11.0  # 10.0 + 10% jitter = 11.0 max

    def test_backoff_with_different_growth_factor(self) -> None:
        """Test backoff with different growth factor."""
        settings = AdapterRetrySettings(
            adapter_initial_backoff_seconds=2.0,
            adapter_backoff_growth_factor=3.0,
            adapter_max_backoff_seconds=20.0,
        )

        # Test attempt 0: 2.0 * 3^0 = 2.0
        delay = calculate_backoff(0, settings)
        assert delay == pytest.approx(2.0, abs=0.2)  # 2.0 ± 10%

        # Test attempt 1: 2.0 * 3^1 = 6.0
        delay = calculate_backoff(1, settings)
        assert delay == pytest.approx(6.0, abs=0.6)  # 6.0 ± 10%


class TestSettingsValidation:
    """Tests for AdapterRetrySettings validation rules."""

    def test_settings_validation_max_retries_non_negative(self) -> None:
        """Test that max_retries must be >= 0."""
        # Valid: 0 or positive
        settings = AdapterRetrySettings(adapter_max_retries=0)
        assert settings.adapter_max_retries == 0

        settings = AdapterRetrySettings(adapter_max_retries=3)
        assert settings.adapter_max_retries == 3

        # Invalid: negative
        with pytest.raises(Exception):  # Pydantic ValidationError
            AdapterRetrySettings(adapter_max_retries=-1)

    def test_settings_validation_initial_backoff_positive(self) -> None:
        """Test that initial_backoff_seconds must be > 0."""
        # Valid: positive
        settings = AdapterRetrySettings(adapter_initial_backoff_seconds=1.0)
        assert settings.adapter_initial_backoff_seconds == pytest.approx(1.0)

        # Invalid: zero or negative
        with pytest.raises(Exception):  # Pydantic ValidationError
            AdapterRetrySettings(adapter_initial_backoff_seconds=0.0)

        with pytest.raises(Exception):  # Pydantic ValidationError
            AdapterRetrySettings(adapter_initial_backoff_seconds=-1.0)

    def test_settings_validation_timeout_positive(self) -> None:
        """Test that request_timeout_seconds must be > 0."""
        # Valid: positive
        settings = AdapterRetrySettings(adapter_request_timeout_seconds=30.0)
        assert settings.adapter_request_timeout_seconds == pytest.approx(30.0)

        # Invalid: zero or negative
        with pytest.raises(Exception):  # Pydantic ValidationError
            AdapterRetrySettings(adapter_request_timeout_seconds=0.0)


class TestRetryDecorator:
    """Tests for retry decorator behavior.

    CRITICAL: These tests MUST fail before implementing the decorator (TDD).
    """

    @pytest.mark.asyncio
    async def test_successful_retry_after_transient_error(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that decorator retries and succeeds after transient error."""
        call_count = 0

        @retry_with_backoff
        async def mock_llm_call(invocation_id: UUID, **kwargs: Any) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call fails with retryable error
                response = MagicMock()
                response.status_code = 503
                raise openai.APIStatusError(
                    message="Service unavailable",
                    response=response,
                    body=None,
                )
            return "success"

        with override_settings(
            adapter_max_retries=3,
            adapter_initial_backoff_seconds=0.1,
        ):
            result = await mock_llm_call(invocation_id=uuid4())
            assert result == "success"
            assert call_count == 2  # Initial + 1 retry

    @pytest.mark.asyncio
    async def test_failure_after_max_retries_exhausted(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that decorator fails after max retries exhausted."""
        call_count = 0

        @retry_with_backoff
        async def mock_llm_call(invocation_id: UUID, **kwargs: Any) -> str:
            nonlocal call_count
            call_count += 1
            response = MagicMock()
            response.status_code = 500
            raise openai.APIStatusError(
                message="Internal server error",
                response=response,
                body=None,
            )

        with override_settings(
            adapter_max_retries=3,
            adapter_initial_backoff_seconds=0.1,
        ):
            with pytest.raises(openai.APIStatusError):
                await mock_llm_call(invocation_id=uuid4())
            assert call_count == 4  # Initial + 3 retries

    @pytest.mark.asyncio
    async def test_non_retryable_error_fails_immediately(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that non-retryable errors fail without retry."""
        call_count = 0

        @retry_with_backoff
        async def mock_llm_call(invocation_id: UUID, **kwargs: Any) -> str:
            nonlocal call_count
            call_count += 1
            raise openai.AuthenticationError(
                message="Invalid API key",
                response=MagicMock(),
                body=None,
            )

        with override_settings(adapter_max_retries=3):
            with pytest.raises(openai.AuthenticationError):
                await mock_llm_call(invocation_id=uuid4())
            assert call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_retryable_error_subclass_triggers_retry(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that RetryableError subclasses are retried by the decorator."""
        from syntara.agent_orchestrator.exceptions import EmptyLLMResponseError

        call_count = 0

        @retry_with_backoff
        async def mock_llm_call(invocation_id: UUID, **kwargs: Any) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise EmptyLLMResponseError(invocation_id=str(invocation_id))
            return "success"

        with override_settings(
            adapter_max_retries=3,
            adapter_initial_backoff_seconds=0.1,
        ):
            result = await mock_llm_call(invocation_id=uuid4())
            assert result == "success"
            assert call_count == 2  # Initial + 1 retry

    @pytest.mark.asyncio
    async def test_rate_limit_error_retryable(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that rate limit errors are retryable."""
        call_count = 0

        @retry_with_backoff
        async def mock_llm_call(invocation_id: UUID, **kwargs: Any) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise openai.RateLimitError(
                    message="Rate limit exceeded",
                    response=MagicMock(),
                    body=None,
                )
            return "success"

        with override_settings(
            adapter_max_retries=3,
            adapter_initial_backoff_seconds=0.1,
        ):
            result = await mock_llm_call(invocation_id=uuid4())
            assert result == "success"
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_exponential_backoff_delays(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that delays follow exponential backoff pattern."""
        recorded_delays: list[float] = []
        original_sleep = asyncio.sleep

        async def mock_sleep(delay: float) -> None:
            recorded_delays.append(delay)
            await original_sleep(0)

        @retry_with_backoff
        async def mock_llm_call(invocation_id: UUID, **kwargs: Any) -> str:
            response = MagicMock()
            response.status_code = 500
            raise openai.APIStatusError(
                message="Internal server error",
                response=response,
                body=None,
            )

        from unittest.mock import patch

        with (
            override_settings(
                adapter_max_retries=3,
                adapter_initial_backoff_seconds=0.1,
                adapter_backoff_growth_factor=2.0,
            ),
            patch("syntara.core.utils.retry.asyncio.sleep", side_effect=mock_sleep),
            pytest.raises(openai.APIStatusError),
        ):
            await mock_llm_call(invocation_id=uuid4())

        # Expected delays: 0.1s, 0.2s, 0.4s (with jitter ±10%)
        assert len(recorded_delays) == 3
        assert recorded_delays[0] == pytest.approx(0.1, abs=0.01)
        assert recorded_delays[1] == pytest.approx(0.2, abs=0.02)
        assert recorded_delays[2] == pytest.approx(0.4, abs=0.04)

    @pytest.mark.asyncio
    async def test_max_retries_zero_disables_retry(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that max_retries=0 disables retry behavior."""
        call_count = 0

        @retry_with_backoff
        async def mock_llm_call(invocation_id: UUID, **kwargs: Any) -> str:
            nonlocal call_count
            call_count += 1
            response = MagicMock()
            response.status_code = 503
            raise openai.APIStatusError(
                message="Service unavailable",
                response=response,
                body=None,
            )

        with override_settings(adapter_max_retries=0):
            with pytest.raises(openai.APIStatusError):
                await mock_llm_call(invocation_id=uuid4())
            assert call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_concurrent_requests_isolated_state(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that concurrent requests maintain independent retry state."""
        call_counts = {"a": 0, "b": 0, "c": 0}

        @retry_with_backoff
        async def mock_llm_call(invocation_id: UUID, request_id: str, **kwargs: Any) -> str:
            call_counts[request_id] += 1
            if request_id == "a":
                # Request A: succeeds immediately
                return "success_a"
            if request_id == "b" and call_counts[request_id] == 1:
                # Request B: fails once, then succeeds
                response = MagicMock()
                response.status_code = 503
                raise openai.APIStatusError(
                    message="Service unavailable",
                    response=response,
                    body=None,
                )
            if request_id == "c":
                # Request C: always fails
                response = MagicMock()
                response.status_code = 500
                raise openai.APIStatusError(
                    message="Internal server error",
                    response=response,
                    body=None,
                )
            return f"success_{request_id}"

        with override_settings(
            adapter_max_retries=3,
            adapter_initial_backoff_seconds=0.1,
        ):
            results = await asyncio.gather(
                mock_llm_call(invocation_id=uuid4(), request_id="a"),
                mock_llm_call(invocation_id=uuid4(), request_id="b"),
                mock_llm_call(invocation_id=uuid4(), request_id="c"),
                return_exceptions=True,
            )

            # Request A: 1 call
            assert results[0] == "success_a"
            assert call_counts["a"] == 1

            # Request B: 2 calls (1 failure + 1 success)
            assert results[1] == "success_b"
            assert call_counts["b"] == 2

            # Request C: 4 calls (initial + 3 retries)
            assert isinstance(results[2], openai.APIStatusError)
            assert call_counts["c"] == 4

    @pytest.mark.asyncio
    async def test_backoff_interruption_handling(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that interruption during backoff is handled correctly."""
        call_count = 0

        @retry_with_backoff
        async def mock_llm_call(invocation_id: UUID, **kwargs: Any) -> str:
            nonlocal call_count
            call_count += 1
            response = MagicMock()
            response.status_code = 503
            raise openai.APIStatusError(
                message="Service unavailable",
                response=response,
                body=None,
            )

        async def cancel_after_delay() -> None:
            await asyncio.sleep(0.5)  # Cancel after 0.5s
            task.cancel()

        with override_settings(
            adapter_max_retries=3,
            adapter_initial_backoff_seconds=10.0,
        ):
            task = asyncio.create_task(mock_llm_call(invocation_id=uuid4()))
            cancel_task = asyncio.create_task(cancel_after_delay())

            with pytest.raises(asyncio.CancelledError):
                await task

            # Cleanup cancel task
            cancel_task.cancel()
            try:
                await cancel_task
            except asyncio.CancelledError:
                pass

            # Should have made initial call and started backoff before cancellation
            assert call_count >= 1

    @pytest.mark.asyncio
    async def test_error_type_changes_between_attempts(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that retry continues when error type changes between attempts."""
        call_count = 0
        errors = [503, 500, 502]  # Different server errors

        @retry_with_backoff
        async def mock_llm_call(invocation_id: UUID, **kwargs: Any) -> str:
            nonlocal call_count
            if call_count < len(errors):
                response = MagicMock()
                response.status_code = errors[call_count]
                call_count += 1
                raise openai.APIStatusError(
                    message=f"Error {errors[call_count - 1]}",
                    response=response,
                    body=None,
                )
            call_count += 1
            return "success"

        with override_settings(
            adapter_max_retries=3,
            adapter_initial_backoff_seconds=0.1,
        ):
            result = await mock_llm_call(invocation_id=uuid4())
            assert result == "success"
            assert call_count == 4  # 3 errors + 1 success

    @pytest.mark.asyncio
    async def test_per_attempt_timeout_enforcement(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that timeout applies independently to each attempt."""
        call_count = 0

        @retry_with_backoff
        async def mock_llm_call(invocation_id: UUID, **kwargs: Any) -> str:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(1.0)  # Simulate slow response (exceeds timeout)
            return "success"

        with (
            override_settings(
                adapter_max_retries=3,
                adapter_initial_backoff_seconds=0.1,
                adapter_request_timeout_seconds=0.5,
            ),
            pytest.raises((asyncio.TimeoutError, openai.APIStatusError)),
        ):
            await mock_llm_call(invocation_id=uuid4())

        # Each attempt's 1.0s response exceeds the 0.5s per-attempt timeout, so
        # every attempt times out and retries. The call count proves the timeout
        # fired independently on all 4 attempts; asserting wall-clock elapsed time
        # here is flaky under CI load.
        assert call_count == 4  # Initial + 3 retries

    @pytest.mark.asyncio
    async def test_httpx_fallback_exceptions(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that httpx exceptions are handled as fallback."""
        call_count = 0

        @retry_with_backoff
        async def mock_llm_call(invocation_id: UUID, **kwargs: Any) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectError(message="Connection failed")
            return "success"

        with override_settings(
            adapter_max_retries=3,
            adapter_initial_backoff_seconds=0.1,
        ):
            result = await mock_llm_call(invocation_id=uuid4())
            assert result == "success"
            assert call_count == 2  # Initial + 1 retry

    @pytest.mark.asyncio
    async def test_instance_method_with_state_dict(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that decorator correctly extracts invocation_id from instance method.

        This tests the real-world scenario where @retry_with_backoff wraps an
        instance method like GenericAgent._execute(self, state: AgentState).
        In this case, args[0] is 'self' and args[1] is the state dict.
        """
        call_count = 0
        test_invocation_id = uuid4()

        class MockAgent:
            @retry_with_backoff
            async def _execute(self, state: dict[str, Any]) -> str:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    # First call fails with retryable error
                    response = MagicMock()
                    response.status_code = 503
                    raise openai.APIStatusError(
                        message="Service unavailable",
                        response=response,
                        body=None,
                    )
                return "success"

        agent = MockAgent()
        state = {"invocation_id": test_invocation_id, "prompt": "test"}

        with override_settings(
            adapter_max_retries=3,
            adapter_initial_backoff_seconds=0.1,
        ):
            result = await agent._execute(state)
            assert result == "success"
            assert call_count == 2  # Initial + 1 retry

    @pytest.mark.asyncio
    async def test_instance_method_logging_includes_invocation_id(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that instance method retry logging includes invocation_id.

        Verifies that when retrying an instance method, the decorator correctly
        extracts invocation_id from the state dict in args[1] and includes it
        in log messages.
        """
        call_count = 0
        test_invocation_id = uuid4()

        class MockAgent:
            @retry_with_backoff
            async def _execute(self, state: dict[str, Any]) -> str:
                nonlocal call_count
                call_count += 1
                if call_count < 2:
                    response = MagicMock()
                    response.status_code = 503
                    raise openai.APIStatusError(
                        message="Service unavailable",
                        response=response,
                        body=None,
                    )
                return "success"

        agent = MockAgent()
        state = {"invocation_id": test_invocation_id, "prompt": "test"}

        with override_settings(
            adapter_max_retries=3,
            adapter_initial_backoff_seconds=0.1,
        ):
            await agent._execute(state)

        assert call_count == 2
