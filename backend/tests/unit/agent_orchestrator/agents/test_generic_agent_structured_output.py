"""Unit tests for GenericAgent structured output support."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

from syntara.audit.emitter import AuditActorContext

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI

from syntara.agent_orchestrator.agents.generic_agent import GenericAgent
from syntara.agent_orchestrator.models.agent_state import AgentState


@pytest.fixture
def mock_llm() -> MagicMock:
    """Create a mock ChatOpenAI instance."""
    llm: MagicMock = MagicMock(spec=ChatOpenAI)
    llm.model_name = "gpt-4"
    return llm


@pytest.fixture
def sample_state() -> AgentState:
    """Create a sample agent state for testing."""
    return AgentState(
        prompt="Extract server information",
        original_prompt="Extract server information",
        session_id="test-session",
        invocation_id=uuid4(),
        actor_context=AuditActorContext(),
        context_package=None,
        current_agent="generic_agent",
        metadata=None,
        messages=[HumanMessage(content="Extract server information")],
        result=None,
        llm_token_usage_log=[],
    )


@pytest.fixture
def server_info_schema() -> dict[str, Any]:
    """JSON Schema for server information."""
    return {
        "type": "object",
        "properties": {
            "hostname": {"type": "string"},
            "ip": {"type": "string"},
            "status": {"type": "string"},
        },
        "required": ["hostname", "ip"],
    }


def _make_record_side_effect() -> Callable[..., Coroutine[Any, Any, Any]]:
    async def _side_effect(_recorder: object, fn: Callable[..., Any], *, model: object = None) -> Any:  # noqa: ANN401
        return await fn()

    return _side_effect


class TestGenericAgentStructuredOutputNoTools:
    """Test GenericAgent structured output with no tools (Case B)."""

    @pytest.mark.asyncio
    async def test_execute_structured_output_no_tools_success(
        self, mock_llm: MagicMock, sample_state: AgentState, server_info_schema: dict[str, Any]
    ) -> None:
        """Test structured output execution with no tools succeeds."""
        sample_state["response_schema"] = server_info_schema

        parsed_output = {"hostname": "server-01", "ip": "192.168.1.10", "status": "active"}
        raw_message = AIMessage(
            content='{"hostname":"server-01"}',
            usage_metadata={"input_tokens": 80, "output_tokens": 20, "total_tokens": 100},
        )

        mock_structured_llm = MagicMock()
        mock_structured_llm.ainvoke = AsyncMock(
            return_value={"raw": raw_message, "parsed": parsed_output, "parsing_error": None}
        )
        mock_llm.with_structured_output.return_value = mock_structured_llm

        agent = GenericAgent(llm=mock_llm, available_tools=[])

        with patch("syntara.agent_orchestrator.agents.generic_agent.record_llm_call") as mock_record:
            mock_record.side_effect = _make_record_side_effect()
            result_state = await agent.execute_as_node(sample_state)

        assert result_state["result"] is not None
        assert result_state["result"]["content"] == parsed_output
        assert result_state["result"]["structured_output_metadata"]["fallback_strategy_used"] == "native"
        mock_llm.with_structured_output.assert_called_with(server_info_schema, method="json_mode", include_raw=True)

    @pytest.mark.asyncio
    async def test_execute_structured_output_no_tools_fallback(
        self, mock_llm: MagicMock, sample_state: AgentState, server_info_schema: dict[str, Any]
    ) -> None:
        """Test structured output falls back to standard execution on error."""
        sample_state["response_schema"] = server_info_schema

        mock_structured_llm = MagicMock()
        mock_structured_llm.ainvoke = AsyncMock(side_effect=Exception("Structured output not supported"))
        mock_llm.with_structured_output.return_value = mock_structured_llm

        standard_message = AIMessage(
            content="hostname: server-01, ip: 192.168.1.10",
            response_metadata={"model": "gpt-4"},
            usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
        )
        mock_llm.bind_tools.return_value.ainvoke = AsyncMock(return_value=standard_message)

        agent = GenericAgent(llm=mock_llm, available_tools=[])

        with patch("syntara.agent_orchestrator.agents.generic_agent.record_llm_call") as mock_record:
            mock_record.side_effect = _make_record_side_effect()
            result_state = await agent.execute_as_node(sample_state)

        assert result_state["result"] is not None
        assert isinstance(result_state["result"]["content"], str)
        assert "server-01" in result_state["result"]["content"]

    @pytest.mark.asyncio
    async def test_execute_structured_parse_none_falls_back_and_keeps_tokens(
        self, mock_llm: MagicMock, sample_state: AgentState, server_info_schema: dict[str, Any]
    ) -> None:
        """include_raw parse failures degrade to standard and keep both calls' tokens."""
        sample_state["response_schema"] = server_info_schema

        structured_raw = AIMessage(
            content="not-valid-json-for-schema",
            usage_metadata={"input_tokens": 80, "output_tokens": 20, "total_tokens": 100},
        )
        mock_structured_llm = MagicMock()
        mock_structured_llm.ainvoke = AsyncMock(
            return_value={"raw": structured_raw, "parsed": None, "parsing_error": "parse failed"}
        )
        mock_llm.with_structured_output.return_value = mock_structured_llm

        standard_message = AIMessage(
            content="hostname: server-01, ip: 192.168.1.10",
            response_metadata={"model": "gpt-4"},
            usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
        )
        mock_llm.bind_tools.return_value.ainvoke = AsyncMock(return_value=standard_message)

        agent = GenericAgent(llm=mock_llm, available_tools=[])

        with patch("syntara.agent_orchestrator.agents.generic_agent.record_llm_call") as mock_record:
            mock_record.side_effect = _make_record_side_effect()
            result_state = await agent.execute_as_node(sample_state)

        assert result_state["result"] is not None
        assert isinstance(result_state["result"]["content"], str)
        assert "server-01" in result_state["result"]["content"]
        # Structured billed call (80+20) then standard fallback (100+50)
        assert result_state["llm_token_usage_log"] == [
            {
                "input_tokens": 80,
                "output_tokens": 20,
                "usage_details": {"input_tokens": 80, "output_tokens": 20, "total_tokens": 100},
            },
            {
                "input_tokens": 100,
                "output_tokens": 50,
                "usage_details": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            },
        ]


