"""Unit tests for GenericAgent with LangGraph integration.

Tests the GenericAgent implementation using LangGraph node execution.
"""

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from syntara.agent_orchestrator.agents import GenericAgent
from syntara.agent_orchestrator.exceptions import (
    AgentConfigurationError,
    AgentOrchestratorError,
    AgentRateLimitError,
    AgentTimeoutError,
)
from syntara.audit.emitter import AuditActorContext

if TYPE_CHECKING:
    from syntara.agent_orchestrator.models.agent_state import AgentState


class TestGenericAgentLLMIntegration:
    """Test GenericAgent with LangChain LLM."""

    @pytest.mark.asyncio
    async def test_generic_agent_queries_llm_and_returns_answer(self) -> None:
        """Test GenericAgent queries LangChain LLM via LangGraph node execution."""
        mock_llm = Mock()
        mock_llm_with_tools = AsyncMock()
        mock_llm_with_tools.ainvoke.return_value = AIMessage(
            content="Available tools include deployment-agent, monitoring-agent, and testing-agent.",
            response_metadata={},
        )
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm.model_name = "anthropic/claude-3.5-sonnet"

        agent = GenericAgent(llm=mock_llm, available_tools=[])
        invocation_id = uuid4()
        state: AgentState = {
            "prompt": "What tools are available for deployment?",
            "original_prompt": "What tools are available for deployment?",
            "session_id": "test-session",
            "invocation_id": invocation_id,
            "actor_context": AuditActorContext(),
            "context_package": None,
            "current_agent": "generic_agent",
            "messages": [HumanMessage("test")],
            "result": None,
            "metadata": None,
            "llm_token_usage_log": [],
        }

        response = await agent.execute_as_node(state)

        assert isinstance(response, dict)
        assert "result" in response
        result = response["result"]
        assert result is not None
        assert result["type"] == "answer"
        assert "deployment-agent" in result["content"]
        assert "monitoring-agent" in result["content"]
        mock_llm_with_tools.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_generic_agent_result_type_is_answer_not_workflow(self) -> None:
        """Test GenericAgent returns type='answer' (not 'workflow')."""
        mock_llm = Mock()
        mock_llm_with_tools = AsyncMock()
        mock_llm_with_tools.ainvoke.return_value = AIMessage(content="Test answer", response_metadata={})
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm.model_name = "anthropic/claude-3.5-sonnet"

        agent = GenericAgent(llm=mock_llm, available_tools=[])
        invocation_id = uuid4()
        state: AgentState = {
            "prompt": "test query",
            "original_prompt": "test query",
            "session_id": "test-session",
            "invocation_id": invocation_id,
            "actor_context": AuditActorContext(),
            "context_package": None,
            "current_agent": "generic_agent",
            "messages": [HumanMessage("test")],
            "result": None,
            "metadata": None,
            "llm_token_usage_log": [],
        }

        response = await agent.execute_as_node(state)

        result = response["result"]
        assert result is not None
        assert result["type"] == "answer"

    @pytest.mark.asyncio
    async def test_generic_agent_raises_configuration_error_for_invalid_api_key(
        self,
    ) -> None:
        """Test GenericAgent raises AgentConfigurationError for invalid API key."""
        mock_llm = Mock()
        mock_llm_with_tools = AsyncMock()
        mock_llm_with_tools.ainvoke.side_effect = RuntimeError("Invalid API key")
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm.model_name = "anthropic/claude-3.5-sonnet"

        agent = GenericAgent(llm=mock_llm, available_tools=[])
        invocation_id = uuid4()
        state: AgentState = {
            "prompt": "test query",
            "original_prompt": "test query",
            "session_id": "test-session",
            "invocation_id": invocation_id,
            "actor_context": AuditActorContext(),
            "context_package": None,
            "current_agent": "generic_agent",
            "messages": [HumanMessage("test")],
            "result": None,
            "metadata": None,
            "llm_token_usage_log": [],
        }

        with pytest.raises(AgentConfigurationError) as exc_info:
            await agent.execute_as_node(state)

        assert exc_info.value.invocation_id == str(invocation_id)
        assert "Invalid API key" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_generic_agent_raises_rate_limit_error(self) -> None:
        """Test GenericAgent raises AgentRateLimitError for rate limit errors."""
        mock_llm = Mock()
        mock_llm_with_tools = AsyncMock()
        mock_llm_with_tools.ainvoke.side_effect = RuntimeError("Rate limit exceeded")
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm.model_name = "anthropic/claude-3.5-sonnet"

        agent = GenericAgent(llm=mock_llm, available_tools=[])
        invocation_id = uuid4()
        state: AgentState = {
            "prompt": "test query",
            "original_prompt": "test query",
            "session_id": "test-session",
            "invocation_id": invocation_id,
            "actor_context": AuditActorContext(),
            "context_package": None,
            "current_agent": "generic_agent",
            "messages": [HumanMessage("test")],
            "result": None,
            "metadata": None,
            "llm_token_usage_log": [],
        }

        with pytest.raises(AgentRateLimitError) as exc_info:
            await agent.execute_as_node(state)

        assert exc_info.value.invocation_id == str(invocation_id)
        assert "Rate limit exceeded" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_generic_agent_raises_timeout_error(self) -> None:
        """Test GenericAgent raises AgentTimeoutError for timeout scenarios."""
        mock_llm = Mock()
        mock_llm_with_tools = AsyncMock()
        mock_llm_with_tools.ainvoke.side_effect = TimeoutError("Request timed out")
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm.model_name = "anthropic/claude-3.5-sonnet"

        agent = GenericAgent(llm=mock_llm, available_tools=[])
        invocation_id = uuid4()
        state: AgentState = {
            "prompt": "test query",
            "original_prompt": "test query",
            "session_id": "test-session",
            "invocation_id": invocation_id,
            "actor_context": AuditActorContext(),
            "context_package": None,
            "current_agent": "generic_agent",
            "messages": [HumanMessage("test")],
            "result": None,
            "metadata": None,
            "llm_token_usage_log": [],
        }

        with pytest.raises(AgentTimeoutError) as exc_info:
            await agent.execute_as_node(state)

        assert exc_info.value.invocation_id == str(invocation_id)


