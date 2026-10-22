"""Activity registries for Temporal worker configuration.

Defines ACTIVITY_REGISTRY (all activities for the main workflow worker) and
BACKGROUND_ACTIVITY_REGISTRY (minimal subset for the background queue worker).
"""

from collections.abc import Callable
from typing import Any

from syntara.workflow_core.models import ActivityName
from syntara.workflow_runtime.engines.temporal.activities.aap_job_template_activity import (
    execute_aap_job_template_activity,
)
from syntara.workflow_runtime.engines.temporal.activities.aap_workflow_job_template_activity import (
    execute_aap_workflow_job_template_activity,
)
from syntara.workflow_runtime.engines.temporal.activities.agentic_activity import (
    cancel_agentic_invocation_activity,
    execute_agentic_activity,
)
from syntara.workflow_runtime.engines.temporal.activities.approval_activity import (
    cancel_approval_requests_activity,
    create_approval_request_activity,
    expire_approval_requests_activity,
    fail_detached_approval_activity,
)
from syntara.workflow_runtime.engines.temporal.activities.approver_resolution_activity import resolve_approvers_activity
from syntara.workflow_runtime.engines.temporal.activities.condition import condition
from syntara.workflow_runtime.engines.temporal.activities.converge import converge
from syntara.workflow_runtime.engines.temporal.activities.credential_resolution_activity import (
    resolve_workflow_credentials,
)
from syntara.workflow_runtime.engines.temporal.activities.eda_trigger import eda_trigger
from syntara.workflow_runtime.engines.temporal.activities.http_request_activity import execute_http_request_activity
from syntara.workflow_runtime.engines.temporal.activities.integration_resolution_activity import (
    resolve_workflow_integration,
)
from syntara.workflow_runtime.engines.temporal.activities.integration_scope_activity import validate_node_references
from syntara.workflow_runtime.engines.temporal.activities.internal import register_activity_monitoring
from syntara.workflow_runtime.engines.temporal.activities.internal_activity import execute_internal_activity
from syntara.workflow_runtime.engines.temporal.activities.loop import loop
from syntara.workflow_runtime.engines.temporal.activities.manual_trigger import manual_trigger
from syntara.workflow_runtime.engines.temporal.activities.runtime_settings_activity import (
    fetch_workflow_runtime_settings,
)
from syntara.workflow_runtime.engines.temporal.activities.scheduled_trigger import scheduled_trigger
from syntara.workflow_runtime.engines.temporal.activities.script_activity import execute_script_activity
from syntara.workflow_runtime.engines.temporal.activities.switch import switch
from syntara.workflow_runtime.engines.temporal.activities.wait_activity import complete_wait, wait
from syntara.workflow_runtime.engines.temporal.activities.webhook_trigger import webhook_trigger

_TEMPORAL_ACTIVITIES: list[Callable[..., Any]] = [
    register_activity_monitoring,
    fetch_workflow_runtime_settings,
    resolve_workflow_credentials,
    resolve_workflow_integration,
    validate_node_references,
    execute_aap_job_template_activity,
    execute_aap_workflow_job_template_activity,
    execute_agentic_activity,
    cancel_agentic_invocation_activity,
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
