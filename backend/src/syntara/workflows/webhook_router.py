"""Webhook reception endpoints for triggering workflows from external systems.

This router handles incoming POST requests from external services (GitHub, Jira,
Slack, EDA, etc.) and triggers the matching workflow. Callers must authenticate
with a service account Bearer token obtained via the OAuth client credentials grant.
"""

from typing import Annotated, Any
from uuid import UUID

import structlog
from fastapi import Body, Depends, Path, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlmodel import Field, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from temporalio.service import RPCError

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.auth.dependencies import (  # private helpers — candidates for a public API (see AAP-83333 review)
    _check_global_revocation,
    _get_token_service,
    _user_from_payload,
    bearer_scheme,
)
from syntara.auth.exceptions import InvalidTokenError
from syntara.core.constants import WebhookLimits
from syntara.core.database.session import get_db
from syntara.core.models import User
from syntara.core.syntara_router import SyntaraRouter
from syntara.workflows.audit.webhook_auth import WebhookAuthSuccessEvent
from syntara.workflows.exceptions import (
    PayloadTooLargeError,
    TemporalUnavailableError,
    TriggerValidationError,
    WebhookAuthenticationRequiredError,
)
from syntara.workflows.services.execution_service import ExecutionService
from syntara.workflows.services.webhook_trigger_service import WebhookTriggerService
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType
from syntara.workflows.workflow_engine.services.temporal_execution_service import (
    TemporalExecutionService,
    create_temporal_execution_service,
)

logger = structlog.stdlib.get_logger(__name__)

router = SyntaraRouter(prefix="/webhooks", tags=["Webhooks"])


# ============================================================================
# Response Models
# ============================================================================


class WebhookResponse(SQLModel):
    """Response from webhook reception endpoint."""

    execution_id: UUID = Field(description="ID of the triggered workflow execution")
    message: str = Field(description="Human-readable status message")


# ============================================================================
# Dependencies
# ============================================================================


async def _check_payload_size(request: Request) -> None:
    """Reject oversized webhook payloads before business logic runs.

    Two-phase check: first the Content-Length header (fast-path rejection
    without reading the body), then a streaming read that aborts as soon
    as the limit is exceeded — never buffering more than the allowed
    maximum.  A reverse proxy / API gateway should also enforce body size
    limits as an additional layer (e.g. nginx ``client_max_body_size 1m;``).
    """
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            length = int(content_length)
        except (ValueError, TypeError):
            msg = "Invalid Content-Length header"
            raise TriggerValidationError(msg) from None
        if length > WebhookLimits.PAYLOAD_MAX_BYTES:
            msg = f"Payload too large: {length} bytes exceeds maximum of {WebhookLimits.PAYLOAD_MAX_BYTES} bytes"
            raise PayloadTooLargeError(msg)

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > WebhookLimits.PAYLOAD_MAX_BYTES:
            msg = f"Payload too large: exceeds maximum of {WebhookLimits.PAYLOAD_MAX_BYTES} bytes"
            raise PayloadTooLargeError(msg)

    # Cache so downstream FastAPI Body() parsing can re-read it.
    request._body = bytes(body)  # noqa: SLF001


async def get_webhook_temporal_service() -> TemporalExecutionService | None:
    """Dependency provider for Temporal execution service in webhook context.

    Returns None if Temporal is unavailable (graceful degradation).
    """
    try:
        return await create_temporal_execution_service()
    except (RPCError, OSError, RuntimeError) as e:
        logger.warning("Temporal service unavailable for webhook", error=str(e))
        return None


