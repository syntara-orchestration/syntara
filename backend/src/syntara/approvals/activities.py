"""Approval-owned activity handlers, independent of Temporal and HTTP clients."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from sqlmodel import select

from syntara.approvals.audit.approval import ApprovalExpiredEvent
from syntara.approvals.exceptions import ApprovalAlreadyRequestedError
from syntara.approvals.models.api_models import (
    ApprovalCreateRequest,
    ApprovalRequestStatus,
    BatchApprovalDecision,
    BatchApprovalDecisionStatus,
    BatchApprovalRequest,
)
from syntara.approvals.models.approval_request import ApprovalRequest
from syntara.approvals.services.approval_service import ApprovalService
from syntara.audit.context_managers import actor_context
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.core.models.principal import make_service_user
from syntara.workflow_runtime.contracts import ActivityContext, ActivityError, Completed, Deferred

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession


class ApprovalActivities:
    """Provide request and cleanup operations using approval business services."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Inject persistence at worker composition."""
        self.session_factory = session_factory

    @asynccontextmanager
    async def _service(self, context: ActivityContext) -> AsyncIterator[ApprovalService]:
        user = make_service_user("worker.ao.svc")
        with actor_context(actor=user, execution_id=context.execution_id, activity_id=context.node_execution_id):
            async with self.session_factory() as session:
                yield ApprovalService(session, user)

    async def request(self, inputs: dict[str, Any], context: ActivityContext) -> Completed | Deferred:
        """Create or reattach an approval, preserving decisions across retries."""
        if context.completion_ref is None:
            msg = "Approval request requires a completion reference"
            raise ActivityError(msg)
        request = ApprovalCreateRequest.model_validate(
            {**inputs, "execution_id": context.execution_id, "project_id": context.project_id}
        )
        async with self._service(context) as service:
            session = service.session
            try:
                approval = await service.create(request, completion_ref=context.completion_ref)
            except ApprovalAlreadyRequestedError:
                await session.rollback()
                approval = await service.attach_activity(request, context.completion_ref)
            if approval.status in {ApprovalRequestStatus.APPROVED, ApprovalRequestStatus.REJECTED}:
                return Completed(
                    {
                        "decision": approval.status.value,
                        "decided_by": approval.decided_by.name if approval.decided_by else None,
                        "decided_at": approval.decided_at.isoformat() if approval.decided_at else None,
                        "decision_notes": approval.decision_notes,
                    }
                )
            if approval.status != ApprovalRequestStatus.PENDING:
                msg = f"Approval is already {approval.status.value}"
                raise ActivityError(msg, code="ApprovalClosed")
            return Deferred(context.completion_ref, str(approval.id))

    async def expire(self, inputs: dict[str, Any], context: ActivityContext) -> Completed:
        """Expire pending requests for the execution, optionally for one canvas node."""
        return await self._cleanup(inputs, context, BatchApprovalDecisionStatus.EXPIRED)

    async def cancel(self, inputs: dict[str, Any], context: ActivityContext) -> Completed:
        """Cancel pending requests using the same authorization and audit path as the API."""
        return await self._cleanup(inputs, context, BatchApprovalDecisionStatus.CANCELLED)

    async def _cleanup(
        self, inputs: dict[str, Any], context: ActivityContext, status: BatchApprovalDecisionStatus
    ) -> Completed:
        async with self._service(context) as service:
            session = service.session
            query = select(ApprovalRequest).where(
                ApprovalRequest.execution_id == context.execution_id,
                ApprovalRequest.project_id == context.project_id,
                ApprovalRequest.status == ApprovalRequestStatus.PENDING,
            )
            node_id = inputs.get("node_id")
            if node_id is not None:
                query = query.where(ApprovalRequest.approval_node_id == node_id)
            pending = (await session.exec(query)).all()
            key = "expired_count" if status == BatchApprovalDecisionStatus.EXPIRED else "cancelled_count"
            if not pending:
                return Completed({key: 0})
            nodes = {row.id: row.approval_node_id for row in pending}
            result = await service.batch_decide(
                BatchApprovalRequest(
                    decisions=[BatchApprovalDecision(approval_id=row.id, status=status) for row in pending]
                )
            )
            if status == BatchApprovalDecisionStatus.EXPIRED:
                for item in result.results:
                    if item.success:
                        AuditEventDispatcher.dispatch(
                            ApprovalExpiredEvent(
                                approval_id=item.approval_id,
                                execution_id=context.execution_id,
                                approval_node_id=nodes[item.approval_id],
                            )
                        )
            if result.total_failed:
                msg = "Some approval cleanup operations failed"
                raise ActivityError(msg, retryable=True)
            return Completed({key: result.total_success})