class TestGenericAgentContextInjection:
    """Test that GenericAgent sends the context-enhanced prompt to the LLM."""

    @pytest.mark.asyncio
    async def test_execute_sends_context_enhanced_prompt_to_llm(self) -> None:
        """Verify standard execution uses state['prompt'] (with context), not state['messages']."""
        mock_llm = Mock()
        mock_llm_with_tools = AsyncMock()
        mock_llm_with_tools.ainvoke.return_value = AIMessage(content="Hello Jane!", response_metadata={})
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm.model_name = "anthropic/claude-3.5-sonnet"

        agent = GenericAgent(llm=mock_llm, available_tools=[])
        original_prompt = "Say hello! Use my name from context."
        enhanced_prompt = (
            "Say hello! Use my name from context.\n\n--- CONTEXT ---\n## documents\nName: Jane Doe\n--- END CONTEXT ---"
        )
        state: AgentState = {
            "prompt": enhanced_prompt,
            "original_prompt": original_prompt,
            "session_id": "test-session",
            "invocation_id": uuid4(),
            "actor_context": AuditActorContext(),
            "context_package": {"grounding_score": 0.95, "context_applied": True},
            "current_agent": "generic_agent",
            "messages": [HumanMessage(original_prompt)],
            "result": None,
            "metadata": None,
            "llm_token_usage_log": [],
        }

        await agent.execute_as_node(state)

        mock_llm_with_tools.ainvoke.assert_called_once()
        messages_sent = mock_llm_with_tools.ainvoke.call_args[0][0]
        human_messages = [m for m in messages_sent if isinstance(m, HumanMessage)]
        assert len(human_messages) == 1
        assert "--- CONTEXT ---" in human_messages[0].content
        assert "Jane Doe" in human_messages[0].content

    @pytest.mark.asyncio
    async def test_execute_structured_sends_context_enhanced_prompt_to_llm(self) -> None:
        """Verify structured output execution uses state['prompt'] (with context)."""
        mock_llm = Mock()
        parsed_output = {"greeting": "Hello Jane!"}
        mock_structured_llm = AsyncMock()
        mock_structured_llm.ainvoke.return_value = parsed_output
        mock_llm.with_structured_output.return_value = mock_structured_llm
        mock_llm.model_name = "anthropic/claude-3.5-sonnet"

        agent = GenericAgent(llm=mock_llm, available_tools=[])
        original_prompt = "Say hello! Use my name from context."
        enhanced_prompt = (
            "Say hello! Use my name from context.\n\n--- CONTEXT ---\n## documents\nName: Jane Doe\n--- END CONTEXT ---"
        )
        state: AgentState = {
            "prompt": enhanced_prompt,
            "original_prompt": original_prompt,
            "session_id": "test-session",
            "invocation_id": uuid4(),
            "actor_context": AuditActorContext(),
            "context_package": {"grounding_score": 0.95, "context_applied": True},
            "current_agent": "generic_agent",
            "messages": [HumanMessage(original_prompt)],
            "result": None,
            "metadata": None,
            "llm_token_usage_log": [],
            "response_schema": {
                "type": "object",
                "properties": {"greeting": {"type": "string"}},
            },
        }

        with patch("syntara.agent_orchestrator.agents.generic_agent.record_llm_call") as mock_record:

            async def _passthrough(_recorder: object, fn: object, *, model: object = None) -> object:
                return await fn()  # type: ignore[operator]

            mock_record.side_effect = _passthrough
            await agent.execute_as_node(state)

        mock_structured_llm.ainvoke.assert_called_once()
        messages_sent = mock_structured_llm.ainvoke.call_args[0][0]
        human_messages = [m for m in messages_sent if isinstance(m, HumanMessage)]
        assert len(human_messages) == 1
        assert "--- CONTEXT ---" in human_messages[0].content
        assert "Jane Doe" in human_messages[0].content


