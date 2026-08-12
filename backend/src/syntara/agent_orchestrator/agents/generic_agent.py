"""GenericAgent implementation using LangChain.

Handles information queries and questions using LLM via OpenRouter.
"""

import json as _json
from typing import TYPE_CHECKING, Any, NamedTuple
from uuid import UUID

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from syntara.agent_orchestrator.agents.base_agent import BaseAgent
from syntara.agent_orchestrator.audit.agent_execution import (
    AgentExecutionEvent,
    AgentExecutionStatus,
)
from syntara.agent_orchestrator.audit.llm_interaction import (
    LLMInteractionEvent,
    LLMInteractionStatus,
    LLMInteractionType,
)
from syntara.agent_orchestrator.exceptions import EmptyLLMResponseError
from syntara.agent_orchestrator.models import GenericAgentResponse
from syntara.agent_orchestrator.models.agent_state import AgentState
from syntara.agent_orchestrator.utils.keyword_association import annotate_tools_with_relevance
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.core.config.base import get_settings
from syntara.core.utils.retry import retry_with_backoff
from syntara.metrics.dependencies import get_metrics_recorder
from syntara.metrics.instrumentation import record_llm_call

if TYPE_CHECKING:
    from langchain.messages import AnyMessage

logger = structlog.stdlib.get_logger(__name__)


class _InvocationContext(NamedTuple):
    """Context fields extracted from AgentState for audit events."""

    session_id: str
    invocation_id: UUID
    execution_id: UUID | None
    request_id: UUID | None
    metadata: dict[str, Any]
    activity_id: str | None
    activity_name: str | None


