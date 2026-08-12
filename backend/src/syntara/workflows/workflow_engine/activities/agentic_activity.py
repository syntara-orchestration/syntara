"""Agentic activity executor for workflow integration with Agent Orchestrator.

This module provides functionality to execute agentic activities within workflows,
integrating with the Agent Orchestrator service for AI-driven task execution.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from pydantic import ValidationError
from temporalio import activity, workflow
from temporalio.exceptions import ApplicationError, CancelledError

from syntara.settings.cache.settings_cache import get_runtime_settings
from syntara.workflows.workflow_engine import constants
from syntara.workflows.workflow_engine.models import AgenticExecutorParameters
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName
from syntara.workflows.workflow_engine.utils.credential_scrubber import ensure_resolved_credentials_dict

from .common import HEARTBEAT_PARTIAL_OUTPUT_KEY, HEARTBEAT_STOP_MONITOR, ActivityExecutionError

# See - https://github.com/temporalio/sdk-python?tab=readme-ov-file#avoiding-the-sandbox for more detail
with workflow.unsafe.imports_passed_through():
    from syntara.core.config.base import get_settings
    from syntara.core.models.principal import service_principal_id
    from syntara.workflows.clients.agent_orchestrator_client import (
        AgentOrchestratorClient,
        AgentOrchestratorClientConnectionError,
    )
    from syntara.workflows.utils.url import generate_activity_signal_url


logger = structlog.stdlib.get_logger(__name__)


# ============================================================================
# Exceptions
# ============================================================================


class AgenticActivityError(ActivityExecutionError):
    """Base exception for agentic activity errors."""


# ============================================================================
# Temporal Activity
# ============================================================================


async def _inject_runtime_settings(input_config: dict[str, Any]) -> None:
    """Inject live runtime settings into agentic activity config.

    Raises:
        ValueError: If the prompt exceeds the configured max length.

    """
    # Pop the engine-injected timeout so it isn't forwarded to the orchestrator.
    engine_timeout = int(input_config.pop(constants.ENGINE_TIMEOUT_SECONDS_KEY, 300))
    if "timeout" not in input_config:
        input_config["timeout"] = engine_timeout

    cache = get_runtime_settings()
    prompt = input_config.get("prompt", "")
    if isinstance(prompt, str):
        max_len = await cache.get_int("workflow_engine.max_prompt_length", default=100000)
        if len(prompt) > max_len:
            msg = f"Prompt exceeds maximum length ({len(prompt)} > {max_len} characters)"
            raise ValueError(msg)


def _build_agent_metadata(
    config: AgenticExecutorParameters,
    input_config: dict[str, Any],
    *,
    workflow_id: str | None,
    activity_id: str,
    execution_id: str,
    callback_url: str,
    request_id: str | None,
) -> dict[str, Any]:
    """Build the metadata dict passed to the agent orchestrator."""
    agent_metadata: dict[str, Any] = {
        "workflow_id": workflow_id,
        "activity_id": activity_id,
        "activity_name": "agentic_v2",
        "execution_id": execution_id,
    }
    if callback_url:
        agent_metadata["callback_url"] = callback_url
    if request_id:
        agent_metadata["request_id"] = request_id

    _inject_llm_credential_metadata(agent_metadata, input_config)
    if config.llm_model_id:
        agent_metadata["llm_model_id"] = config.llm_model_id

    if config.integration_connections:
        agent_metadata["integration_connections"] = [c.model_dump() for c in config.integration_connections]

    if config.tool_selection_strategy:
        agent_metadata["tool_selection_strategy"] = config.tool_selection_strategy
    if config.tool_selections:
        agent_metadata["tool_selections"] = config.tool_selections

    if config.response_schema:
        agent_metadata["response_schema"] = config.response_schema

    return agent_metadata


@activity.defn(name=ActivityName.AGENTIC)
async def execute_agentic_activity(  # noqa: PLR0915
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,  # noqa: ARG001  # must match Temporal dispatch signature; agentic completes async via callback, not via return value
    execution_id: str = "",
    request_id: str | None = None,
    project_id: str = "",
    created_by_user_id: str = "",
) -> dict[str, Any]:
    """V2 agentic activity with async completion.

    On successful dispatch, calls raise_complete_async() so the activity stays
    STARTED in Temporal until the agent orchestrator calls back with results.
    Pre-dispatch failures return synchronously to avoid retry-induced duplicates.

    Args:
        input_config: Activity configuration containing prompt, agent, model, etc.
        output_config: Output mapping configuration
        execution_id: Workflow execution ID for callback URL generation
        request_id: Optional X-Request-Id (UUID) from the originating HTTP request
        project_id: Project ID to associate the invocation with (required)
        created_by_user_id: UUID of the user who started the workflow (for created_by attribution)

    """
    logger.info("Starting agentic activity (v2)")
    activity.heartbeat({HEARTBEAT_STOP_MONITOR: True})

    try:
        try:
            await _inject_runtime_settings(input_config)
        except ValueError as e:
            logger.warning("Agentic activity runtime settings validation failed", error=str(e))
            msg = "Runtime settings validation failed"
            raise ApplicationError(msg, type="ConfigError", non_retryable=True) from None

        config = AgenticExecutorParameters.model_validate(input_config)

        if not config.prompt.strip():
            msg = "Agentic activity requires non-empty 'prompt' field"
            raise ApplicationError(msg, type="ConfigError", non_retryable=True)  # noqa: TRY301

        if not project_id:
            msg = "Agentic activity requires non-empty 'project_id'"
            raise ApplicationError(msg, type="ConfigError", non_retryable=True)  # noqa: TRY301

        file_ids = config.file_ids or []

        try:
            activity_info = activity.info()
            workflow_id = activity_info.workflow_id
            activity_id = activity_info.activity_id
        except RuntimeError:
            workflow_id = "direct-invocation"
            activity_id = "unknown"

        settings = get_settings()
        user_id = created_by_user_id or str(service_principal_id(settings.service_identity))
        callback_url = generate_activity_signal_url(UUID(execution_id), activity_id) if execution_id else ""

        logger.info(
            "Invoking Agent Orchestrator",
            user_id=user_id,
            agent=config.agent,
            file_count=len(file_ids),
        )

        agent_metadata = _build_agent_metadata(
            config,
            input_config,
            workflow_id=workflow_id,
            activity_id=activity_id,
            execution_id=execution_id,
            callback_url=callback_url,
            request_id=request_id,
        )

        async with AgentOrchestratorClient(
            base_url=constants.AGENT_ORCHESTRATOR_BASE_URL,
            on_behalf_of_user_id=user_id,
        ) as agent_client:
            invocation_id = await agent_client.invoke_agent_async(
                prompt=config.prompt,
                user_id=user_id,
                agent=config.agent,
                input_data={},
                file_ids=file_ids,
                metadata=agent_metadata,
                project_id=project_id,
            )

            logger.info(
                "Agent invocation created successfully",
                invocation_id=invocation_id,
            )

            activity.heartbeat(
                {
                    HEARTBEAT_STOP_MONITOR: True,
                    HEARTBEAT_PARTIAL_OUTPUT_KEY: {"invocation_id": str(invocation_id)},
                }
            )

            activity.raise_complete_async()

    # All pre-invocation failures raise ApplicationError(non_retryable=True).
    # raise_complete_async() raises BaseException (not caught by Exception handlers below),
    # so these handlers only fire on genuine pre-invocation failures.
    except (ApplicationError, CancelledError):
        raise
    except ValidationError as e:
        logger.warning("Agentic activity config validation failed", error_count=e.error_count())
        fields = [str(err["loc"]) for err in e.errors()]
        msg = f"Invalid configuration: {e.error_count()} error(s) in fields {fields}"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True) from None
    except AgentOrchestratorClientConnectionError:
        logger.exception("Failed to connect to Agent Orchestrator")
        msg = "Failed to connect to Agent Orchestrator"
        raise ApplicationError(msg, type="ConnectionError", non_retryable=True) from None
    except Exception as e:
        logger.exception("Unexpected error during agentic activity")
        msg = "Unexpected error during agentic activity"
        raise ApplicationError(msg, type=type(e).__name__, non_retryable=True) from None


def _inject_llm_credential_metadata(metadata: dict[str, Any], input_data: dict[str, Any]) -> None:
    """Inject LLM credential reference into agent metadata from resolved credentials.

    Passes only ``credential_id`` for deferred resolution at execution time.
    The decrypted API key and all non-secret LLM metadata are omitted from
    invocation context_data.

    Args:
        metadata: Mutable agent metadata dict to update.
        input_data: Activity input data potentially containing _resolved_credentials.

    """
    resolved_creds = input_data.get("_resolved_credentials")
    if not resolved_creds:
        return
    resolved_creds = ensure_resolved_credentials_dict(resolved_creds)
    # Pass credential_id for deferred resolution — NOT the decrypted key
    cred_id = resolved_creds.get("credential_id")
    if cred_id:
        metadata["credential_id"] = cred_id
