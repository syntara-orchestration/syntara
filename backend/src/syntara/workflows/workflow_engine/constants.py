"""Workflow engine constants loaded from Pydantic settings.

Static infrastructure settings (URLs, UUIDs, cleanup timeouts) that are
not runtime-configurable. Activity timeouts and limits are runtime settings
in the Settings Catalog — see ``catalog.py``.
"""

from syntara.core.config.base import get_settings

# Clear cached settings so re-imports pick up any environment changes
get_settings.cache_clear()

# Load settings once at module import time
_settings = get_settings()

# Agentic activity infrastructure
AGENT_ORCHESTRATOR_BASE_URL = str(_settings.agent_orchestrator_base_url)
APPROVALS_API_BASE_URL = str(_settings.approvals_api_base_url)

# Script activity settings
SCRIPT_CLEANUP_TERMINATE_TIMEOUT = _settings.script_cleanup_terminate_timeout
SCRIPT_CLEANUP_KILL_TIMEOUT = _settings.script_cleanup_kill_timeout
MAX_ENV_VAR_LENGTH = _settings.max_env_var_length

# Temporal start-to-close safety ceiling used as a fallback until per-type
# catalog lookup is wired in the engine. 30s is sufficient for condition and
# switch nodes, which complete in milliseconds. Converge, loop, and all
# executor nodes use _get_default_timeout() for type-appropriate defaults.
DEFAULT_ACTIVITY_TIMEOUT_SECONDS = 30

# Timeout for the Agent Execution builtin workflow node.  Used by
# seed_builtin.py and as the cancel-key TTL in invocation_service.py.
AGENT_EXECUTION_TIMEOUT_SECONDS = 3600

# Temporal only delivers activity cancellation through heartbeats, and only to an
# activity that was scheduled with a heartbeat_timeout -- without one the server
# drops the beats and a cancelled workflow cannot interrupt a long-running
# activity. Internal activities beat on this interval; the schedule allows 3x
# that before Temporal declares the attempt dead. Ref: AAP-88614.
INTERNAL_ACTIVITY_HEARTBEAT_INTERVAL_SECONDS = 10.0
INTERNAL_ACTIVITY_HEARTBEAT_TIMEOUT_SECONDS = 30.0

# Key injected by the engine into each activity's input config so the activity
# can use the already-resolved timeout without re-querying the catalog.
# Must be popped by agentic_activity before forwarding config to the orchestrator.
ENGINE_TIMEOUT_SECONDS_KEY = "_engine_timeout_seconds"
ENGINE_MAX_OUTPUT_BYTES_KEY = "_engine_max_output_bytes"
DEFAULT_MAX_OUTPUT_BYTES = 1_048_576
# Temporal's server-side limit.blobSize.error (must match development-sql.yaml).
_TEMPORAL_BLOB_SIZE_ERROR = 2_097_152  # 2 MB
# 10% headroom covers JSON escaping expansion and protobuf envelope overhead.
TEMPORAL_PAYLOAD_MAX_BYTES = int(_TEMPORAL_BLOB_SIZE_ERROR * 0.9)

# ---------------------------------------------------------------------------
# Node-kind permissions (ANSTRAT-1750)
# ---------------------------------------------------------------------------
# These live here because the Temporal workflow sandbox needs them: importing
# them from syntara.workflows.node_launch_checks or node_kind_switch would drag
# the authz (regopy) and settings-cache stacks into the sandbox and break
# workflow validation.  The sandbox only ever needs the strings; the evaluator
# and the settings cache stay on the activity side.

NODE_EXECUTE_DENIED_ERROR_CODE = "node_execute_denied"
"""Stable error code on a node that was not executed because of a deny policy."""

PERMISSION_CHECK_ALLOWED_PORT = "allowed"
PERMISSION_CHECK_DENIED_PORT = "denied"
PERMISSION_CHECK_PORTS: frozenset[str] = frozenset({PERMISSION_CHECK_ALLOWED_PORT, PERMISSION_CHECK_DENIED_PORT})
"""Output ports of the ``permission_check`` node, mirroring ``condition``'s true/false."""

CHECK_NODE_KIND_ENABLED_ACTIVITY = "check_node_kind_enabled"
RECORD_NODE_EXECUTE_DENIED_ACTIVITY = "record_node_execute_denied"
RECOMPUTE_DENIED_NODES_ACTIVITY = "recompute_denied_nodes"
"""Names of the node-permission activities, dispatched by name from the sandbox."""