class TestGenericAgentToolLoopReEntry:
    """Test that tool-call history is preserved on re-entry after tool execution."""

    @pytest.mark.asyncio
    async def test_tool_call_history_preserved_on_reentry(self) -> None:
        """On TOOLS → GENERIC_AGENT re-entry, AIMessage + ToolMessage must be forwarded to the LLM."""
        mock_llm = Mock()
        mock_llm_with_tools = AsyncMock()
        mock_llm_with_tools.ainvoke.return_value = AIMessage(content="The sum is 42.", response_metadata={})
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm.model_name = "anthropic/claude-3.5-sonnet"

        mock_tool = Mock(spec=["name", "description"])
        mock_tool.name = "calculate_sum"
        mock_tool.description = "Calculate the sum of two numbers"
        agent = GenericAgent(llm=mock_llm, available_tools=[mock_tool])

        tool_call_ai_msg = AIMessage(
            content="",
            tool_calls=[{"id": "call_1", "name": "calculate_sum", "args": {"a": 20, "b": 22}}],
        )
        tool_result_msg = ToolMessage(content="42", tool_call_id="call_1")

        state: AgentState = {
            "prompt": "What is 20 + 22?",
            "original_prompt": "What is 20 + 22?",
            "session_id": "test-session",
            "invocation_id": uuid4(),
            "actor_context": AuditActorContext(),
            "context_package": None,
            "current_agent": "generic_agent",
            "messages": [HumanMessage("What is 20 + 22?"), tool_call_ai_msg, tool_result_msg],
            "result": None,
            "metadata": None,
            "llm_token_usage_log": [],
        }

        await agent.execute_as_node(state)

        mock_llm_with_tools.ainvoke.assert_called_once()
        messages_sent = mock_llm_with_tools.ainvoke.call_args[0][0]
        ai_messages = [m for m in messages_sent if isinstance(m, AIMessage)]
        tool_messages = [m for m in messages_sent if isinstance(m, ToolMessage)]
        assert len(ai_messages) == 1, "AIMessage with tool_calls must be forwarded"
        assert ai_messages[0].tool_calls[0]["name"] == "calculate_sum"
        assert len(tool_messages) == 1, "ToolMessage with results must be forwarded"
        assert tool_messages[0].content == "42"

    @pytest.mark.asyncio
    async def test_first_call_has_no_extra_messages(self) -> None:
        """On the first call (no tool history), only SystemMessage + HumanMessage are sent."""
        mock_llm = Mock()
        mock_llm_with_tools = AsyncMock()
        mock_llm_with_tools.ainvoke.return_value = AIMessage(content="Hello!", response_metadata={})
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm.model_name = "anthropic/claude-3.5-sonnet"

        agent = GenericAgent(llm=mock_llm, available_tools=[])
        state: AgentState = {
            "prompt": "Hello",
            "original_prompt": "Hello",
            "session_id": "test-session",
            "invocation_id": uuid4(),
            "actor_context": AuditActorContext(),
            "context_package": None,
            "current_agent": "generic_agent",
            "messages": [HumanMessage("Hello")],
            "result": None,
            "metadata": None,
            "llm_token_usage_log": [],
        }

        await agent.execute_as_node(state)

        messages_sent = mock_llm_with_tools.ainvoke.call_args[0][0]
        assert len(messages_sent) == 2
        assert messages_sent[0].__class__.__name__ == "SystemMessage"
        assert isinstance(messages_sent[1], HumanMessage)


