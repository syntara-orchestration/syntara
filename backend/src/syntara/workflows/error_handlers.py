"""RFC 9457 compliant error handlers for Workflows domain.

This module provides error handling for workflow and execution-specific exceptions.
"""

from typing import TYPE_CHECKING

import structlog
from fastapi import Request, status
from fastapi.responses import JSONResponse
from temporalio.service import RPCError

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.core.error_handlers import PROBLEM_TYPES, create_problem_details_response
from syntara.workflows.audit.webhook_auth import WebhookAuthFailureEvent
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType

if TYPE_CHECKING:
    from syntara.workflows.exceptions import (
        BuiltinWorkflowDeleteError,
        BuiltinWorkflowMissingError,
        BuiltinWorkflowModifyError,
        ExecutionInTerminalStateError,
        ExecutionNotFoundError,
        ExecutionNotRetryableError,
        PayloadTooLargeError,
        ScheduledTriggerNotFoundError,
        ScheduledTriggerSyncError,
        TemporalUnavailableError,
        TriggerValidationError,
        WebhookAuthenticationRequiredError,
        WebhookServiceAccountNotAuthorizedError,
        WebhookTriggerNotFoundError,
        WebhookTriggerPathConflictError,
        WorkflowConcurrencyLimitError,
        WorkflowDefinitionInvalidError,
        WorkflowNameConflictError,
        WorkflowNotFoundError,
        WorkflowNotPublishedError,
        WorkflowPublishValidationError,
        WorkflowValidationError,
        WorkflowVersionConflictError,
        WorkflowVersionNotFoundError,
    )
    from syntara.workflows.models.validation_finding import ValidationResult

logger = structlog.stdlib.get_logger(__name__)

_PROBLEM_JSON_MEDIA_TYPE = "application/problem+json"


def build_validation_problem_response(
    request: Request,
    result: "ValidationResult",
) -> JSONResponse:
    """Build an RFC 9457 problem details response for workflow validation failures."""
    content = {
        "type": PROBLEM_TYPES["validation_error"],
        "title": "Workflow Definition Invalid",
        "detail": "The workflow definition failed validation",
        "code": "WORKFLOW_DEFINITION_INVALID",
        "retryable": False,
        "instance": str(request.url),
        "validation_result": result.model_dump(mode="json"),
    }
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=content,
        media_type=_PROBLEM_JSON_MEDIA_TYPE,
    )


def publish_validation_handler(request: Request, exc: "WorkflowPublishValidationError") -> JSONResponse:
    """Return RFC 9457 problem details when publishing is blocked due to validation issues."""
    logger.warning("Workflow publish blocked due to validation issues", exc_info=exc)
    content = {
        "type": PROBLEM_TYPES["publish_validation"],
        "title": "Workflow Publish Blocked",
        "detail": "Cannot publish a workflow version with validation errors or warnings",
        "code": "WORKFLOW_PUBLISH_VALIDATION_ERROR",
        "retryable": False,
        "instance": str(request.url),
        "validation_result": exc.validation_result.model_dump(mode="json"),
    }
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=content,
        media_type=_PROBLEM_JSON_MEDIA_TYPE,
    )


def definition_invalid_handler(request: Request, exc: "WorkflowDefinitionInvalidError") -> JSONResponse:
    """Return RFC 9457 problem details with validation_result extension."""
    return build_validation_problem_response(request, exc.validation_result)


def validation_error_handler(request: Request, exc: "WorkflowValidationError") -> JSONResponse:
    """Handle core WorkflowValidationError with RFC 9457 format."""
    logger.error("Core validation error", exc_info=exc)

    err_detail = exc.message
    detail = "The provided data failed validation requirements" if len(err_detail) == 0 else err_detail
    return create_problem_details_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        problem_type=PROBLEM_TYPES["validation_error"],
        title="Validation Error",
        detail=detail,
        code="VALIDATION_ERROR",
        retryable=False,
        instance=str(request.url),
    )


def workflow_not_found_handler(request: Request, exc: "WorkflowNotFoundError") -> JSONResponse:
    """Handle WorkflowNotFoundError with RFC 9457 format."""
    # Log the full exception for debugging but don't expose workflow IDs to users
    logger.error("Workflow not found", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_404_NOT_FOUND,
        problem_type=PROBLEM_TYPES["resource_not_found"],
        title="Workflow Not Found",
        detail="The requested workflow was not found",
        code="WORKFLOW_NOT_FOUND",
        retryable=False,
        instance=str(request.url),
    )


