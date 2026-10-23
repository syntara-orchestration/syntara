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
from syntara.eventstreams.models.responses import (
    EventSubscriptionListParams,
    EventSubscriptionListResponse,
    EventSubscriptionRead,
    EventSubscriptionTestResponse,
)
from syntara.eventstreams.services.inspection_service import EventSubscriptionInspectionService
from syntara.workflows.models.workflow import Workflow

router = SyntaraRouter(prefix="/workflows/{workflow_id}/event-subscriptions", tags=["Workflows"])
_read = PermissionChecker("workflow", "read", resource_model=Workflow, resource_id_param="workflow_id")
_update = PermissionChecker("workflow", "update", resource_model=Workflow, resource_id_param="workflow_id")


def get_inspection_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    evaluator: Annotated[AuthzEvaluator, Depends(get_authz_evaluator)],
) -> EventSubscriptionInspectionService:
    """Compose request-scoped read and validation dependencies."""
    return EventSubscriptionInspectionService(db, user, evaluator, create_secret_service(db))


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
    """Read the requested current subscription within its workflow/project."""
    return await service.get_current(workflow_id, subscription_id)
