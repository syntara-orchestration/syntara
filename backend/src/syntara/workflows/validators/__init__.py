"""Workflow validation module.

This module provides validation for workflow definitions and metadata.
"""

from syntara.settings.cache.settings_cache import get_runtime_settings

from .workflow_definition import WorkflowValidator, collect_scheduled_trigger_config_findings
from .workflow_integrations import validate_workflow_references

# Convenience singleton instance for easy usage
workflow_validator = WorkflowValidator()


async def get_system_continue_on_failure() -> bool:
    """Fetch the admin-level continue_on_failure default from settings cache."""
    cache = get_runtime_settings()
    return await cache.get_bool("workflow_engine.continue_on_failure", default=False)


__all__ = [
    "WorkflowValidator",
    "collect_scheduled_trigger_config_findings",
    "get_system_continue_on_failure",
    "validate_workflow_references",
    "workflow_validator",
]