class TestGenericAgentStructuredOutputWithTools:
    """Test GenericAgent structured output with tools (Case A)."""

    @pytest.mark.asyncio
    async def test_execute_structured_output_with_tools_extraction(
        self, mock_llm: MagicMock, sample_state: AgentState, server_info_schema: dict[str, Any]
    ) -> None:
        """Test structured output extraction after tool loop."""
        sample_state["response_schema"] = server_info_schema

        standard_message = AIMessage(
            content="The server hostname is server-01 and IP is 192.168.1.10",
            response_metadata={"model": "gpt-4"},
            usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
        )
        mock_llm.bind_tools.return_value.ainvoke = AsyncMock(return_value=standard_message)

        extracted_output = {"hostname": "server-01", "ip": "192.168.1.10", "status": "unknown"}
        extraction_raw = AIMessage(
            content='{"hostname":"server-01"}',
            usage_metadata={"input_tokens": 40, "output_tokens": 15, "total_tokens": 55},
        )
        mock_extraction_llm = MagicMock()
        mock_extraction_llm.ainvoke = AsyncMock(
            return_value={"raw": extraction_raw, "parsed": extracted_output, "parsing_error": None}
        )
        mock_llm.with_structured_output.return_value = mock_extraction_llm

        mock_tool = MagicMock()
        mock_tool.name = "test_tool"

        agent = GenericAgent(llm=mock_llm, available_tools=[mock_tool])
        with patch("syntara.agent_orchestrator.agents.generic_agent.record_llm_call") as mock_record:
            mock_record.side_effect = _make_record_side_effect()
            result_state = await agent.execute_as_node(sample_state)

        assert result_state["result"] is not None
        assert result_state["result"]["content"] == extracted_output
        assert result_state["result"]["structured_output_metadata"]["fallback_strategy_used"] == "native"
        # Case A: tools present → standard tool-loop path (bind_tools), then extraction.
        mock_llm.bind_tools.assert_called()
        # Standard tool-loop call (100+50) + extraction call (40+15)
        assert result_state["llm_token_usage_log"] == [
            {
                "input_tokens": 100,
                "output_tokens": 50,
                "usage_details": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            },
            {
                "input_tokens": 40,
                "output_tokens": 15,
                "usage_details": {"input_tokens": 40, "output_tokens": 15, "total_tokens": 55},
            },
        ]

    @pytest.mark.asyncio
    async def test_execute_structured_output_with_tools_extraction_failure(
        self, mock_llm: MagicMock, sample_state: AgentState, server_info_schema: dict[str, Any]
    ) -> None:
        """Test structured output extraction failure keeps raw text."""
        sample_state["response_schema"] = server_info_schema

        standard_message = AIMessage(
            content="The server hostname is server-01",
            response_metadata={"model": "gpt-4"},
            usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
        )
        mock_llm.bind_tools.return_value.ainvoke = AsyncMock(return_value=standard_message)

        mock_extraction_llm = MagicMock()
        mock_extraction_llm.ainvoke = AsyncMock(side_effect=Exception("Extraction failed"))
        mock_llm.with_structured_output.return_value = mock_extraction_llm

        mock_tool = MagicMock()
        mock_tool.name = "test_tool"

        agent = GenericAgent(llm=mock_llm, available_tools=[mock_tool])
        with patch("syntara.agent_orchestrator.agents.generic_agent.record_llm_call") as mock_record:
            mock_record.side_effect = _make_record_side_effect()
            result_state = await agent.execute_as_node(sample_state)

        assert result_state["result"] is not None
        assert isinstance(result_state["result"]["content"], str)
        assert "server-01" in result_state["result"]["content"]
        assert result_state["result"]["structured_output_metadata"]["fallback_strategy_used"] == "none"

    @pytest.mark.asyncio
    async def test_extraction_logs_tokens_when_parsed_output_is_none(
        self, mock_llm: MagicMock, sample_state: AgentState, server_info_schema: dict[str, Any]
    ) -> None:
        """Provider billed the extraction call even if parsing returns None — still count it."""
        sample_state["response_schema"] = server_info_schema

        standard_message = AIMessage(
            content="The server hostname is server-01",
            response_metadata={"model": "gpt-4"},
            usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
        )
        mock_llm.bind_tools.return_value.ainvoke = AsyncMock(return_value=standard_message)

        extraction_raw = AIMessage(
            content="not-valid-for-schema",
            usage_metadata={"input_tokens": 40, "output_tokens": 15, "total_tokens": 55},
        )
        mock_extraction_llm = MagicMock()
        mock_extraction_llm.ainvoke = AsyncMock(
            return_value={"raw": extraction_raw, "parsed": None, "parsing_error": "parse failed"}
        )
        mock_llm.with_structured_output.return_value = mock_extraction_llm

        mock_tool = MagicMock()
        mock_tool.name = "test_tool"

        agent = GenericAgent(llm=mock_llm, available_tools=[mock_tool])
        with patch("syntara.agent_orchestrator.agents.generic_agent.record_llm_call") as mock_record:
            mock_record.side_effect = _make_record_side_effect()
            result_state = await agent.execute_as_node(sample_state)

        assert result_state["result"] is not None
        assert result_state["result"]["structured_output_metadata"]["fallback_strategy_used"] == "none"
        assert result_state["llm_token_usage_log"] == [
            {
                "input_tokens": 100,
                "output_tokens": 50,
                "usage_details": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            },
            {
                "input_tokens": 40,
                "output_tokens": 15,
                "usage_details": {"input_tokens": 40, "output_tokens": 15, "total_tokens": 55},
            },
        ]


