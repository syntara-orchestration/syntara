"""Workflow validation module.

This module provides validation for workflow definitions and metadata.
"""

from .workflow_definition import WorkflowValidator, collect_scheduled_trigger_config_findings
from .workflow_integrations import validate_workflow_references

# Convenience singleton instance for easy usage
workflow_validator = WorkflowValidator()

__all__ = [
    "WorkflowValidator",
    "collect_scheduled_trigger_config_findings",
    "validate_workflow_references",
    "workflow_validator",
]
