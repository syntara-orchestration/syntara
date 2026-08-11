"""Integration tests for GenericAgent retry behavior.

These tests validate the end-to-end retry functionality when GenericAgent
makes LLM calls through the retry decorator.
"""

# ruff: noqa: ANN401, TRY003, EM101

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import openai
import pytest
from langchain_core.messages import HumanMessage

from syntara.agent_orchestrator.agents.generic_agent import GenericAgent
from syntara.agent_orchestrator.models.agent_state import AgentState
from syntara.audit.emitter import AuditActorContext


@pytest.fixture
def sample_agent_state() -> AgentState:
    """Create a sample agent state for testing."""
    return {
        "prompt": "What is the weather today?",
        "original_prompt": "What is the weather today?",
        "session_id": "test-session",
        "invocation_id": uuid4(),
        "actor_context": AuditActorContext(),
        "context_package": None,
        "current_agent": "generic_agent",
        "metadata": None,
        "messages": [HumanMessage("What is the weather today?")],
        "result": None,
        "llm_token_usage_log": [],
    }


class TestSuccessfulRetryAfterTransientError:
    """Test scenario: successful retry after transient 503 error."""

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("fast_retry_settings")
    async def test_retry_succeeds_after_503_error(
        self,
        sample_agent_state: AgentState,
    ) -> None:
        """Test that GenericAgent retries and succeeds after 503 error."""
        # Create mock LLM
        mock_llm = Mock()
        mock_llm_with_tools = AsyncMock()
        mock_llm.model_name = "test-model"

        call_count = 0

        async def mock_ainvoke(messages: Any) -> Any:
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # First call fails with 503
                response = MagicMock()
                response.status_code = 503
                raise openai.APIStatusError(
                    message="Service unavailable",
                    response=response,
                    body=None,
                )

            # Second call succeeds
            mock_response = MagicMock()
            mock_response.text = "I am Malenia, blade of Miquella."
            mock_response.content = "I am Malenia, blade of Miquella."
            mock_response.response_metadata = {"model": "test-model", "tokens": 10}
            return mock_response

        mock_llm_with_tools.ainvoke = mock_ainvoke
        mock_llm.bind_tools.return_value = mock_llm_with_tools

        # Create agent
        agent = GenericAgent(llm=mock_llm, available_tools=[])

        # Execute
        await agent._execute(sample_agent_state)

        # Verify success
        result_data = sample_agent_state["result"]
        assert result_data is not None
        assert result_data["content"] == "I am Malenia, blade of Miquella."
        assert call_count == 2  # Initial + 1 retry
        assert "model" in result_data["response_metadata"]

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("fast_retry_settings")
    async def test_retry_succeeds_after_connection_error(
        self,
        sample_agent_state: AgentState,
    ) -> None:
        """Test that GenericAgent retries and succeeds after APIConnectionError."""
        mock_llm = Mock()
        mock_llm_with_tools = AsyncMock()
        mock_llm.model_name = "test-model"

        call_count = 0

        async def mock_ainvoke(messages: Any) -> Any:
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                raise openai.APIConnectionError(request=MagicMock())

            mock_response = MagicMock()
            mock_response.text = "Success after connection error."
            mock_response.content = "Success after connection error."
            mock_response.response_metadata = {"model": "test-model"}
            return mock_response

        mock_llm_with_tools.ainvoke = mock_ainvoke
        mock_llm.bind_tools.return_value = mock_llm_with_tools

        agent = GenericAgent(llm=mock_llm, available_tools=[])

        await agent._execute(sample_agent_state)

        result_data = sample_agent_state["result"]
        assert result_data is not None
        assert result_data["content"] == "Success after connection error."
        assert call_count == 2