class TestGenericAgentPromptEngineering:
    """Test GenericAgent prompt template and engineering."""

    @pytest.mark.asyncio
    async def test_generic_agent_uses_information_assistant_prompt(self) -> None:
        """Test GenericAgent uses appropriate prompt template for information queries."""
        mock_llm = Mock()
        mock_llm_with_tools = AsyncMock()
        mock_llm_with_tools.ainvoke.return_value = AIMessage(content="Test response", response_metadata={})
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm.model_name = "anthropic/claude-3.5-sonnet"

        agent = GenericAgent(llm=mock_llm, available_tools=[])
        user_prompt = "What deployment tools exist?"
        invocation_id = uuid4()
        state: AgentState = {
            "prompt": user_prompt,
            "original_prompt": user_prompt,
            "session_id": "test-session",
            "invocation_id": invocation_id,
            "actor_context": AuditActorContext(),
            "context_package": None,
            "current_agent": "generic_agent",
            "messages": [HumanMessage("test")],
            "result": None,
            "metadata": None,
            "llm_token_usage_log": [],
        }

        await agent.execute_as_node(state)

        mock_llm_with_tools.ainvoke.assert_called_once()
        call_args = mock_llm_with_tools.ainvoke.call_args
        assert call_args is not None

    @pytest.mark.asyncio
    async def test_generic_agent_raises_on_empty_llm_response(self) -> None:
        """Test GenericAgent raises EmptyLLMResponseError on empty LLM response."""
        mock_llm = Mock()
        mock_llm_with_tools = AsyncMock()
        mock_llm_with_tools.ainvoke.return_value = AIMessage(content="", response_metadata={})
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm.model_name = "anthropic/claude-3.5-sonnet"

        agent = GenericAgent(llm=mock_llm, available_tools=[])
        invocation_id = uuid4()
        state: AgentState = {
            "prompt": "test query",
            "original_prompt": "test query",
            "session_id": "test-session",
            "invocation_id": invocation_id,
            "actor_context": AuditActorContext(),
            "context_package": None,
            "current_agent": "generic_agent",
            "messages": [HumanMessage("test")],
            "result": None,
            "metadata": None,
            "llm_token_usage_log": [],
        }

        with patch("syntara.core.utils.retry.get_settings") as mock_settings:
            mock_settings.return_value.adapter_max_retries = 0
            mock_settings.return_value.adapter_request_timeout_seconds = 30
            with pytest.raises(AgentOrchestratorError):
                await agent.execute_as_node(state)

    @pytest.mark.asyncio
    async def test_generic_agent_allows_tool_calls_with_empty_text(self) -> None:
        """Test GenericAgent does not raise when LLM returns tool_calls with empty text."""
        mock_llm = Mock()
        mock_llm_with_tools = AsyncMock()
        mock_llm_with_tools.ainvoke.return_value = AIMessage(
            content="",
            response_metadata={},
            tool_calls=[{"name": "get_greeting", "args": {"name": "jimmy"}, "id": "call_1"}],
        )
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm.model_name = "anthropic/claude-3.5-sonnet"

        agent = GenericAgent(llm=mock_llm, available_tools=[])
        invocation_id = uuid4()
        state: AgentState = {
            "prompt": "test query",
            "original_prompt": "test query",
            "session_id": "test-session",
            "invocation_id": invocation_id,
            "actor_context": AuditActorContext(),
            "context_package": None,
            "current_agent": "generic_agent",
            "messages": [HumanMessage("test")],
            "result": None,
            "metadata": None,
            "llm_token_usage_log": [],
        }

        response = await agent.execute_as_node(state)

        assert isinstance(response, dict)
        assert response["result"] is not None

    @pytest.mark.asyncio
    async def test_generic_agent_raises_error_for_malformed_llm_response(self) -> None:
        """Test GenericAgent raises AgentOrchestratorError for malformed LLM responses."""
        mock_llm = Mock()
        mock_llm_with_tools = AsyncMock()
        mock_llm_with_tools.ainvoke.return_value = None  # Malformed response
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm.model_name = "anthropic/claude-3.5-sonnet"

        agent = GenericAgent(llm=mock_llm, available_tools=[])
        invocation_id = uuid4()
        state: AgentState = {
            "prompt": "test query",
            "original_prompt": "test query",
            "session_id": "test-session",
            "invocation_id": invocation_id,
            "actor_context": AuditActorContext(),
            "context_package": None,
            "current_agent": "generic_agent",
            "messages": [HumanMessage("test")],
            "result": None,
            "metadata": None,
            "llm_token_usage_log": [],
        }

        with pytest.raises(AgentOrchestratorError) as exc_info:
            await agent.execute_as_node(state)

        assert exc_info.value.invocation_id == str(invocation_id)


