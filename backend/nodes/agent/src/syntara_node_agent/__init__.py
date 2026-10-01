"""SDK adapter for the existing Agent Orchestrator HTTP API."""

from __future__ import annotations

import asyncio
import ssl
from typing import Any
from uuid import UUID, uuid4

import httpx
from pydantic import Field
from sqlmodel import SQLModel
from syntara_node_runtime.models import AgenticExecutorParameters
from syntara_node_runtime.runtime import NodeFailure, RuntimeContext, run_async
from syntara_sdk import ExecutionContext, TaskNode


class AgentInput(SQLModel):
    """Execute parameters are validated separately from cancellation inputs."""

    prompt: str | None = None
    invocation_id: str | None = None
    invocation_ids: list[str] = Field(default_factory=list)
    reason: str = "Workflow cancelled"


class AgentOutput(SQLModel):
    """Acknowledgement; final workflow output arrives through the callback."""

    invocation_id: str
    cancelled: bool = False


def build_payload(config: AgenticExecutorParameters, context: RuntimeContext) -> dict[str, Any]:
    """Preserve the Agent Orchestrator invocation request shape."""
    ctx = context.invocation.workflow_context
    metadata = dict(ctx.get("agent_metadata", {}))
    context_data = {
        key: metadata.pop(key)
        for key in ("workflow_id", "activity_id", "activity_name", "execution_id", "callback_url")
        if key in metadata
    }
    context_data.update(
        input_data={},
        file_ids=config.file_ids or [],
        agent=config.agent,
        timeout_seconds=context.invocation.timeout_seconds,
        metadata=metadata or None,
    )
    return {
        "prompt": config.prompt,
        "createdBy": ctx["created_by_user_id"],
        "sessionId": str(uuid4()),
        "projectId": ctx["project_id"],
        "contextData": {k: v for k, v in context_data.items() if v is not None},
    }


def tls_context(context: RuntimeContext) -> bool | ssl.SSLContext:
    """Load the agent service identity from its mounted secret."""
    if not context.invocation.workflow_context.get("agent_tls_enabled", True):
        return True
    result = ssl.create_default_context(cafile="/run/agent-tls/ca.pem")
    result.minimum_version = ssl.TLSVersion.TLSv1_3
    result.load_cert_chain("/run/agent-tls/tls.crt", "/run/agent-tls/tls.key")
    return result


class Node(TaskNode[AgentInput, AgentOutput]):
    """Create or cancel an invocation; model/tool execution remains in AO."""

    def __init__(self) -> None:
        """Initialize the node contract and execution state."""
        super().__init__(AgentInput, AgentOutput)

    def run(self, inputs: AgentInput, context: ExecutionContext) -> AgentOutput:
        """Execute validated inputs using the portable runtime."""
        if not isinstance(context, RuntimeContext):
            message = "Use the container runner with a RuntimeContext"
            raise TypeError(message)

        async def invoke() -> dict[str, Any]:
            """Provide the invoke operation."""
            ctx = context.invocation.workflow_context
            headers = {"X-On-Behalf-Of": ctx["created_by_user_id"]} if ctx.get("created_by_user_id") else {}
            async with httpx.AsyncClient(
                verify=tls_context(context), headers=headers, timeout=30, trust_env=False
            ) as client:
                base = ctx["agent_base_url"].rstrip("/")
                try:
                    if context.invocation.operation == "cancel":
                        identifiers = inputs.invocation_ids or [inputs.invocation_id or ""]
                        ids = [str(UUID(value)) for value in identifiers]

                        async def cancel_one(invocation_id: str) -> None:
                            response = await client.post(
                                f"{base}/invocations/{invocation_id}/cancel", json={"reason": inputs.reason}
                            )
                            response.raise_for_status()

                        await asyncio.gather(*(cancel_one(value) for value in ids))
                        return {"invocation_id": ids[0], "cancelled": True}
                    config = AgenticExecutorParameters.model_validate(context.invocation.inputs)
                    if not config.prompt.strip():
                        message = "Agent prompt is empty"
                        raise NodeFailure(message, type="ConfigError")
                    response = await client.post(f"{base}/invocations", json=build_payload(config, context))
                    response.raise_for_status()
                    invocation_id = str(UUID(response.json()["id"]))
                    context.emit(
                        "heartbeat", {"stop_monitor": True, "partial_output": {"invocation_id": invocation_id}}
                    )
                    return {"invocation_id": invocation_id}
                except httpx.HTTPError:
                    # A POST may have succeeded despite a lost response. Never retry it here.
                    message = "Agent Orchestrator request failed"
                    raise NodeFailure(message, type="ConnectionError") from None

        return AgentOutput.model_validate(run_async(invoke, context))