class GenericAgent(BaseAgent):
    """Agent for answering information queries using LangChain LLM.

    Uses LangChain with OpenRouter to provide natural language answers
    to user questions about tools, services, and capabilities.
    """

    def __init__(self, llm: ChatOpenAI, available_tools: list[BaseTool]) -> None:
        """Initialize GenericAgent with LangChain LLM.

        Args:
            llm: Configured ChatOpenAI instance (from openrouter_config)
            available_tools: Tools that are available to the LLM

        """
        super().__init__()
        self.llm: ChatOpenAI = llm
        self.available_tools = available_tools

    @retry_with_backoff
    async def _execute(self, state: AgentState) -> AgentState:
        """Execute GenericAgent-specific logic: query LLM for answer.

        Args:
            state: LangGraph state containing enhanced prompt and metadata

        Returns:
            GenericAgentResponse SQLModel instance with LLM-generated answer

        """
        # Extract context from AgentState
        session_id = state["session_id"]
        invocation_id = state["invocation_id"]
        execution_id = state.get("execution_id", None)
        request_id = state.get("request_id", None)

        # Emit START event
        AuditEventDispatcher.dispatch(
            AgentExecutionEvent(
                agent_type="generic_agent",
                session_id=session_id,
                invocation_id=invocation_id,
                execution_id=execution_id,
                request_id=request_id,
                status=AgentExecutionStatus.STARTED,
            )
        )

        try:
            response_schema = state.get("response_schema")

            # Case B: Structured output with no tools - use .with_structured_output() directly
            if response_schema and not self.available_tools:
                state = await self._execute_structured(state, response_schema)
            else:
                # Standard execution (with or without tools)
                state = await self._execute_standard(state)

                # Case A: Structured output with tools - run extraction step after tool loop
                if response_schema and self.available_tools:
                    state = await self._extract_structured_output(state, response_schema)

            # Emit COMPLETED event
            AuditEventDispatcher.dispatch(
                AgentExecutionEvent(
                    agent_type="generic_agent",
                    session_id=session_id,
                    invocation_id=invocation_id,
                    execution_id=execution_id,
                    request_id=request_id,
                    status=AgentExecutionStatus.COMPLETED,
                )
            )

            return state

        except Exception as e:
            # Emit FAILED event
            AuditEventDispatcher.dispatch(
                AgentExecutionEvent(
                    agent_type="generic_agent",
                    session_id=session_id,
                    invocation_id=invocation_id,
                    execution_id=execution_id,
                    request_id=request_id,
                    status=AgentExecutionStatus.FAILED,
                    error_type=type(e).__name__,
                )
            )
            raise

    @staticmethod
    def _extract_context(state: AgentState) -> _InvocationContext:
        """Extract common invocation context from AgentState.

        Args:
            state: LangGraph state containing session/invocation metadata

        Returns:
            _InvocationContext with all extracted fields

        """
        metadata = state.get("metadata") or {}
        return _InvocationContext(
            session_id=state["session_id"],
            invocation_id=state["invocation_id"],
            execution_id=state.get("execution_id", None),
            request_id=state.get("request_id", None),
            metadata=metadata,
            activity_id=metadata.get("activity_id"),
            activity_name=metadata.get("activity_name"),
        )

    async def _execute_standard(self, state: AgentState) -> AgentState:
        """Execute standard LLM call with tools.

        Args:
            state: LangGraph state containing enhanced prompt and metadata

        Returns:
            Updated state with LLM response

        """
        ctx = self._extract_context(state)

        # Annotate tools with keyword relevance hints before binding
        # Use original_prompt (raw user input) — the enhanced prompt includes
        # context sections that dilute keyword scores.
        prompt = state.get("original_prompt", "")
        annotated_tools = annotate_tools_with_relevance(prompt, self.available_tools)

        # Query LLM via LangChain (async)
        llm_with_tools = self.llm.bind_tools(annotated_tools)
        # Use state["prompt"] which contains the context-enhanced prompt
        # (with retrieved documents) from the orchestrator, rather than
        # state["messages"] which only has the original user input.
        messages: list[AnyMessage] = [
            SystemMessage(
                content=f"You are an information assistant for the {get_settings().product_name} automation system. "
                "Answer user questions concisely and accurately. "
                "Focus on providing helpful, direct answers about tools, services, and capabilities."
            ),
            HumanMessage(content=state["prompt"]),
        ]
        # On re-entry after tool execution, carry forward tool-call history
        # (AIMessage with tool_calls + ToolMessage with results).
        messages.extend(msg for msg in state["messages"] if not isinstance(msg, HumanMessage))
        result_message = await record_llm_call(
            get_metrics_recorder(),
            lambda: llm_with_tools.ainvoke(messages),
            model=getattr(self.llm, "model_name", None),
        )

        # Tool-call-only responses (empty text but tool_calls present) are valid;
        # check BEFORE mutating state so retry_with_backoff replays the original messages.
        answer = str(result_message.text)
        if (not answer or not answer.strip()) and not result_message.tool_calls:
            # Emit EMPTY_RESPONSE event before raising
            AuditEventDispatcher.dispatch(
                LLMInteractionEvent(
                    session_id=ctx.session_id,
                    invocation_id=ctx.invocation_id,
                    execution_id=ctx.execution_id,
                    request_id=ctx.request_id,
                    interaction_type=LLMInteractionType.STANDARD,
                    model_name=getattr(self.llm, "model_name", "unknown"),
                    status=LLMInteractionStatus.EMPTY_RESPONSE,
                    error_type="EmptyLLMResponseError",
                    activity_id=ctx.activity_id,
                    activity_name=ctx.activity_name,
                )
            )
            raise EmptyLLMResponseError(invocation_id=str(ctx.invocation_id))

        # Emit SUCCESS event after successful LLM call
        tool_calls_count = len(result_message.tool_calls) if result_message.tool_calls else 0
        AuditEventDispatcher.dispatch(
            LLMInteractionEvent(
                session_id=ctx.session_id,
                invocation_id=ctx.invocation_id,
                execution_id=ctx.execution_id,
                request_id=ctx.request_id,
                interaction_type=LLMInteractionType.STANDARD,
                model_name=getattr(self.llm, "model_name", "unknown"),
                status=LLMInteractionStatus.SUCCESS,
                tools_available=len(self.available_tools),
                tool_calls_made=tool_calls_count,
                response_schema_provided=bool(state.get("response_schema")),
                activity_id=ctx.activity_id,
                activity_name=ctx.activity_name,
            )
        )

        # Collect token usage from LLM response for post-LLM update
        token_entry = self._build_token_usage_entry(result_message)
        token_log: list[dict[str, Any]] = [token_entry] if token_entry is not None else []

        # Update AgentState
        state["messages"] = [result_message]
        state["llm_token_usage_log"] = token_log
        response_metadata = result_message.response_metadata
        response_model: GenericAgentResponse = GenericAgentResponse(content=answer, response_metadata=response_metadata)

        state["result"] = response_model.model_dump(by_alias=True)

        return state

    async def _execute_structured(self, state: AgentState, response_schema: dict[str, Any]) -> AgentState:
        """Execute with structured output directly (no tools).

        Args:
            state: LangGraph state
            response_schema: JSON Schema for structured output

        Returns:
            Updated state with structured output

        """
        ctx = self._extract_context(state)

        try:
            # include_raw=True so we can read provider usage from the AIMessage
            structured_llm = self.llm.with_structured_output(response_schema, method="json_mode", include_raw=True)
            schema_str = _json.dumps(response_schema, indent=2)
            product = get_settings().product_name
            messages = [
                SystemMessage(
                    content=f"You are an information assistant for the {product} automation system. "
                    "You MUST respond with ONLY a valid JSON object matching this exact schema:\n\n"
                    f"```json\n{schema_str}\n```\n\n"
                    "Use exactly the property names from the schema. "
                    "Do not include any text outside the JSON object."
                ),
                HumanMessage(content=state["prompt"]),
            ]

            structured_response = await record_llm_call(
                get_metrics_recorder(),
                lambda: structured_llm.ainvoke(messages),
                model=getattr(self.llm, "model_name", None),
            )
            parsed_output, raw_message = self._unpack_structured_response(structured_response)
        except Exception as e:  # noqa: BLE001
            # Emit ERROR event before fallback
            AuditEventDispatcher.dispatch(
                LLMInteractionEvent(
                    session_id=ctx.session_id,
                    invocation_id=ctx.invocation_id,
                    execution_id=ctx.execution_id,
                    request_id=ctx.request_id,
                    interaction_type=LLMInteractionType.STRUCTURED_OUTPUT,
                    model_name=getattr(self.llm, "model_name", "unknown"),
                    status=LLMInteractionStatus.ERROR,
                    tools_available=0,
                    response_schema_provided=True,
                    error_type=type(e).__name__,
                    activity_id=ctx.activity_id,
                    activity_name=ctx.activity_name,
                )
            )
            logger.warning("Structured output failed, falling back to standard execution", exc_info=True)
            return await self._execute_standard(state)

        # include_raw=True returns parse failures as {parsed: None, raw: ...} instead of
        # raising — treat like the exception path: count billed tokens, then degrade to
        # standard execution (pre-include_raw behavior).
        if parsed_output is None:
            AuditEventDispatcher.dispatch(
                LLMInteractionEvent(
                    session_id=ctx.session_id,
                    invocation_id=ctx.invocation_id,
                    execution_id=ctx.execution_id,
                    request_id=ctx.request_id,
                    interaction_type=LLMInteractionType.STRUCTURED_OUTPUT,
                    model_name=getattr(self.llm, "model_name", "unknown"),
                    status=LLMInteractionStatus.ERROR,
                    tools_available=0,
                    response_schema_provided=True,
                    error_type="StructuredOutputParseError",
                    activity_id=ctx.activity_id,
                    activity_name=ctx.activity_name,
                )
            )
            logger.warning("Structured output parse returned None, falling back to standard execution")
            structured_token_entry = self._build_token_usage_entry(raw_message) if raw_message is not None else None
            state = await self._execute_standard(state)
            # _execute_standard replaces llm_token_usage_log — keep the billed structured call.
            if structured_token_entry is not None:
                fallback_log = list(state.get("llm_token_usage_log") or [])
                state["llm_token_usage_log"] = [structured_token_entry, *fallback_log]
            return state

        # Emit SUCCESS event after successful structured output
        AuditEventDispatcher.dispatch(
            LLMInteractionEvent(
                session_id=ctx.session_id,
                invocation_id=ctx.invocation_id,
                execution_id=ctx.execution_id,
                request_id=ctx.request_id,
                interaction_type=LLMInteractionType.STRUCTURED_OUTPUT,
                model_name=getattr(self.llm, "model_name", "unknown"),
                status=LLMInteractionStatus.SUCCESS,
                tools_available=0,  # No tools in structured mode
                response_schema_provided=True,
                fallback_strategy_used="native",
                activity_id=ctx.activity_id,
                activity_name=ctx.activity_name,
            )
        )

        token_entry = self._build_token_usage_entry(raw_message) if raw_message is not None else None
        state["llm_token_usage_log"] = [token_entry] if token_entry is not None else []
        state["messages"] = [raw_message] if raw_message is not None else []

        result_dict = GenericAgentResponse(
            content=parsed_output,
            response_metadata=getattr(raw_message, "response_metadata", None) or {},
        ).model_dump(by_alias=True)
        result_dict["structured_output_metadata"] = {"fallback_strategy_used": "native"}
        state["result"] = result_dict

        return state

    async def _extract_structured_output(self, state: AgentState, response_schema: dict[str, Any]) -> AgentState:
        """Post-tool-loop extraction: reformat result into schema.

        Args:
            state: State after tool execution
            response_schema: JSON Schema for structured output

        Returns:
            Updated state with structured content

        """
        ctx = self._extract_context(state)

        try:
            result_dict = state.get("result")
            if not result_dict:
                return state

            current_answer = result_dict.get("content", "")
            if not current_answer:
                return state

            # include_raw=True so the extraction LLM call is counted in token totals
            extraction_llm = self.llm.with_structured_output(response_schema, method="json_mode", include_raw=True)
            schema_str = _json.dumps(response_schema, indent=2)
            extraction_messages = [
                SystemMessage(
                    content="Extract and format the following information into this exact JSON schema:\n\n"
                    f"```json\n{schema_str}\n```\n\n"
                    "Use exactly the property names from the schema. "
                    "Do not include any text outside the JSON object."
                ),
                HumanMessage(content=f"Extract from this text:\n\n{current_answer}"),
            ]

            structured_response = await record_llm_call(
                get_metrics_recorder(),
                lambda: extraction_llm.ainvoke(extraction_messages),
                model=getattr(self.llm, "model_name", None),
            )
            parsed_output, raw_message = self._unpack_structured_response(structured_response)

            # Count provider tokens for the extraction call even when parsing fails —
            # the LLM was billed regardless of whether parsed_output is usable.
            token_entry = self._build_token_usage_entry(raw_message) if raw_message is not None else None
            if token_entry is not None:
                existing_log = list(state.get("llm_token_usage_log") or [])
                existing_log.append(token_entry)
                state["llm_token_usage_log"] = existing_log

            if parsed_output is None:
                result_dict["structured_output_metadata"] = {"fallback_strategy_used": "none"}
                return state

            # Emit SUCCESS only when extraction produced usable structured output
            AuditEventDispatcher.dispatch(
                LLMInteractionEvent(
                    session_id=ctx.session_id,
                    invocation_id=ctx.invocation_id,
                    execution_id=ctx.execution_id,
                    request_id=ctx.request_id,
                    interaction_type=LLMInteractionType.EXTRACTION,
                    model_name=getattr(self.llm, "model_name", "unknown"),
                    status=LLMInteractionStatus.SUCCESS,
                    response_schema_provided=True,
                    fallback_strategy_used="native",
                    activity_id=ctx.activity_id,
                    activity_name=ctx.activity_name,
                )
            )

            result_dict["content"] = parsed_output
            result_dict["structured_output_metadata"] = {"fallback_strategy_used": "native"}
            return state
        except Exception as e:  # noqa: BLE001
            # Emit ERROR event before fallback
            AuditEventDispatcher.dispatch(
                LLMInteractionEvent(
                    session_id=ctx.session_id,
                    invocation_id=ctx.invocation_id,
                    execution_id=ctx.execution_id,
                    request_id=ctx.request_id,
                    interaction_type=LLMInteractionType.EXTRACTION,
                    model_name=getattr(self.llm, "model_name", "unknown"),
                    status=LLMInteractionStatus.ERROR,
                    error_type=type(e).__name__,
                    activity_id=ctx.activity_id,
                    activity_name=ctx.activity_name,
                )
            )
            logger.warning("Structured output extraction failed, keeping raw text", exc_info=True)
            result_dict = state.get("result")
            if result_dict:
                result_dict["structured_output_metadata"] = {"fallback_strategy_used": "none"}
            return state

    @staticmethod
    def _unpack_structured_response(response: object) -> tuple[object, AIMessage | None]:
        """Unpack ``with_structured_output(..., include_raw=True)`` response.

        Returns:
            Tuple of (parsed_output, raw AIMessage if available).

        """
        if isinstance(response, dict) and "parsed" in response:
            raw = response.get("raw")
            return response.get("parsed"), raw if isinstance(raw, AIMessage) else None
        return response, None

    @staticmethod
    def _build_token_usage_entry(result_message: AIMessage) -> dict[str, Any] | None:
        """Extract token usage data from an AIMessage response.

        Args:
            result_message: AIMessage from the LLM provider

        Returns:
            Dict with input_tokens, output_tokens, and usage_details,
            or None if no token metadata is available.

        """
        usage_meta = result_message.usage_metadata
        if usage_meta and isinstance(usage_meta, dict):
            input_tokens = usage_meta.get("input_tokens")
            if input_tokens is not None:
                return {
                    "input_tokens": input_tokens,
                    "output_tokens": usage_meta.get("output_tokens") or 0,
                    "usage_details": dict(usage_meta),
                }

        # Fallback path: response_metadata["token_usage"]
        response_meta = result_message.response_metadata
        if response_meta and isinstance(response_meta, dict):
            token_usage = response_meta.get("token_usage")
            if token_usage and isinstance(token_usage, dict):
                prompt_tokens = token_usage.get("prompt_tokens")
                if prompt_tokens is not None:
                    return {
                        "input_tokens": prompt_tokens,
                        "output_tokens": token_usage.get("completion_tokens") or 0,
                        "usage_details": dict(token_usage),
                    }

        return None
