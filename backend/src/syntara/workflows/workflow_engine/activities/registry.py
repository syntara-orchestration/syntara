"""Activity registries for Temporal worker configuration.

Defines ACTIVITY_REGISTRY (all activities for the main workflow worker) and
BACKGROUND_ACTIVITY_REGISTRY (minimal subset for the background queue worker).
"""

from collections.abc import Callable
from typing import Any

from syntara.workflows.workflow_engine.activities.aap_job_template_activity import execute_aap_job_template_activity
from syntara.workflows.workflow_engine.activities.aap_workflow_job_template_activity import (
    execute_aap_workflow_job_template_activity,
)
from syntara.workflows.workflow_engine.activities.agentic_activity import execute_agentic_activity
from syntara.workflows.workflow_engine.activities.approval_activity import (
    cancel_approval_requests_activity,
    create_approval_request_activity,
    expire_approval_requests_activity,
    fail_detached_approval_activity,
)
from syntara.workflows.workflow_engine.activities.approver_resolution_activity import resolve_approvers_activity
from syntara.workflows.workflow_engine.activities.condition import condition
from syntara.workflows.workflow_engine.activities.converge import converge
from syntara.workflows.workflow_engine.activities.credential_resolution_activity import resolve_workflow_credentials
from syntara.workflows.workflow_engine.activities.eda_trigger import eda_trigger
from syntara.workflows.workflow_engine.activities.http_request_activity import execute_http_request_activity
from syntara.workflows.workflow_engine.activities.integration_resolution_activity import resolve_workflow_integration
from syntara.workflows.workflow_engine.activities.integration_scope_activity import validate_node_references
from syntara.workflows.workflow_engine.activities.internal import register_activity_monitoring
from syntara.workflows.workflow_engine.activities.internal_activity import execute_internal_activity
from syntara.workflows.workflow_engine.activities.loop import loop
from syntara.workflows.workflow_engine.activities.manual_trigger import manual_trigger
from syntara.workflows.workflow_engine.activities.runtime_settings_activity import fetch_workflow_runtime_settings
from syntara.workflows.workflow_engine.activities.scheduled_trigger import scheduled_trigger
from syntara.workflows.workflow_engine.activities.script_activity import execute_script_activity
from syntara.workflows.workflow_engine.activities.switch import switch
from syntara.workflows.workflow_engine.activities.wait_activity import complete_wait, wait
from syntara.workflows.workflow_engine.activities.webhook_trigger import webhook_trigger
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName

_TEMPORAL_ACTIVITIES: list[Callable[..., Any]] = [
    register_activity_monitoring,
    fetch_workflow_runtime_settings,
    resolve_workflow_credentials,
    resolve_workflow_integration,
    validate_node_references,
    execute_aap_job_template_activity,
    execute_aap_workflow_job_template_activity,
    execute_agentic_activity,
    cancel_approval_requests_activity,
    create_approval_request_activity,
    expire_approval_requests_activity,
    fail_detached_approval_activity,
    resolve_approvers_activity,
    condition,
    converge,
    eda_trigger,
    switch,
    execute_http_request_activity,
    execute_internal_activity,
    loop,
    manual_trigger,
    scheduled_trigger,
    execute_script_activity,
    wait,
    complete_wait,
    webhook_trigger,
]

ACTIVITY_REGISTRY: dict[ActivityName, Callable[..., Any]] = {
    ActivityName(fn.__temporal_activity_definition.name): fn  # type: ignore[attr-defined]  # noqa: SLF001
    for fn in _TEMPORAL_ACTIVITIES
}

# Activities for built-in workflows only. Background worker runs a smaller
# footprint excluding user-facing executor activities. Both trigger types
# required: manual_trigger and scheduled_trigger.
_BACKGROUND_ACTIVITIES: list[Callable[..., Any]] = [
    register_activity_monitoring,
    fetch_workflow_runtime_settings,
    manual_trigger,
    scheduled_trigger,
    execute_internal_activity,
]

BACKGROUND_ACTIVITY_REGISTRY: dict[ActivityName, Callable[..., Any]] = {
    ActivityName(fn.__temporal_activity_definition.name): fn  # type: ignore[attr-defined]  # noqa: SLF001
    for fn in _BACKGROUND_ACTIVITIES
}