def execution_not_found_handler(request: Request, exc: "ExecutionNotFoundError") -> JSONResponse:
    """Handle ExecutionNotFoundError with RFC 9457 format."""
    # Log the full exception for debugging but don't expose execution IDs to users
    logger.error("Execution not found", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_404_NOT_FOUND,
        problem_type=PROBLEM_TYPES["resource_not_found"],
        title="Execution Not Found",
        detail="The requested execution was not found",
        code="EXECUTION_NOT_FOUND",
        retryable=False,
        instance=str(request.url),
    )


def execution_not_retryable_handler(request: Request, exc: "ExecutionNotRetryableError") -> JSONResponse:
    """Handle ExecutionNotRetryableError with RFC 9457 format."""
    logger.error(
        "Execution not retryable",
        execution_id=str(exc.execution_id),
        reason=exc.reason,
        exc_info=exc,
    )
    return create_problem_details_response(
        status_code=status.HTTP_409_CONFLICT,
        problem_type=PROBLEM_TYPES["resource_conflict"],
        title="Execution Not Retryable",
        detail=str(exc),
        code="EXECUTION_NOT_RETRYABLE",
        retryable=False,
        instance=str(request.url),
    )


def execution_terminal_state_handler(request: Request, exc: "ExecutionInTerminalStateError") -> JSONResponse:
    """Handle ExecutionInTerminalStateError with RFC 9457 format."""
    logger.error(
        "Cannot modify execution in terminal state",
        execution_id=str(exc.execution_id),
        status=exc.status,
        operation=exc.operation,
        exc_info=exc,
    )
    return create_problem_details_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        problem_type=PROBLEM_TYPES["validation_error"],
        title="Execution In Terminal State",
        detail=f"Cannot {exc.operation} execution in {exc.status} state",
        code="EXECUTION_TERMINAL_STATE",
        retryable=False,
        instance=str(request.url),
    )


def workflow_version_not_found_handler(request: Request, exc: "WorkflowVersionNotFoundError") -> JSONResponse:
    """Handle WorkflowVersionNotFoundError with RFC 9457 format."""
    # Log the full exception for debugging but don't expose workflow IDs to users
    logger.error("Workflow version not found", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_404_NOT_FOUND,
        problem_type=PROBLEM_TYPES["resource_not_found"],
        title="Workflow Version Not Found",
        detail="The requested workflow version was not found",
        code="WORKFLOW_VERSION_NOT_FOUND",
        retryable=False,
        instance=str(request.url),
    )


def workflow_name_conflict_handler(request: Request, exc: "WorkflowNameConflictError") -> JSONResponse:
    """Handle WorkflowNameConflictError with RFC 9457 format."""
    logger.error("Workflow name conflict", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_409_CONFLICT,
        problem_type=PROBLEM_TYPES["name_conflict"],
        title="Workflow Name Conflict",
        detail="A workflow with this name already exists in this project",
        code="WORKFLOW_NAME_CONFLICT",
        retryable=False,
        instance=str(request.url),
    )


def workflow_version_conflict_handler(request: Request, exc: "WorkflowVersionConflictError") -> JSONResponse:
    """Handle WorkflowVersionConflictError with RFC 9457 format and conflict metadata."""
    logger.warning(
        "Workflow version conflict",
        workflow_id=str(exc.workflow_id),
        current_version=exc.current_version,
        expected_version=exc.expected_version,
    )
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "type": PROBLEM_TYPES["resource_conflict"],
            "title": "Version Conflict",
            "detail": "A newer version of this workflow has been saved by another user",
            "code": "WORKFLOW_VERSION_CONFLICT",
            "retryable": False,
            "instance": str(request.url),
            "current_version": exc.current_version,
            "current_version_name": exc.current_version_name,
            "expected_version": exc.expected_version,
            "expected_version_name": exc.expected_version_name,
            "expected_created_at": exc.expected_created_at.isoformat() if exc.expected_created_at else None,
            "created_by_username": exc.created_by_username,
            "created_at": exc.created_at.isoformat(),
        },
        media_type=_PROBLEM_JSON_MEDIA_TYPE,
    )


def workflow_not_published_handler(request: Request, exc: "WorkflowNotPublishedError") -> JSONResponse:
    """Handle WorkflowNotPublishedError with RFC 9457 format."""
    logger.error("Workflow not published", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        problem_type=PROBLEM_TYPES["resource_not_published"],
        title="Workflow Not Published",
        detail="The requested workflow has no published version",
        code="WORKFLOW_NOT_PUBLISHED",
        retryable=False,
        instance=str(request.url),
    )


