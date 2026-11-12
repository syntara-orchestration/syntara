"""Workflow-authorized connection testing for unsaved Kafka Subscribe parameters."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth import get_current_user
from syntara.authz.dependencies import PermissionChecker, get_authz_evaluator
from syntara.authz.evaluator import AuthzEvaluator
from syntara.core.database.session import get_db
from syntara.core.models import User
from syntara.core.services.secret_service import create_secret_service
from syntara.core.syntara_router import SyntaraRouter
from syntara.eventstreams.adapters.kafka_parameters import KafkaSubscribeParameters
from syntara.eventstreams.models.responses import EventSubscriptionTestResponse
from syntara.eventstreams.services.inspection_service import EventSubscriptionInspectionService
from syntara.workflows.models.workflow import Workflow

router = SyntaraRouter(prefix="/workflows/{workflow_id}/event_subscriptions", tags=["Workflows"])
_update = PermissionChecker("workflow", "update", resource_model=Workflow, resource_id_param="workflow_id")


def get_inspection_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    evaluator: Annotated[AuthzEvaluator, Depends(get_authz_evaluator)],
    request: Request,
) -> EventSubscriptionInspectionService:
    """Compose request-scoped connection-test dependencies."""
    return EventSubscriptionInspectionService(
        db,
        user,
        evaluator,
        create_secret_service(db),
        is_cert_authenticated=getattr(request.state, "is_cert_authenticated", False),
    )


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
