"""Workflow models package.

This package contains database models (SQLModel tables):
- Workflow: Workflow database model
- WorkflowVersion: WorkflowVersion database model
- Execution: Execution database model
- ActivityExecution: ActivityExecution database model
- WebhookTrigger: WebhookTrigger database model

And API request/response models (Pydantic):
- ActivitySignalPayload: Signal payload for activity signals
- SignalResponse: Response for signal operations

And WebSocket streaming models (Pydantic):
- ActivityData: Activity data for visualization messages
- JsonPatchOperation: JSON Patch operation for incremental updates
- ExecutionSnapshotMessage: Full execution snapshot message
- ActivityPatchMessage: Incremental activity update message

Usage:
    from syntara.workflows.models import Workflow, WorkflowVersion, Execution, ActivityExecution, WebhookTrigger
    from syntara.workflows.models import ActivitySignalPayload, SignalResponse
    from syntara.workflows.models import ActivityData, ExecutionSnapshotMessage, ActivityPatchMessage
"""

from .activity_execution import ActivityExecution, ActivityExecutionListResponse, ActivityStatus
from .execution import (
    TERMINAL_EXECUTION_STATUSES,
    ActivityData,
    Execution,
    ExecutionInclude,
    ExecutionListResponse,
    ExecutionStatus,
)
from .query_params import (
    ActivityListParams,
    ExecutionIncludeParams,
    ExecutionListParams,
    ExecutionStreamingQueryParams,
    WorkflowListParams,
    WorkflowVersionListParams,
)
from .signal import ActivitySignalPayload, SignalResponse
from .validation_finding import (
    DetailedValidationProblemDetail,
    ValidationCategory,
    ValidationFinding,
    ValidationResult,
    ValidationSeverity,
)
from .visualization import (
    ActivityPatchMessage,
    ExecutionSnapshotMessage,
    JsonPatchOperation,
)
from .webhook_trigger import WebhookTrigger, WebhookTriggerRead
from .webhook_trigger_service_account import WebhookTriggerServiceAccount
from .workflow import (
    PublishWorkflowVersionResponse,
    Workflow,
    WorkflowCreate,
    WorkflowListResponse,
    WorkflowRead,
    WorkflowReadWithVersion,
    WorkflowUpdate,
)
from .workflow_definition import WorkflowDefinition
from .workflow_publish_event import PublishAction, WorkflowPublishEvent
from .workflow_validation_result import (
    WorkflowValidateRequest,
)
from .workflow_version import (
    PublishVersionRequest,
    WorkflowVersion,
    WorkflowVersionListResponse,
    WorkflowVersionRead,
    WorkflowVersionUpdate,
)

__all__ = [
    "TERMINAL_EXECUTION_STATUSES",
    "ActivityData",
    "ActivityExecution",
    "ActivityExecutionListResponse",
    "ActivityListParams",
    "ActivityPatchMessage",
    "ActivitySignalPayload",
    "ActivityStatus",
    "DetailedValidationProblemDetail",
    "Execution",
    "ExecutionInclude",
    "ExecutionIncludeParams",
    "ExecutionListParams",
    "ExecutionListResponse",
    "ExecutionSnapshotMessage",
    "ExecutionStatus",
    "ExecutionStreamingQueryParams",
    "JsonPatchOperation",
    "PublishAction",
    "PublishVersionRequest",
    "PublishWorkflowVersionResponse",
    "SignalResponse",
    "ValidationCategory",
    "ValidationFinding",
    "ValidationResult",
    "ValidationSeverity",
    "WebhookTrigger",
    "WebhookTriggerRead",
    "WebhookTriggerServiceAccount",
    "Workflow",
    "WorkflowCreate",
    "WorkflowDefinition",
    "WorkflowListParams",
    "WorkflowListResponse",
    "WorkflowPublishEvent",
    "WorkflowRead",
    "WorkflowReadWithVersion",
    "WorkflowUpdate",
    "WorkflowValidateRequest",
    "WorkflowVersion",
    "WorkflowVersionListParams",
    "WorkflowVersionListResponse",
    "WorkflowVersionRead",
    "WorkflowVersionUpdate",
]