def builtin_workflow_delete_handler(request: Request, exc: "BuiltinWorkflowDeleteError") -> JSONResponse:
    """Handle BuiltinWorkflowDeleteError with RFC 9457 format."""
    logger.warning("Attempted to delete builtin workflow", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_403_FORBIDDEN,
        problem_type=PROBLEM_TYPES["forbidden"],
        title="Forbidden",
        detail=str(exc),
        code="BUILTIN_WORKFLOW_DELETE_FORBIDDEN",
        retryable=False,
        instance=str(request.url),
    )


def builtin_workflow_modify_handler(request: Request, exc: "BuiltinWorkflowModifyError") -> JSONResponse:
    """Handle BuiltinWorkflowModifyError with RFC 9457 format."""
    logger.warning("Attempted to modify builtin workflow", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_403_FORBIDDEN,
        problem_type=PROBLEM_TYPES["forbidden"],
        title="Forbidden",
        detail=str(exc),
        code="BUILTIN_WORKFLOW_MODIFY_FORBIDDEN",
        retryable=False,
        instance=str(request.url),
    )


def builtin_workflow_missing_handler(request: Request, exc: "BuiltinWorkflowMissingError") -> JSONResponse:
    """Handle BuiltinWorkflowMissingError with RFC 9457 format."""
    logger.error("Required builtin workflow missing", workflow_name=exc.workflow_name, exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        problem_type=PROBLEM_TYPES["internal_error"],
        title="System Misconfigured",
        detail="A required system workflow is missing. Contact your administrator.",
        code="BUILTIN_WORKFLOW_MISSING",
        retryable=True,
        instance=str(request.url),
    )


def temporal_unavailable_handler(request: Request, exc: "TemporalUnavailableError") -> JSONResponse:
    """Handle TemporalUnavailableError with RFC 9457 format."""
    logger.error("Temporal service unavailable", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        problem_type=PROBLEM_TYPES["service_unavailable"],
        title="Temporal Service Unavailable",
        detail="Temporal workflow service is currently unavailable",
        code="TEMPORAL_UNAVAILABLE",
        retryable=True,
        instance=str(request.url),
    )


def workflow_concurrency_limit_handler(request: Request, exc: "WorkflowConcurrencyLimitError") -> JSONResponse:
    """Handle WorkflowConcurrencyLimitError with RFC 9457 format (HTTP 429)."""
    logger.warning(
        "Workflow concurrency limit reached",
        limit=exc.limit,
        active=exc.active,
    )
    return create_problem_details_response(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        problem_type=PROBLEM_TYPES["rate_limited"],
        title="Workflow Concurrency Limit Reached",
        detail=str(exc),
        code="WORKFLOW_CONCURRENCY_LIMIT",
        retryable=True,
        instance=str(request.url),
    )


# ============================================================================
# Trigger Error Handlers
# ============================================================================


def webhook_trigger_not_found_handler(request: Request, exc: "WebhookTriggerNotFoundError") -> JSONResponse:
    """Handle WebhookTriggerNotFoundError with RFC 9457 format."""
    logger.warning("Webhook trigger not found", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_404_NOT_FOUND,
        problem_type=PROBLEM_TYPES["resource_not_found"],
        title="Webhook Trigger Not Found",
        detail="No webhook trigger is configured for the requested path",
        code="WEBHOOK_TRIGGER_NOT_FOUND",
        retryable=False,
        instance=str(request.url),
    )


def webhook_trigger_path_conflict_handler(request: Request, exc: "WebhookTriggerPathConflictError") -> JSONResponse:
    """Handle WebhookTriggerPathConflictError with RFC 9457 format."""
    logger.warning("Webhook trigger path conflict", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_409_CONFLICT,
        problem_type=PROBLEM_TYPES["name_conflict"],
        title="Webhook Path Conflict",
        detail="The requested webhook path is already in use by another trigger",
        code="WEBHOOK_TRIGGER_PATH_CONFLICT",
        retryable=False,
        instance=str(request.url),
    )