class TestGenericAgentTokenTracking:
    """Test token usage tracking with structured output."""

    @pytest.mark.asyncio
    async def test_token_tracking_structured_output(
        self, mock_llm: MagicMock, sample_state: AgentState, server_info_schema: dict[str, Any]
    ) -> None:
        """Test structured output with include_raw logs provider token usage."""
        sample_state["response_schema"] = server_info_schema

        parsed_output = {"hostname": "server-01", "ip": "192.168.1.10"}
        raw_message = AIMessage(
            content='{"hostname":"server-01","ip":"192.168.1.10"}',
            usage_metadata={"input_tokens": 120, "output_tokens": 30, "total_tokens": 150},
        )

        mock_structured_llm = MagicMock()
        mock_structured_llm.ainvoke = AsyncMock(
            return_value={"raw": raw_message, "parsed": parsed_output, "parsing_error": None}
        )
        mock_llm.with_structured_output.return_value = mock_structured_llm

        agent = GenericAgent(llm=mock_llm, available_tools=[])

        with patch("syntara.agent_orchestrator.agents.generic_agent.record_llm_call") as mock_record:
            mock_record.side_effect = _make_record_side_effect()
            result_state = await agent.execute_as_node(sample_state)

        result = result_state["result"]
        assert result is not None
        assert result["content"] == parsed_output
        assert result["structured_output_metadata"]["fallback_strategy_used"] == "native"
        assert result_state["llm_token_usage_log"] == [
            {
                "input_tokens": 120,
                "output_tokens": 30,
                "usage_details": {"input_tokens": 120, "output_tokens": 30, "total_tokens": 150},
            }
        ]

    def test_unpack_structured_response_include_raw(self) -> None:
        raw = AIMessage(content="{}")
        parsed, raw_out = GenericAgent._unpack_structured_response(
            {"raw": raw, "parsed": {"a": 1}, "parsing_error": None}
        )
        assert parsed == {"a": 1}
        assert raw_out is raw

    def test_unpack_structured_response_legacy_parsed_only(self) -> None:
        parsed, raw_out = GenericAgent._unpack_structured_response({"hostname": "x"})
        assert parsed == {"hostname": "x"}
        assert raw_out is None
