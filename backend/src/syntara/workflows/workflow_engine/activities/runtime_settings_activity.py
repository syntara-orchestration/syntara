"""Activity for fetching workflow engine runtime settings at execution start."""

import asyncio
from typing import Any

from temporalio import activity

from syntara.settings.cache.settings_cache import get_runtime_settings
from syntara.settings.catalog import SETTINGS_CATALOG
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName

_WORKFLOW_ENGINE_KEYS: list[str] = [entry.key for entry in SETTINGS_CATALOG if entry.key.startswith("workflow_engine.")]


@activity.defn(name=ActivityName.FETCH_RUNTIME_SETTINGS)
async def fetch_workflow_runtime_settings() -> dict[str, Any]:
    """Fetch all workflow_engine.* runtime settings as a flat dict.

    Called once at the start of every workflow execution so the workflow
    can use live operator-configured values (timeouts, continue_on_failure,
    retry policy) without hardcoding catalog mirrors.

    Returns:
        Flat dict of all workflow_engine.* setting key-value pairs.

    """
    cache = get_runtime_settings()
    values = await asyncio.gather(*[cache.get(key) for key in _WORKFLOW_ENGINE_KEYS])
    return {key: value for key, value in zip(_WORKFLOW_ENGINE_KEYS, values, strict=True) if value is not None}