class TestExhaustedRetriesAfterMultipleFailures:
    """Test scenario: exhausted retries after persistent errors."""

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("fast_retry_settings")
    async def test_fails_after_max_retries_with_500_errors(
        self,
        sample_agent_state: AgentState,
    ) -> None:
        """Test that GenericAgent fails after exhausting retries with 500 errors."""
        mock_llm = Mock()
        mock_llm_with_tools = AsyncMock()
        mock_llm.model_name = "test-model"

        call_count = 0

        async def mock_ainvoke(messages: Any) -> Any:
            nonlocal call_count
            call_count += 1

            # Always fail with 500
            response = MagicMock()
            response.status_code = 500
            raise openai.APIStatusError(
                message="Internal server error",
                response=response,
                body=None,
            )

        mock_llm_with_tools.ainvoke = mock_ainvoke
        mock_llm.bind_tools.return_value = mock_llm_with_tools

        agent = GenericAgent(llm=mock_llm, available_tools=[])

        with pytest.raises(openai.APIStatusError) as exc_info:
            await agent._execute(sample_agent_state)

        # Verify retries exhausted and the final 500 error propagates.
        # Backoff scheduling (0.1s, 0.2s, 0.4s with jitter) is covered
        # deterministically by test_retry_decorator.test_exponential_backoff_delays;
        # asserting wall-clock time here is flaky under CI load.
        assert call_count == 4  # Initial + 3 retries
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("fast_retry_settings")
    async def test_fails_after_max_retries_with_different_errors(
        self,
        sample_agent_state: AgentState,
    ) -> None:
        """Test that retry continues with different error types."""
        mock_llm = Mock()
        mock_llm_with_tools = AsyncMock()
        mock_llm.model_name = "test-model"

        call_count = 0
        errors = [503, 500, 502, 504]

        async def mock_ainvoke(messages: Any) -> Any:
            nonlocal call_count
            response = MagicMock()
            response.status_code = errors[call_count]
            call_count += 1
            raise openai.APIStatusError(
                message=f"Error {errors[call_count - 1]}",
                response=response,
                body=None,
            )

        mock_llm_with_tools.ainvoke = mock_ainvoke
        mock_llm.bind_tools.return_value = mock_llm_with_tools

        agent = GenericAgent(llm=mock_llm, available_tools=[])

        with pytest.raises(openai.APIStatusError):
            await agent._execute(sample_agent_state)

        # All errors should have been tried
        assert call_count == 4


class TestNonRetryableErrorFailsImmediately:
    """Test scenario: non-retryable errors fail without retry."""

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("fast_retry_settings")
    async def test_authentication_error_fails_immediately(
        self,
        sample_agent_state: AgentState,
    ) -> None:
        """Test that authentication errors fail without retry."""
        mock_llm = Mock()
        mock_llm_with_tools = AsyncMock()
        mock_llm.model_name = "test-model"

        call_count = 0

        async def mock_ainvoke(messages: Any) -> Any:
            nonlocal call_count
            call_count += 1

            raise openai.AuthenticationError(
                message="Invalid API key",
                response=MagicMock(),
                body=None,
            )

        mock_llm_with_tools.ainvoke = mock_ainvoke
        mock_llm.bind_tools.return_value = mock_llm_with_tools

        agent = GenericAgent(llm=mock_llm, available_tools=[])

        with pytest.raises(openai.AuthenticationError) as exc_info:
            await agent._execute(sample_agent_state)

        # No retries
        assert call_count == 1
        assert "Invalid API key" in str(exc_info.value)

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("fast_retry_settings")
    async def test_bad_request_error_fails_immediately(
        self,
        sample_agent_state: AgentState,
    ) -> None:
        """Test that bad request errors fail without retry."""
        mock_llm = Mock()
        mock_llm_with_tools = AsyncMock()
        mock_llm.model_name = "test-model"

        call_count = 0

        async def mock_ainvoke(messages: Any) -> Any:
            nonlocal call_count
            call_count += 1

            raise openai.BadRequestError(
                message="Invalid request format",
                response=MagicMock(),
                body=None,
            )

        mock_llm_with_tools.ainvoke = mock_ainvoke
        mock_llm.bind_tools.return_value = mock_llm_with_tools

        agent = GenericAgent(llm=mock_llm, available_tools=[])

        with pytest.raises(openai.BadRequestError):
            await agent._execute(sample_agent_state)

        assert call_count == 1


class TestZeroRetriesConfiguration:
    """Test scenario: retry disabled with max_retries=0."""

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("disabled_retry_settings")
    async def test_zero_retries_fails_immediately_on_503(
        self,
        sample_agent_state: AgentState,
    ) -> None:
        """Test that retry is disabled when max_retries=0."""
        mock_llm = Mock()
        mock_llm_with_tools = AsyncMock()
        mock_llm.model_name = "test-model"

        call_count = 0

        async def mock_ainvoke(messages: Any) -> Any:
            nonlocal call_count
            call_count += 1

            response = MagicMock()
            response.status_code = 503
            raise openai.APIStatusError(
                message="Service unavailable",
                response=response,
                body=None,
            )

        mock_llm_with_tools.ainvoke = mock_ainvoke
        mock_llm.bind_tools.return_value = mock_llm_with_tools

        agent = GenericAgent(llm=mock_llm, available_tools=[])

        with pytest.raises(openai.APIStatusError):
            await agent._execute(sample_agent_state)

        # No retries despite retryable error
        assert call_count == 1


