"""Resolve model and MCP operations requested by one AO Task Agent workload."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, cast

import structlog
from execution_plane_client.commands.agent import AgentOperation, AgentOperationCommandResult
from execution_plane_client.errors import ProtocolConflict
from execution_plane_client.handlers import HandlingResult
from execution_plane_client.protocol import MessageEnvelope, ResourceReference
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.runtime import Runtime
from pydantic import ValidationError

from syntara.agent_orchestrator.agents.generic_agent import GenericAgent
from syntara.agent_orchestrator.audit.llm_interaction import (
    LLMInteractionEvent,
    LLMInteractionStatus,
    LLMInteractionType,
)
from syntara.agent_orchestrator.executor.invocation_executor import InvocationExecutor
from syntara.agent_orchestrator.models.context_data import InvocationContextData
from syntara.agent_orchestrator.models.invocation import Invocation, InvocationStatus
from syntara.agent_orchestrator.utils.context_helpers import extract_execution_id, extract_request_id
from syntara.agent_orchestrator.utils.keyword_association import annotate_tools_with_relevance
from syntara.agent_orchestrator.utils.response_metadata import normalize_response_metadata
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.core.config.base import get_settings
from syntara.execution_plane.commands.errors import CommandResourceNotFoundError, CommandResourceStateError
from syntara.execution_plane.registry.repository import (
    execution_plane_plugin_supports_revision,
    get_execution_plane_plugin,
)
from syntara.execution_plane.utils import execution_plane_work_item_id
from syntara.metrics.dependencies import get_metrics_recorder
from syntara.metrics.instrumentation import record_llm_call
from syntara.workflow_core.models import NodeType
from syntara.workflows.models.activity_execution import TERMINAL_ACTIVITY_STATUSES, ActivityExecution

logger = structlog.stdlib.get_logger(__name__)
_MAX_AGENT_TURNS = 32
_MAX_TOOL_TEXT = 10_000
_MAX_AGENT_PAYLOAD_ITEMS = 256
_MAX_TOOL_CALLS_PER_TURN = 16
_MAX_TOOL_ARGUMENT_BYTES = 8_192

if TYPE_CHECKING:
    from execution_plane_client.commands.base import CommandPayload
    from langchain_openai import ChatOpenAI

    from syntara.agent_orchestrator.services.orchestration_service import OrchestrationService
    from syntara.execution_plane.commands.context import AOCommandContext


class AgentOperationCommandHandler:
    """Authorize one operation against an active AO agent invocation."""

    async def handle(
        self, message: MessageEnvelope, payload: CommandPayload, context: AOCommandContext
    ) -> HandlingResult:
        """Run one model turn or selected MCP tool call in AO's control plane."""
        del message
        if not isinstance(payload, AgentOperation):
            raise ProtocolConflict
        invocation = await context.session.get(Invocation, payload.agent_invocation_id)
        activity = await context.session.get(ActivityExecution, payload.work_item_id)
        if invocation is None or activity is None:
            raise CommandResourceNotFoundError
        if (
            invocation.status is not InvocationStatus.RUNNING
            or activity.status in TERMINAL_ACTIVITY_STATUSES
            or activity.node_type != NodeType.AGENTIC
        ):
            raise CommandResourceStateError
        if not self._matches_active_invocation(payload, invocation):
            raise CommandResourceStateError
        if not re.fullmatch(rf"{re.escape(str(payload.work_item_id))}-\d+", payload.attempt_id):
            raise CommandResourceStateError
        if not get_settings().agent_runtime_enabled:
            raise CommandResourceStateError

        plugin = await get_execution_plane_plugin(context.session, "ao-task-agent")
        if (
            plugin is None
            or plugin.node_type is not NodeType.AGENTIC
            or not execution_plane_plugin_supports_revision(plugin, payload.step_revision_id)
        ):
            raise CommandResourceStateError

        request_context = InvocationContextData.model_validate(invocation.context_data or {})
        result = await self._resolve_operation(invocation, request_context, payload)
        logger.info(
            "Resolved AO Task Agent host operation",
            invocation_id=str(invocation.id),
            operation=payload.operation,
            request_id=payload.request_id,
        )
        return HandlingResult(
            resource=ResourceReference(kind="work_item", resource_id=payload.work_item_id),
            result=AgentOperationCommandResult(request_id=payload.request_id, result=result),
        )

    @staticmethod
    def _matches_active_invocation(payload: AgentOperation, invocation: Invocation) -> bool:
        """Require the EP work UUID to match the invocation's server-created activity context."""
        try:
            ctx = InvocationContextData.model_validate(invocation.context_data or {})
            execution_id = extract_execution_id(ctx)
            if execution_id is None or not ctx.activity_id:
                return False
            return execution_plane_work_item_id(execution_id, ctx.activity_id) == payload.work_item_id
        except (TypeError, ValueError, ValidationError):
            return False

    async def _resolve_operation(
        self, invocation: Invocation, ctx: InvocationContextData, payload: AgentOperation
    ) -> dict[str, Any]:
        """Create AO-owned model/tool clients, then resolve the requested operation."""
        executor = InvocationExecutor()
        initialized = await executor._init_orchestration(  # noqa: SLF001 -- reuse AO credential validation and provider setup.
            invocation, ctx
        )
        if initialized is None:
            raise CommandResourceStateError
        orchestration, llm_http_client = initialized
        try:
            execution_id = extract_execution_id(ctx)
            tools = await orchestration._get_tools(  # noqa: SLF001 -- reuse AO's existing MCP tool selection and auth.
                invocation.session_id,
                invocation.id,
                execution_id=execution_id,
                request_id=extract_request_id(ctx),
                activity_id=ctx.activity_id,
                activity_name=ctx.activity_name,
            )
            if payload.operation == "agent.model.turn":
                return await self._model_turn(orchestration.llm, tools, ctx, invocation, payload.payload)
            if payload.operation == "agent.mcp.call":
                return await self._mcp_call(orchestration, tools, invocation, ctx, payload.payload)
            raise CommandResourceStateError
        finally:
            if llm_http_client is not None:
                await llm_http_client.aclose()

    @staticmethod
    def _tool_definitions(tools: list[Any]) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, str]]:
        definitions: list[dict[str, Any]] = []
        by_id: dict[str, Any] = {}
        handle_by_name: dict[str, str] = {}
        for tool in tools:
            metadata = getattr(tool, "metadata", None) or {}
            tool_id = metadata.get("tool_id")
            if not isinstance(tool_id, str) or not tool_id:
                continue
            if tool.name in handle_by_name:
                raise CommandResourceStateError
            args_schema = getattr(tool, "args_schema", None)
            schema_factory = getattr(args_schema, "model_json_schema", None)
            if callable(schema_factory):
                schema = schema_factory()
            elif isinstance(args_schema, dict):
                schema = args_schema
            else:
                schema = {"type": "object", "properties": {}}
            definitions.append(
                {
                    "handle": tool_id,
                    "name": tool.name,
                    "description": tool.description or "",
                    "input_schema": schema,
                }
            )
            by_id[tool_id] = tool
            handle_by_name[tool.name] = tool_id
        return definitions, by_id, handle_by_name

    @classmethod
    async def _model_turn(  # noqa: C901, PLR0912, PLR0915 -- normalizes configured provider response formats.
        cls,
        llm: ChatOpenAI,
        tools: list[Any],
        ctx: InvocationContextData,
        invocation: Invocation,
        payload: dict[str, object],
    ) -> dict[str, Any]:
        """Call AO's configured provider once, binding only AO-discovered tools."""
        turn_index = payload.get("turn_index")
        mode = payload.get("mode", "standard")
        raw_messages = payload.get("messages")
        if type(turn_index) is not int or not 1 <= turn_index <= _MAX_AGENT_TURNS:
            raise CommandResourceStateError
        if not isinstance(mode, str) or mode not in {"standard", "structured_direct", "structured_extract"}:
            raise CommandResourceStateError
        if not isinstance(raw_messages, list) or not raw_messages or len(raw_messages) > _MAX_AGENT_PAYLOAD_ITEMS:
            raise CommandResourceStateError
        response_schema = (
            ctx.metadata.response_schema.get_data() if ctx.metadata and ctx.metadata.response_schema else None
        )
        if mode != "standard" and response_schema is None:
            raise CommandResourceStateError
        messages = cls._messages(raw_messages)
        if mode == "structured_direct":
            schema_prompt = (
                "You MUST respond with ONLY a valid JSON object matching this exact schema:\n\n"
                f"```json\n{json.dumps(response_schema, indent=2)}\n```\n\n"
                "Use exactly the property names from the schema. Do not include any text outside the JSON object."
            )
            messages.insert(0, SystemMessage(content=schema_prompt))
        supplied_tools = payload.get("tools", [])
        if not isinstance(supplied_tools, list) or len(supplied_tools) > _MAX_AGENT_PAYLOAD_ITEMS:
            raise CommandResourceStateError
        requested_handles: set[str] = set()
        for item in supplied_tools:
            if not isinstance(item, dict) or not isinstance(item.get("handle"), str):
                raise CommandResourceStateError
            requested_handles.add(item["handle"])
        selected_tools = [
            tool for tool in tools if (getattr(tool, "metadata", None) or {}).get("tool_id") in requested_handles
        ]
        selected_tools = annotate_tools_with_relevance(invocation.prompt, selected_tools)
        definitions, _by_id, handle_by_name = cls._tool_definitions(selected_tools)
        interaction_type = {
            "standard": LLMInteractionType.STANDARD,
            "structured_direct": LLMInteractionType.STRUCTURED_OUTPUT,
            "structured_extract": LLMInteractionType.EXTRACTION,
        }[mode]

        raw_result: object
        parsed_output: Any | None = None
        try:
            if mode == "standard":
                raw_result = await record_llm_call(
                    get_metrics_recorder(),
                    lambda: llm.bind_tools(selected_tools).ainvoke(messages),
                    model=getattr(llm, "model_name", None),
                )
                if len(getattr(raw_result, "tool_calls", []) or []) > _MAX_TOOL_CALLS_PER_TURN:
                    raise CommandResourceStateError  # noqa: TRY301 -- reject oversized provider tool batches.
            else:
                structured_llm = llm.with_structured_output(response_schema, method="json_mode", include_raw=True)
                structured_response = await record_llm_call(
                    get_metrics_recorder(),
                    lambda: structured_llm.ainvoke(messages),
                    model=getattr(llm, "model_name", None),
                )
                if not isinstance(structured_response, dict):
                    raise CommandResourceStateError  # noqa: TRY301 -- malformed provider output must fall back in structured mode.
                raw_result = structured_response.get("raw")
                parsed_output = structured_response.get("parsed")
                if not isinstance(raw_result, AIMessage):
                    raise CommandResourceStateError  # noqa: TRY301 -- malformed provider output must fall back in structured mode.
        except Exception as error:
            AuditEventDispatcher.dispatch(
                LLMInteractionEvent(
                    interaction_type=interaction_type,
                    status=LLMInteractionStatus.ERROR,
                    model_name=getattr(llm, "model_name", "unknown"),
                    session_id=invocation.session_id,
                    invocation_id=invocation.id,
                    execution_id=extract_execution_id(ctx),
                    request_id=extract_request_id(ctx),
                    tools_available=len(selected_tools),
                    response_schema_provided=response_schema is not None,
                    error_type=type(error).__name__,
                    activity_id=ctx.activity_id,
                    activity_name=ctx.activity_name,
                )
            )
            if mode != "standard":
                return {
                    "content": "",
                    "parsed_output": None,
                    "structured_output_metadata": {"fallback_strategy_used": "none"},
                    "usage": None,
                    "available_tools": len(definitions),
                }
            raise

        if not isinstance(raw_result, AIMessage):
            raise CommandResourceStateError
        if mode == "standard" and not raw_result.tool_calls and not str(raw_result.text or "").strip():
            AuditEventDispatcher.dispatch(
                LLMInteractionEvent(
                    interaction_type=interaction_type,
                    status=LLMInteractionStatus.EMPTY_RESPONSE,
                    model_name=getattr(llm, "model_name", "unknown"),
                    session_id=invocation.session_id,
                    invocation_id=invocation.id,
                    execution_id=extract_execution_id(ctx),
                    request_id=extract_request_id(ctx),
                    tools_available=len(selected_tools),
                    response_schema_provided=response_schema is not None,
                    error_type="EmptyLLMResponseError",
                    activity_id=ctx.activity_id,
                    activity_name=ctx.activity_name,
                )
            )
            raise CommandResourceStateError

        parse_failed = mode != "standard" and parsed_output is None
        AuditEventDispatcher.dispatch(
            LLMInteractionEvent(
                interaction_type=interaction_type,
                status=LLMInteractionStatus.ERROR if parse_failed else LLMInteractionStatus.SUCCESS,
                model_name=getattr(llm, "model_name", "unknown"),
                session_id=invocation.session_id,
                invocation_id=invocation.id,
                execution_id=extract_execution_id(ctx),
                request_id=extract_request_id(ctx),
                tools_available=len(selected_tools),
                tool_calls_made=len(getattr(raw_result, "tool_calls", []) or []),
                response_schema_provided=response_schema is not None,
                fallback_strategy_used="none" if parse_failed else ("native" if mode != "standard" else None),
                error_type="StructuredOutputParseError" if parse_failed else None,
                activity_id=ctx.activity_id,
                activity_name=ctx.activity_name,
            )
        )

        tool_calls: list[dict[str, Any]] = []
        wire_tool_calls: list[dict[str, Any]] = []
        for call in getattr(raw_result, "tool_calls", []) or []:
            name = call.get("name")
            arguments = call.get("args")
            call_id = call.get("id")
            handle = handle_by_name.get(name) if isinstance(name, str) else None
            if not isinstance(call_id, str) or not handle or not isinstance(arguments, dict):
                raise CommandResourceStateError
            if len(json.dumps(arguments, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > (
                _MAX_TOOL_ARGUMENT_BYTES
            ):
                raise CommandResourceStateError
            wire_tool_calls.append({"tool_call_id": call_id, "handle": handle, "name": name, "arguments": arguments})
            tool_calls.append({"id": call_id, "name": name, "args": arguments, "type": "tool_call"})
        content = str(getattr(raw_result, "text", "") or "")
        assistant_message = {"role": "assistant", "content": content, "tool_calls": tool_calls}
        token_entry = (
            GenericAgent._build_token_usage_entry(raw_result)  # noqa: SLF001 -- reuse AO's token usage normalization.
            if isinstance(raw_result, AIMessage)
            else None
        )
        return {
            "assistant_message": assistant_message,
            "tool_calls": wire_tool_calls,
            "content": content,
            "response_metadata": normalize_response_metadata(
                getattr(raw_result, "response_metadata", None),
                usage_metadata=getattr(raw_result, "usage_metadata", None),
            ),
            "parsed_output": parsed_output,
            "structured_output_metadata": (
                {"fallback_strategy_used": "native"} if parsed_output is not None and mode != "standard" else None
            ),
            "usage": token_entry,
            "available_tools": len(definitions),
        }

    @staticmethod
    def _messages(raw_messages: list[object]) -> list[Any]:  # noqa: C901 -- validates the agent callback's message protocol.
        """Convert the runtime's small message vocabulary to LangChain messages."""
        messages: list[Any] = []
        for raw in raw_messages:
            if not isinstance(raw, dict) or not isinstance(raw.get("role"), str):
                raise CommandResourceStateError
            role = raw["role"]
            content = raw.get("content", "")
            if isinstance(content, dict):
                content = json.dumps(content, ensure_ascii=False)
            elif not isinstance(content, str) and not (
                isinstance(content, list) and all(isinstance(item, (str, dict)) for item in content)
            ):
                raise CommandResourceStateError
            if isinstance(content, list):
                content = cast("list[str | dict[str, Any]]", content)
            if role == "system":
                messages.append(SystemMessage(content=content))
            elif role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                tool_calls = raw.get("tool_calls", [])
                if not isinstance(tool_calls, list):
                    raise CommandResourceStateError
                messages.append(AIMessage(content=content, tool_calls=tool_calls))
            elif role == "tool":
                call_id = raw.get("tool_call_id")
                name = raw.get("name")
                if not isinstance(call_id, str) or not isinstance(name, str):
                    raise CommandResourceStateError
                tool_status = "error" if raw.get("is_error") is True else "success"
                messages.append(ToolMessage(content=content, tool_call_id=call_id, name=name, status=tool_status))
            else:
                raise CommandResourceStateError
        return messages

    async def _mcp_call(
        self,
        orchestration: OrchestrationService,
        tools: list[Any],
        invocation: Invocation,
        ctx: InvocationContextData,
        payload: dict[str, object],
    ) -> dict[str, Any]:
        """Execute one AO-selected tool through the existing audited ToolNode."""
        handle = payload.get("handle")
        arguments = payload.get("arguments")
        call_id = payload.get("tool_call_id")
        turn_index = payload.get("turn_index")
        if (
            not isinstance(handle, str)
            or not isinstance(arguments, dict)
            or not isinstance(call_id, str)
            or not call_id
            or type(turn_index) is not int
            or not 1 <= turn_index <= _MAX_AGENT_TURNS
        ):
            raise CommandResourceStateError
        _definitions, by_id, _handle_by_name = self._tool_definitions(tools)
        tool = by_id.get(handle)
        if tool is None:
            raise CommandResourceStateError
        tool_node = orchestration._create_tool_node(  # noqa: SLF001 -- use AO's audited tool wrappers and persistence.
            [tool],
            invocation.session_id,
            invocation.id,
            execution_id=extract_execution_id(ctx),
            request_id=extract_request_id(ctx),
            activity_id=ctx.activity_id,
            activity_name=ctx.activity_name,
        )
        result = await tool_node.ainvoke(
            {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[{"name": tool.name, "args": arguments, "id": call_id, "type": "tool_call"}],
                    )
                ]
            },
            runtime=Runtime(),
        )
        result_messages = result.get("messages") if isinstance(result, dict) else None
        if (
            not isinstance(result_messages, list)
            or not result_messages
            or not isinstance(result_messages[-1], ToolMessage)
        ):
            raise CommandResourceStateError
        tool_message = result_messages[-1]
        content = (
            tool_message.content
            if isinstance(tool_message.content, str)
            else json.dumps(tool_message.content, ensure_ascii=False, default=str)
        )
        return {"content": content[:_MAX_TOOL_TEXT], "is_error": tool_message.status == "error"}