class TestGenericAgentLogging:
    """Test GenericAgent logging."""

    @pytest.mark.asyncio
    async def test_generic_agent_logs_llm_interactions(
        self,
    ) -> None:
        """Test GenericAgent logs all LLM interactions."""
        mock_llm = Mock()
        mock_llm_with_tools = AsyncMock()
        mock_llm_with_tools.ainvoke.return_value = AIMessage(content="Test response", response_metadata={})
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm.model_name = "anthropic/claude-3.5-sonnet"

        agent = GenericAgent(llm=mock_llm, available_tools=[])
        invocation_id = uuid4()
        state: AgentState = {
            "prompt": "test query",
            "original_prompt": "test query",
            "session_id": "test-session",
            "invocation_id": invocation_id,
            "actor_context": AuditActorContext(),
            "context_package": None,
            "current_agent": "generic_agent",
            "messages": [HumanMessage("test")],
            "result": None,
            "metadata": None,
            "llm_token_usage_log": [],
        }

        with patch.object(agent, "logger") as mock_logger:
            await agent.execute_as_node(state)

            assert mock_logger.info.called


# T012: _build_token_usage_entry tests


class TestBuildTokenUsageEntry:
    """Tests for _build_token_usage_entry helper extracting token data from AIMessage."""

    def _make_agent(self) -> GenericAgent:
        mock_llm = Mock()
        return GenericAgent(llm=mock_llm, available_tools=[])

    def test_extracts_from_usage_metadata(self) -> None:
        """Test extraction via usage_metadata path (preferred)."""
        agent = self._make_agent()
        msg = AIMessage(
            content="test",
            usage_metadata={"input_tokens": 943, "output_tokens": 500, "total_tokens": 1443},
            response_metadata={},
        )
        result = agent._build_token_usage_entry(msg)
        assert result is not None
        assert result["input_tokens"] == 943
        assert result["output_tokens"] == 500

    def test_extracts_from_response_metadata_fallback(self) -> None:
        """Test extraction via response_metadata['token_usage'] fallback."""
        agent = self._make_agent()
        msg = AIMessage(
            content="test",
            response_metadata={
                "token_usage": {
                    "prompt_tokens": 800,
                    "completion_tokens": 200,
                    "total_tokens": 1000,
                }
            },
        )
        result = agent._build_token_usage_entry(msg)
        assert result is not None
        assert result["input_tokens"] == 800
        assert result["output_tokens"] == 200

    def test_returns_none_when_no_metadata(self) -> None:
        """Test returns None when no token metadata available (FR-008)."""
        agent = self._make_agent()
        msg = AIMessage(content="test", response_metadata={})
        result = agent._build_token_usage_entry(msg)
        assert result is None

    def test_zero_output_tokens(self) -> None:
        """Test zero output tokens edge case (empty LLM response)."""
        agent = self._make_agent()
        msg = AIMessage(
            content="",
            usage_metadata={"input_tokens": 943, "output_tokens": 0, "total_tokens": 943},
            response_metadata={},
        )
        result = agent._build_token_usage_entry(msg)
        assert result is not None
        assert result["output_tokens"] == 0
        assert result["input_tokens"] == 943


