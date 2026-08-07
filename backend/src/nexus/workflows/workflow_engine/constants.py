"""Workflow engine constants loaded from Pydantic settings.

Static infrastructure settings (URLs, UUIDs, cleanup timeouts) that are
not runtime-configurable. Activity timeouts and limits are runtime settings
in the Settings Catalog — see ``catalog.py``.
"""

from nexus.core.config.base import get_settings

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
