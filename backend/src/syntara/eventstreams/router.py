"""Workflow-scoped subscription reads and unsaved runtime preflight."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Query, Request
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth import get_current_user
from syntara.authz.dependencies import PermissionChecker, get_authz_evaluator
from syntara.authz.evaluator import AuthzEvaluator
from syntara.core.database.session import get_db
from syntara.core.models import User
from syntara.core.services.secret_service import create_secret_service
from syntara.core.syntara_router import SyntaraRouter
from syntara.eventstreams.adapters.kafka_parameters import KafkaSubscribeParameters
from syntara.eventstreams.models.controls import (
    SubscriptionControlRequest,
    SubscriptionControlResponse,
    SubscriptionRecoveryRequest,
    SubscriptionRetireRequest,
)
from syntara.eventstreams.models.responses import (
    EventSubscriptionListParams,
    EventSubscriptionListResponse,
    EventSubscriptionRead,
    EventSubscriptionTestResponse,
)
from syntara.eventstreams.services.control_service import EventSubscriptionControlService
from syntara.eventstreams.services.inspection_service import EventSubscriptionInspectionService
from syntara.workflows.models.workflow import Workflow

router = SyntaraRouter(prefix="/workflows/{workflow_id}/event_subscriptions", tags=["Workflows"])
_read = PermissionChecker("workflow", "read", resource_model=Workflow, resource_id_param="workflow_id")
_update = PermissionChecker("workflow", "update", resource_model=Workflow, resource_id_param="workflow_id")
_recover = PermissionChecker("event_subscription", "recover", resource_model=Workflow, resource_id_param="workflow_id")


def get_control_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    evaluator: Annotated[AuthzEvaluator, Depends(get_authz_evaluator)],
    request: Request,
) -> EventSubscriptionControlService:
    """Preserve workflow permissions and actor authentication context."""
    return EventSubscriptionControlService(
        db, user, evaluator, is_cert_authenticated=getattr(request.state, "is_cert_authenticated", False)
    )


@router.post(
    "/{subscription_id}/pause",
    operation_id="pause_event_subscription",
    summary="Pause event subscription",
    dependencies=[Depends(_update)],
)
async def pause_event_subscription(
    workflow_id: UUID,
    subscription_id: UUID,
    body: SubscriptionControlRequest,
    service: Annotated[EventSubscriptionControlService, Depends(get_control_service)],
) -> SubscriptionControlResponse:
    """Close new admission; report pending until all consumer stops are acknowledged."""
    return await service.action(workflow_id, subscription_id, body, "pause")


@router.post(
    "/{subscription_id}/resume",
    operation_id="resume_event_subscription",
    summary="Resume event subscription",
    dependencies=[Depends(_update)],
)
async def resume_event_subscription(
    workflow_id: UUID,
    subscription_id: UUID,
    body: SubscriptionControlRequest,
    service: Annotated[EventSubscriptionControlService, Depends(get_control_service)],
) -> SubscriptionControlResponse:
    """Resume only a current published source without changing its frozen deliveries."""
    return await service.action(workflow_id, subscription_id, body, "resume")


@router.post(
    "/{subscription_id}/retry",
    operation_id="retry_event_subscription",
    summary="Retry event subscription",
    dependencies=[Depends(_update)],
)
async def retry_event_subscription(
    workflow_id: UUID,
    subscription_id: UUID,
    body: SubscriptionControlRequest,
    service: Annotated[EventSubscriptionControlService, Depends(get_control_service)],
) -> SubscriptionControlResponse:
    """Retry runtime setup and prepared scheduling; never replay or reset positions."""
    return await service.action(workflow_id, subscription_id, body, "retry")


@router.post(
    "/{subscription_id}/recover",
    operation_id="recover_event_subscription",
    summary="Recover event subscription",
    status_code=202,
    dependencies=[Depends(_update), Depends(_recover)],
)
async def recover_event_subscription(
    workflow_id: UUID,
    subscription_id: UUID,
    body: SubscriptionRecoveryRequest,
    service: Annotated[EventSubscriptionControlService, Depends(get_control_service)],
) -> SubscriptionControlResponse:
    """Queue an authorized boundary policy for the current partition owner."""
    return await service.recover(workflow_id, subscription_id, body)


@router.post(
    "/{subscription_id}/retire",
    operation_id="retire_event_subscription",
    summary="Retire event subscription source",
    dependencies=[Depends(_update)],
)
async def retire_event_subscription(
    workflow_id: UUID,
    subscription_id: UUID,
    body: SubscriptionRetireRequest,
    service: Annotated[EventSubscriptionControlService, Depends(get_control_service)],
) -> SubscriptionControlResponse:
    """Retire a removed/replaced source; disposition additionally requires retire authority."""
    return await service.retire(workflow_id, subscription_id, body)


def get_inspection_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    evaluator: Annotated[AuthzEvaluator, Depends(get_authz_evaluator)],
    request: Request,
) -> EventSubscriptionInspectionService:
    """Compose request-scoped read and validation dependencies."""
    return EventSubscriptionInspectionService(
        db,
        user,
        evaluator,
        create_secret_service(db),
        is_cert_authenticated=getattr(request.state, "is_cert_authenticated", False),
    )


@router.get(
    "",
    operation_id="list_event_subscriptions",
    summary="List workflow event subscriptions",
    dependencies=[Depends(_read)],
)
async def list_event_subscriptions(
    workflow_id: UUID,
    request: Request,
    params: Annotated[EventSubscriptionListParams, Query()],
    service: Annotated[EventSubscriptionInspectionService, Depends(get_inspection_service)],
) -> EventSubscriptionListResponse:
    """Read current published subscription/source configuration with bounded pagination."""
    return await service.list_current(workflow_id, params, request.query_params.multi_items())


@router.post(
    "/test",
    operation_id="test_event_subscription",
    summary="Test unsaved event subscription",
    dependencies=[Depends(_update)],
)
async def test_event_subscription(
    workflow_id: UUID,
    parameters: KafkaSubscribeParameters,
    service: Annotated[EventSubscriptionInspectionService, Depends(get_inspection_service)],
) -> EventSubscriptionTestResponse:
    """Check runtime credentials and non-creating metadata; READ/group ACLs remain unverified."""
    return await service.test_unsaved(workflow_id, parameters)


@router.get(
    "/{subscription_id}",
    operation_id="get_event_subscription",
    summary="Get workflow event subscription",
    dependencies=[Depends(_read)],
)
async def get_event_subscription(
    workflow_id: UUID,
    subscription_id: UUID,
    service: Annotated[EventSubscriptionInspectionService, Depends(get_inspection_service)],
) -> EventSubscriptionRead:
    """Read subscription lifecycle and recovery state within its workflow/project."""
    return await service.get_current(workflow_id, subscription_id)