# T013: token usage log accumulation tests


class TestTokenUsageLogAccumulation:
    """Tests for llm_token_usage_log accumulation across LLM calls."""

    @pytest.mark.asyncio
    async def test_token_usage_entry_returned_in_state(self) -> None:
        """Test that _execute returns llm_token_usage_log entry in state."""
        mock_llm = Mock()
        mock_llm_with_tools = AsyncMock()
        mock_llm_with_tools.ainvoke.return_value = AIMessage(
            content="Test response",
            usage_metadata={"input_tokens": 500, "output_tokens": 100, "total_tokens": 600},
            response_metadata={},
        )
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm.model_name = "test-model"

        agent = GenericAgent(llm=mock_llm, available_tools=[])
        invocation_id = uuid4()
        state: AgentState = {
            "prompt": "test",
            "original_prompt": "test",
            "session_id": "test-session",
            "invocation_id": invocation_id,
            "actor_context": AuditActorContext(),
            "context_package": None,
            "current_agent": "generic_agent",
            "messages": [HumanMessage("test")],
            "result": None,
            "metadata": None,
            "llm_token_usage_log": [],
        }

        response = await agent.execute_as_node(state)

        assert "llm_token_usage_log" in response
        log = response["llm_token_usage_log"]
        assert len(log) == 1
        assert log[0]["input_tokens"] == 500
        assert log[0]["output_tokens"] == 100

    @pytest.mark.asyncio
    async def test_no_entry_when_no_usage_metadata(self) -> None:
        """Test no entry added when LLM returns no usage metadata."""
        mock_llm = Mock()
        mock_llm_with_tools = AsyncMock()
        mock_llm_with_tools.ainvoke.return_value = AIMessage(
            content="Test response",
            response_metadata={},
        )
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm.model_name = "test-model"

        agent = GenericAgent(llm=mock_llm, available_tools=[])
        invocation_id = uuid4()
        state: AgentState = {
            "prompt": "test",
            "original_prompt": "test",
            "session_id": "test-session",
            "invocation_id": invocation_id,
            "actor_context": AuditActorContext(),
            "context_package": None,
            "current_agent": "generic_agent",
            "messages": [HumanMessage("test")],
            "result": None,
            "metadata": None,
            "llm_token_usage_log": [],
        }

        response = await agent.execute_as_node(state)

        # Should return empty list (no entry added)
        assert response.get("llm_token_usage_log", []) == []
