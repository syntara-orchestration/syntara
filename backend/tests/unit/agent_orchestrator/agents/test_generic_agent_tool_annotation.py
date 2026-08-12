"""Integration tests for keyword-based tool annotation in GenericAgent (AAP-60442).

Verifies that annotate_tools_with_relevance is called before bind_tools
and that the LLM receives annotated tool descriptions.
"""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import BaseTool

from syntara.agent_orchestrator.agents import GenericAgent
from syntara.agent_orchestrator.models.agent_state import AgentState
from syntara.agent_orchestrator.utils.keyword_association import HINT_HIGH
from syntara.audit.emitter import AuditActorContext


def _make_state(prompt: str = "search github repos") -> AgentState:
    """Create a minimal AgentState dict for testing."""
    return {
        "prompt": prompt,
        "original_prompt": prompt,
        "session_id": "test-session",
        "invocation_id": uuid4(),
        "execution_id": None,
        "request_id": None,
        "messages": [HumanMessage(content=prompt)],
        "result": None,
        "current_agent": "generic_agent",
        "context_package": None,
        "metadata": {},
        "response_schema": None,
        "routing_duration_ms": None,
        "llm_token_usage_log": [],
        "actor_context": AuditActorContext(),
    }


def _make_real_tool(name: str, description: str) -> BaseTool:
    """Create a mock with spec=BaseTool that has mutable description."""
    tool = Mock(spec=BaseTool)
    tool.name = name
    tool.description = description
    return tool


class TestGenericAgentToolAnnotation:
    """Verify keyword annotation integrates with GenericAgent execution."""

    @pytest.mark.asyncio
    async def test_bind_tools_receives_annotated_descriptions(self) -> None:
        """Tools with matching keywords get hints before bind_tools."""
        mock_llm = Mock()
        mock_llm_with_tools = AsyncMock()
        mock_llm_with_tools.ainvoke.return_value = AIMessage(
            content="Found relevant repositories.",
            response_metadata={},
        )
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm.model_name = "test-model"

        search_tool = _make_real_tool("search_repos", "Search GitHub repositories")
        calc_tool = _make_real_tool("calculate_sum", "Add two numbers together")

        agent = GenericAgent(llm=mock_llm, available_tools=[search_tool, calc_tool])
        state = _make_state("search github repos")

        with patch("syntara.agent_orchestrator.agents.generic_agent.AuditEventDispatcher"):
            await agent._execute_standard(state)

        bound_tools = mock_llm.bind_tools.call_args[0][0]
        search_bound = next(t for t in bound_tools if t.name == "search_repos")
        calc_bound = next(t for t in bound_tools if t.name == "calculate_sum")

        assert search_bound.description.startswith(HINT_HIGH)
        assert not calc_bound.description.startswith(HINT_HIGH)

    @pytest.mark.asyncio
    async def test_all_tools_passed_to_bind_tools(self) -> None:
        """No tools are removed — all are passed to bind_tools."""
        mock_llm = Mock()
        mock_llm_with_tools = AsyncMock()
        mock_llm_with_tools.ainvoke.return_value = AIMessage(
            content="Done.",
            response_metadata={},
        )
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm.model_name = "test-model"

        tools = [
            _make_real_tool("search_repos", "Search repositories"),
            _make_real_tool("calculate_sum", "Add numbers"),
            _make_real_tool("send_email", "Send notification email"),
        ]

        agent = GenericAgent(llm=mock_llm, available_tools=tools)
        state = _make_state("search repos")

        with patch("syntara.agent_orchestrator.agents.generic_agent.AuditEventDispatcher"):
            await agent._execute_standard(state)

        bound_tools = mock_llm.bind_tools.call_args[0][0]
        assert len(bound_tools) == 3

    @pytest.mark.asyncio
    async def test_relevant_tools_sorted_first(self) -> None:
        """Relevant tools appear before irrelevant ones in bind_tools."""
        mock_llm = Mock()
        mock_llm_with_tools = AsyncMock()
        mock_llm_with_tools.ainvoke.return_value = AIMessage(
            content="Done.",
            response_metadata={},
        )
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm.model_name = "test-model"

        tools = [
            _make_real_tool("calculate_sum", "Add two numbers"),
            _make_real_tool("search_repos", "Search GitHub repositories for code"),
            _make_real_tool("send_email", "Send notification email"),
        ]

        agent = GenericAgent(llm=mock_llm, available_tools=tools)
        state = _make_state("search github code")

        with patch("syntara.agent_orchestrator.agents.generic_agent.AuditEventDispatcher"):
            await agent._execute_standard(state)

        bound_tools = mock_llm.bind_tools.call_args[0][0]
        assert bound_tools[0].name == "search_repos"

    @pytest.mark.asyncio
    async def test_uses_original_prompt_not_enhanced(self) -> None:
        """Annotation uses original_prompt, not the context-enhanced prompt.

        The enhanced prompt adds context sections that dilute keyword scores.
        """
        mock_llm = Mock()
        mock_llm_with_tools = AsyncMock()
        mock_llm_with_tools.ainvoke.return_value = AIMessage(
            content="Done.",
            response_metadata={},
        )
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm.model_name = "test-model"

        tools = [_make_real_tool("search_repos", "Search GitHub repositories")]

        agent = GenericAgent(llm=mock_llm, available_tools=tools)

        state = _make_state("search github repos")
        # Simulate OrchestratorAgent enrichment: prompt gets context appended
        state["prompt"] = (
            "search github repos\n\n--- CONTEXT ---\n"
            "Available tools: search_repos, calculate_sum, send_email\n"
            "Session history: user asked about deployment"
        )

        with patch("syntara.agent_orchestrator.agents.generic_agent.AuditEventDispatcher"):
            await agent._execute_standard(state)

        bound_tools = mock_llm.bind_tools.call_args[0][0]
        # With original_prompt ("search github repos" → 3 keywords, 3 match → HIGH)
        # With enhanced prompt (many extra keywords dilute → LOW or none)
        assert bound_tools[0].description.startswith(HINT_HIGH)
