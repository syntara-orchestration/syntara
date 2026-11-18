"""Activity for fetching workflow engine runtime settings at execution start."""

import asyncio
from typing import Any

from temporalio import activity

from syntara.core.config.base import get_settings
from syntara.settings.cache.settings_cache import get_runtime_settings
from syntara.settings.catalog import SETTINGS_CATALOG
from syntara.workflow_core.models import ActivityName
from syntara.workflow_runtime.engines.temporal.execution_plane_policy import (
    EP_POLICY_SNAPSHOT_KEY,
)

_WORKFLOW_ENGINE_KEYS: list[str] = [entry.key for entry in SETTINGS_CATALOG if entry.key.startswith("workflow_engine.")]


@activity.defn(name=ActivityName.FETCH_RUNTIME_SETTINGS)
async def fetch_workflow_runtime_settings() -> dict[str, Any]:
    """Fetch workflow defaults and snapshot the separate EP infrastructure policy.

    Called once at the start of every workflow execution so the workflow
    can use live operator-configured values (timeouts, continue_on_failure,
    retry policy) without hardcoding catalog mirrors.

    Returns:
        Workflow catalog values plus an EP policy snapshot recorded in history.

    """
    cache = get_runtime_settings()
    values = await asyncio.gather(*[cache.get(key) for key in _WORKFLOW_ENGINE_KEYS])
    snapshot = {key: value for key, value in zip(_WORKFLOW_ENGINE_KEYS, values, strict=True) if value is not None}
    settings = get_settings()
    snapshot[EP_POLICY_SNAPSHOT_KEY] = {
        "ep_dispatch_max_retries": settings.ep_dispatch_max_retries,
        "ep_dispatch_initial_backoff_seconds": settings.ep_dispatch_initial_backoff_seconds,
        "ep_dispatch_max_backoff_seconds": settings.ep_dispatch_max_backoff_seconds,
        "ep_work_timeout_seconds": settings.ep_work_timeout_seconds,
    }
    return snapshot
