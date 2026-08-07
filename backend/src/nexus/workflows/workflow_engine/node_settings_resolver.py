"""Pure functions for resolving per-node execution settings.

Merges node-level settings (node.settings.*) with global operator-configured
defaults (runtime_settings fetched at workflow start) to produce concrete
values the engine uses for activity dispatch.
"""

from datetime import timedelta
from typing import Any

from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

from nexus.workflows.workflow_engine.constants import DEFAULT_ACTIVITY_TIMEOUT_SECONDS, DEFAULT_MAX_OUTPUT_BYTES
from nexus.workflows.workflow_engine.graph import ActivityNode
from nexus.workflows.workflow_engine.models.workflow_definition import (
    NodeSettingsCof,
    NodeSettingsFull,
    NodeSettingsNoRetry,
    NodeType,
)

# Maps executor node type to its catalog setting key for timeout.
# Approval and converge are excluded — they use dedicated parameters fields
# (decision_window and wait_duration) resolved by their own functions below.
_TIMEOUT_CATALOG_KEYS: dict[str, str] = {
    NodeType.SCRIPT: "workflow_engine.script_timeout_seconds",
    NodeType.HTTP_REQUEST: "workflow_engine.http_request_timeout_seconds",
    NodeType.AAP_JOB_TEMPLATE: "workflow_engine.aap_timeout_seconds",
    NodeType.AAP_WORKFLOW_JOB_TEMPLATE: "workflow_engine.aap_timeout_seconds",
    NodeType.AGENTIC: "workflow_engine.agentic_timeout_seconds",
}

_MAX_OUTPUT_CATALOG_KEYS: dict[str, str] = {
    NodeType.SCRIPT: "workflow_engine.script_max_output_kb",
}

_BYTES_PER_KB = 1024


def _require_int(node_id: str, field: str, value: Any) -> int:  # noqa: ANN401
    """Parse an integer value, raising a non-retryable ConfigError on bad input."""
    try:
        return int(value)
    except (ValueError, TypeError):
        msg = f"Node {node_id}: parameters field '{field}' must be an integer, got {value!r}"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True) from None


def resolve_max_iterations(node: ActivityNode, runtime_settings: dict[str, Any]) -> int:
    """Return the maximum iteration count for a loop node.

    Resolution: node.parameters.max_iterations → workflow_engine.max_loop_iterations catalog value.
    """
    node_value = node.parameters.get("max_iterations")
    if node_value is not None:
        return _require_int(node.id, "max_iterations", node_value)
    return int(runtime_settings.get("workflow_engine.max_loop_iterations", 10000))


def resolve_decision_window(node: ActivityNode, runtime_settings: dict[str, Any]) -> int:
    """Return the decision window (seconds) for an approval node.

    Resolution: node.parameters.decision_window → workflow_engine.approval_decision_window_seconds catalog value.
    """
    node_value = node.parameters.get("decision_window")
    if node_value is not None:
        return _require_int(node.id, "decision_window", node_value)
    return int(runtime_settings.get("workflow_engine.approval_decision_window_seconds", 86400))


def resolve_wait_duration(node: ActivityNode, runtime_settings: dict[str, Any]) -> int:
    """Return the branch wait duration (seconds) for a converge node.

    Resolution: node.parameters.wait_duration → workflow_engine.converge_wait_duration_seconds catalog value.
    """
    node_value = node.parameters.get("wait_duration")
    if node_value is not None:
        return _require_int(node.id, "wait_duration", node_value)
    return int(runtime_settings.get("workflow_engine.converge_wait_duration_seconds", 86400))


def get_default_timeout(node_type: str, runtime_settings: dict[str, Any]) -> int:
    """Return the effective default timeout (seconds) for a node type.

    Resolution: catalog key from runtime_settings → DEFAULT_ACTIVITY_TIMEOUT_SECONDS.
    """
    key = _TIMEOUT_CATALOG_KEYS.get(node_type)
    if key:
        value = runtime_settings.get(key)
        if value is not None:
            return int(value)
    return DEFAULT_ACTIVITY_TIMEOUT_SECONDS


def resolve_timeout(node: ActivityNode, runtime_settings: dict[str, Any]) -> int:
    """Return the timeout (seconds) for a node.

    Resolution: node.settings.timeout → catalog global → DEFAULT_ACTIVITY_TIMEOUT_SECONDS.
    """
    if isinstance(node.settings, NodeSettingsNoRetry) and node.settings.timeout is not None:
        return node.settings.timeout
    return get_default_timeout(node.type, runtime_settings)


def resolve_max_output_bytes(node: ActivityNode, runtime_settings: dict[str, Any]) -> int:
    """Return the max output bytes for a node.

    The catalog setting is in KB; this returns bytes.
    Resolution: catalog global (KB → bytes) → DEFAULT_MAX_OUTPUT_BYTES.
    """
    key = _MAX_OUTPUT_CATALOG_KEYS.get(node.type)
    if key:
        value = runtime_settings.get(key)
        if value is not None:
            return int(value) * _BYTES_PER_KB
    return DEFAULT_MAX_OUTPUT_BYTES


def resolve_continue_on_failure(node: ActivityNode, runtime_settings: dict[str, Any]) -> bool:
    """Return whether downstream nodes should continue after this node fails.

    Resolution: node.settings.continue_on_failure → global catalog default → False.
    """
    if isinstance(node.settings, NodeSettingsCof) and node.settings.continue_on_failure is not None:
        return node.settings.continue_on_failure
    return bool(runtime_settings.get("workflow_engine.continue_on_failure", False))


def resolve_retry_policy(
    node: ActivityNode,
    runtime_settings: dict[str, Any],
) -> RetryPolicy | None:
    """Return the Temporal RetryPolicy for a node.

    Returns a single-attempt policy for node types that should never retry
    (Temporal's default is unlimited retries when no policy is provided).
    Resolution: node.settings.retry_policy fields → global catalog defaults → single attempt.
    """
    if not isinstance(node.settings, NodeSettingsFull):
        return RetryPolicy(maximum_attempts=1)

    cfg = node.settings.retry_policy

    max_retries = (
        cfg.max_retries
        if cfg is not None and cfg.max_retries is not None
        else runtime_settings.get("workflow_engine.retry_max_retries", 3)
    )

    if max_retries is None:
        return None

    initial_interval = (
        cfg.initial_interval
        if cfg is not None and cfg.initial_interval is not None
        else runtime_settings.get("workflow_engine.retry_initial_interval", 1)
    )
    max_interval = (
        cfg.max_interval
        if cfg is not None and cfg.max_interval is not None
        else runtime_settings.get("workflow_engine.retry_max_interval", 60)
    )
    backoff_coefficient = (
        cfg.backoff_coefficient
        if cfg is not None and cfg.backoff_coefficient is not None
        else runtime_settings.get("workflow_engine.retry_backoff_coefficient", 2.0)
    )

    return RetryPolicy(
        maximum_attempts=max_retries + 1,  # Temporal counts initial attempt
        initial_interval=timedelta(seconds=int(initial_interval)),
        maximum_interval=timedelta(seconds=int(max_interval)),
        backoff_coefficient=float(backoff_coefficient),
    )