class TestConcurrentRequestsWithIndependentState:
    """Test scenario: concurrent requests maintain isolated retry state."""

    def _create_mock_llm_for_request(self, request_id: str, call_counts: dict[str, int]) -> Mock:
        """Create a mock LLM with specific behavior for each request."""
        mock_llm = Mock()
        mock_llm_with_tools = AsyncMock()
        mock_llm.model_name = "test-model"

        async def mock_ainvoke(messages: Any) -> Any:
            call_counts[request_id] += 1

            if request_id == "a":
                return self._create_success_response("Success A")

            if request_id == "b" and call_counts[request_id] == 1:
                self._raise_service_unavailable_error()
            if request_id == "b":
                return self._create_success_response("Success B")

            if request_id == "c":
                self._raise_internal_server_error()

            raise RuntimeError("Unexpected request ID")

        mock_llm_with_tools.ainvoke = mock_ainvoke
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        return mock_llm

    def _create_success_response(self, content: str) -> MagicMock:
        """Create a successful response mock."""
        mock_response = MagicMock()
        mock_response.text = content
        mock_response.content = content
        mock_response.response_metadata = {"model": "test"}
        return mock_response

    def _raise_service_unavailable_error(self) -> None:
        """Raise a service unavailable error."""
        response = MagicMock()
        response.status_code = 503
        raise openai.APIStatusError(
            message="Service unavailable",
            response=response,
            body=None,
        )

    def _raise_internal_server_error(self) -> None:
        """Raise an internal server error."""
        response = MagicMock()
        response.status_code = 500
        raise openai.APIStatusError(
            message="Internal server error",
            response=response,
            body=None,
        )

    def _create_test_state(self, request_id: str, query: str) -> AgentState:
        """Create a test state for a request."""
        return {
            "prompt": query,
            "original_prompt": query,
            "session_id": f"session-{request_id}",
            "invocation_id": uuid4(),
            "actor_context": AuditActorContext(),
            "context_package": None,
            "current_agent": "generic_agent",
            "metadata": None,
            "messages": [HumanMessage(query)],
            "result": None,
            "llm_token_usage_log": [],
        }

    def _validate_concurrent_retry_results(
        self, results: tuple[AgentState | BaseException, ...], call_counts: dict[str, int]
    ) -> None:
        """Validate the results of concurrent retry test."""
        # Request A: 1 call (immediate success)
        assert not isinstance(results[0], BaseException)
        result_a = results[0]["result"]
        assert result_a is not None
        assert result_a["content"] == "Success A"
        assert call_counts["a"] == 1

        # Request B: 2 calls (1 failure + 1 success)
        assert not isinstance(results[1], BaseException)
        result_b = results[1]["result"]
        assert result_b is not None
        assert result_b["content"] == "Success B"
        assert call_counts["b"] == 2

        # Request C: 4 calls (initial + 3 retries)
        assert isinstance(results[2], openai.APIStatusError)
        assert call_counts["c"] == 4

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("fast_retry_settings")
    async def test_concurrent_requests_independent_retry_counters(self) -> None:
        """Test that concurrent requests have independent retry state."""
        call_counts = {"a": 0, "b": 0, "c": 0}

        # Create agents with different mock LLMs
        agent_a = GenericAgent(llm=self._create_mock_llm_for_request("a", call_counts), available_tools=[])
        agent_b = GenericAgent(llm=self._create_mock_llm_for_request("b", call_counts), available_tools=[])
        agent_c = GenericAgent(llm=self._create_mock_llm_for_request("c", call_counts), available_tools=[])

        # Create states
        state_a = self._create_test_state("a", "Query A")
        state_b = self._create_test_state("b", "Query B")
        state_c = self._create_test_state("c", "Query C")

        # Run concurrently
        results = await asyncio.gather(
            agent_a._execute(state_a),
            agent_b._execute(state_b),
            agent_c._execute(state_c),
            return_exceptions=True,
        )

        # Validate results
        self._validate_concurrent_retry_results(results, call_counts)