def webhook_auth_required_handler(request: Request, exc: "WebhookAuthenticationRequiredError") -> JSONResponse:
    """Handle WebhookAuthenticationRequiredError with RFC 9457 format."""
    logger.warning("Webhook authentication required", exc_info=exc)
    webhook_path = request.path_params.get("webhook_path", "")
    trigger_type = NodeType.EDA_TRIGGER if "/eda/" in request.url.path else NodeType.WEBHOOK_TRIGGER
    AuditEventDispatcher.dispatch(
        WebhookAuthFailureEvent(
            webhook_path=webhook_path,
            trigger_type=trigger_type,
            failure_reason="missing_or_invalid_token",
        )
    )
    return create_problem_details_response(
        status_code=status.HTTP_401_UNAUTHORIZED,
        problem_type=PROBLEM_TYPES["unauthorized"],
        title="Authentication Required",
        detail="A valid service account Bearer token is required to invoke this webhook",
        code="WEBHOOK_AUTH_REQUIRED",
        retryable=False,
        instance=str(request.url),
    )


def webhook_sa_not_authorized_handler(request: Request, exc: "WebhookServiceAccountNotAuthorizedError") -> JSONResponse:
    """Handle WebhookServiceAccountNotAuthorizedError with RFC 9457 format."""
    logger.warning("Service account not authorized for webhook trigger", exc_info=exc)
    AuditEventDispatcher.dispatch(
        WebhookAuthFailureEvent(
            webhook_path=exc.webhook_path,
            trigger_type=exc.trigger_type,
            failure_reason="sa_not_authorized",
            service_account_id=exc.service_account_id,
        )
    )
    return create_problem_details_response(
        status_code=status.HTTP_403_FORBIDDEN,
        problem_type=PROBLEM_TYPES["forbidden"],
        title="Not Authorized",
        detail="The service account is not authorized to invoke this webhook trigger",
        code="WEBHOOK_SA_NOT_AUTHORIZED",
        retryable=False,
        instance=str(request.url),
    )


def scheduled_trigger_sync_handler(request: Request, exc: "ScheduledTriggerSyncError") -> JSONResponse:
    """Handle ScheduledTriggerSyncError with RFC 9457 format."""
    logger.warning("Scheduled trigger sync failed", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        problem_type=PROBLEM_TYPES["service_unavailable"],
        title="Scheduled Trigger Sync Failed",
        detail="Could not sync scheduled triggers because the scheduling service is unavailable",
        code="SCHEDULED_TRIGGER_SYNC_FAILED",
        retryable=True,
        instance=str(request.url),
    )


def scheduled_trigger_not_found_handler(request: Request, exc: "ScheduledTriggerNotFoundError") -> JSONResponse:
    """Handle ScheduledTriggerNotFoundError with RFC 9457 format."""
    logger.warning("Scheduled trigger not found", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_404_NOT_FOUND,
        problem_type=PROBLEM_TYPES["resource_not_found"],
        title="Scheduled Trigger Not Found",
        detail="No scheduled trigger is configured for the requested schedule ID",
        code="SCHEDULED_TRIGGER_NOT_FOUND",
        retryable=False,
        instance=str(request.url),
    )


def trigger_validation_handler(request: Request, exc: "TriggerValidationError") -> JSONResponse:
    """Handle TriggerValidationError with RFC 9457 format."""
    logger.warning("Trigger payload validation failed", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        problem_type=PROBLEM_TYPES["validation_error"],
        title="Trigger Payload Validation Failed",
        detail=exc.message,
        code="TRIGGER_VALIDATION_ERROR",
        retryable=False,
        instance=str(request.url),
    )


def payload_too_large_handler(request: Request, exc: "PayloadTooLargeError") -> JSONResponse:
    """Handle PayloadTooLargeError with RFC 9457 format."""
    logger.warning("Webhook payload too large", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        problem_type=PROBLEM_TYPES["payload_too_large"],
        title="Payload Too Large",
        detail=exc.message,
        code="PAYLOAD_TOO_LARGE",
        retryable=False,
        instance=str(request.url),
    )


def temporal_rpc_error_handler(request: Request, exc: RPCError) -> JSONResponse:
    """Handle Temporal RPCError with RFC 9457 format."""
    # Log the full error for debugging but don't expose it to users
    logger.error("Temporal RPC error", exc_info=exc)

    return create_problem_details_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        problem_type=PROBLEM_TYPES["internal_error"],
        title="Temporal Workflow Error",
        detail="Temporal workflow operation failed",
        code="TEMPORAL_WORKFLOW_ERROR",
        retryable=True,
        instance=str(request.url),
    )