async def get_webhook_caller(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> tuple[User, UUID]:
    """Authenticate the webhook caller as a service account.

    Returns:
        Tuple of (authenticated User, service account UUID).

    Raises:
        WebhookAuthenticationRequiredError: If no token or not a service account token.

    """
    if not credentials:
        raise WebhookAuthenticationRequiredError

    token_service = _get_token_service()
    try:
        payload = token_service.decode_token(credentials.credentials, token_type="access")  # noqa: S106
    except InvalidTokenError as e:
        logger.info("Webhook auth failed: invalid token", error=str(e))
        raise WebhookAuthenticationRequiredError from e

    await _check_global_revocation(payload, token_type="access", db=db)  # noqa: S106

    if payload.token_type != "service_account":  # noqa: S105
        raise WebhookAuthenticationRequiredError

    user = _user_from_payload(payload)
    sa_id = UUID(payload.sub)
    return user, sa_id


# ============================================================================
# Shared Logic
# ============================================================================


async def _handle_webhook_request(
    webhook_path: str,
    payload: Any,  # noqa: ANN401
    trigger_type: str,
    caller: tuple[User, UUID],
    temporal_service: TemporalExecutionService | None,
    db: AsyncSession,
    label: str = "",
) -> WebhookResponse:
    label = f"{label} webhook" if label else "webhook"
    user, sa_id = caller
    logger.info(
        "Received webhook event",
        trigger_type=label,
        webhook_path=webhook_path,
        service_account_id=str(sa_id),
        payload_type=type(payload).__name__,
    )

    webhook_service = WebhookTriggerService(db, user)
    trigger = await webhook_service.get_by_webhook_path(webhook_path, trigger_type=trigger_type)

    await webhook_service.verify_service_account_authorization(trigger.id, sa_id)

    AuditEventDispatcher.dispatch(
        WebhookAuthSuccessEvent(
            service_account_id=sa_id,
            webhook_path=webhook_path,
            trigger_type=trigger_type,
            workflow_id=trigger.workflow_id,
        )
    )

    if temporal_service is None:
        raise TemporalUnavailableError(f"{label} triggering")  # noqa: EM102, TRY003

    execution_service = ExecutionService(db, user, temporal_service=temporal_service)
    trigger_input = payload

    execution = await execution_service.create_execution(
        workflow_id=trigger.workflow_id,
        input_data=trigger_input,
        trigger_node_id=trigger.trigger_node_id,
        use_published=True,
    )

    logger.info(
        "Webhook triggered workflow execution",
        trigger_type=label,
        webhook_path=webhook_path,
        workflow_id=trigger.workflow_id,
        execution_id=execution.id,
        trigger_node_id=trigger.trigger_node_id,
        service_account_id=str(sa_id),
    )

    return WebhookResponse(
        execution_id=execution.id,
        message=f"Workflow execution started from {label} '{webhook_path}'",
    )


# ============================================================================
# Endpoints
# ============================================================================


@router.post(
    "/{webhook_path}",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="receive_webhook",
    summary="Receive webhook event",
    description=(
        "Receive a webhook event from an external system and trigger the matching workflow. "
        "Requires a service account Bearer token. "
        "Only POST method is supported; other methods receive 405 Method Not Allowed."
    ),
    response_description="Webhook accepted and workflow execution started",
    responses={
        401: {
            "description": "Missing or invalid service account Bearer token",
            "content": {"application/problem+json": {"schema": {"$ref": "#/components/schemas/ErrorData"}}},
        },
        403: {
            "description": "Service account is not authorized for this trigger",
            "content": {"application/problem+json": {"schema": {"$ref": "#/components/schemas/ErrorData"}}},
        },
        413: {
            "description": "Payload exceeds the 1 MB size limit",
            "content": {"application/problem+json": {"schema": {"$ref": "#/components/schemas/ErrorData"}}},
        },
    },
)
async def receive_webhook(
    webhook_path: Annotated[str, Path(max_length=WebhookLimits.PATH_MAX_LENGTH, pattern=WebhookLimits.PATH_PATTERN)],
    payload: Annotated[Any, Body()],  # noqa: ANN401
    caller: Annotated[tuple[User, UUID], Depends(get_webhook_caller)],
    temporal_service: Annotated[TemporalExecutionService | None, Depends(get_webhook_temporal_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _payload_size: Annotated[None, Depends(_check_payload_size)],
) -> WebhookResponse:
    """Receive a webhook event and trigger the matching workflow."""
    return await _handle_webhook_request(
        webhook_path=webhook_path,
        payload=payload,
        trigger_type=NodeType.WEBHOOK_TRIGGER,
        caller=caller,
        temporal_service=temporal_service,
        db=db,
    )


@router.post(
    "/eda/{webhook_path}",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="receive_eda_webhook",
    summary="Receive EDA webhook event",
    description=(
        "Receive a webhook event from Event-Driven Ansible and trigger the matching workflow. "
        "Requires a service account Bearer token. "
        "Each EDA trigger node has its own unique webhook path. "
        "The payload can be any JSON structure."
    ),
    response_description="Webhook accepted and workflow execution started",
    responses={
        401: {
            "description": "Missing or invalid service account Bearer token",
            "content": {"application/problem+json": {"schema": {"$ref": "#/components/schemas/ErrorData"}}},
        },
        403: {
            "description": "Service account is not authorized for this trigger",
            "content": {"application/problem+json": {"schema": {"$ref": "#/components/schemas/ErrorData"}}},
        },
        413: {
            "description": "Payload exceeds the 1 MB size limit",
            "content": {"application/problem+json": {"schema": {"$ref": "#/components/schemas/ErrorData"}}},
        },
    },
)
async def receive_eda_webhook(
    webhook_path: Annotated[str, Path(max_length=WebhookLimits.PATH_MAX_LENGTH, pattern=WebhookLimits.PATH_PATTERN)],
    payload: Annotated[Any, Body()],  # noqa: ANN401
    caller: Annotated[tuple[User, UUID], Depends(get_webhook_caller)],
    temporal_service: Annotated[TemporalExecutionService | None, Depends(get_webhook_temporal_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _payload_size: Annotated[None, Depends(_check_payload_size)],
) -> WebhookResponse:
    """Receive a webhook event from EDA and trigger the matching workflow."""
    return await _handle_webhook_request(
        webhook_path=webhook_path,
        payload=payload,
        trigger_type=NodeType.EDA_TRIGGER,
        caller=caller,
        temporal_service=temporal_service,
        db=db,
        label="EDA",
    )
