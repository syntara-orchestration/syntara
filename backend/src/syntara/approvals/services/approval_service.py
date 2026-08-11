"""Approval service layer for business logic.

This service encapsulates approval-related business logic, separating it from
HTTP/API concerns in the FastAPI endpoints. It handles all approval request
operations including creating, listing, deciding, and cancelling approvals.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

import structlog
from sqlalchemy import delete as sa_delete
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from uuid import UUID

    from sqlalchemy import Select
    from sqlmodel.ext.asyncio.session import AsyncSession
    from sqlmodel.sql._expression_select_cls import SelectOfScalar

    from syntara.authz.engine import AllowedProjectsResult
    from syntara.authz.evaluator import AuthzEvaluator
    from syntara.core.models import User

from syntara.approvals.audit.approval import ApprovalDecidedEvent, ApprovalDecisionDeniedEvent, ApprovalRequestedEvent
from syntara.approvals.clients.workflow_client import WorkflowApiClient
from syntara.approvals.exceptions import (
    ApprovalAlreadyDecidedError,
    ApprovalAlreadyRequestedError,
    ApprovalNotAuthorizedError,
    ApprovalNotFoundError,
)
from syntara.approvals.models import (
    ApprovalApproverGroup,
    ApprovalApproverUser,
    ApprovalCreateRequest,
    ApprovalDecisionRequest,
    ApprovalListResponse,
    ApprovalRequest,
    ApprovalRequestRead,
    ApprovalRequestStatus,
    ApproverGroupSummary,
    ApproverUserSummary,
    BatchApprovalDecision,
    BatchApprovalDecisionStatus,
    BatchApprovalRequest,
    BatchApprovalResponse,
    BatchApprovalResult,
    UserReference,
)
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.core.services import BaseService, GroupMembershipService
from syntara.core.services.extensions import ConvertResourceMixin, EnrichQueryMixin

logger = structlog.stdlib.get_logger(__name__)


class ApprovalEnrichQuery(EnrichQueryMixin):
    """Eagerly load the decider and approver relationships to avoid lazy-load in async context."""

    def enrich(  # type: ignore[override]
        self,
        query: Select[tuple[ApprovalRequest]] | SelectOfScalar[tuple[ApprovalRequest]],
    ) -> Select[tuple[ApprovalRequest]] | SelectOfScalar[tuple[ApprovalRequest]]:
        """Add selectinload for the decider and approver relationships."""
        # Use inline loading to avoid accessing ApprovalService (which uses this mixin)
        return query.options(
            selectinload(ApprovalRequest.decider),  # type: ignore[arg-type]
            selectinload(ApprovalRequest.approver_user_records),  # type: ignore[arg-type]
            selectinload(ApprovalRequest.approver_group_records),  # type: ignore[arg-type]
        )


class ApprovalServiceConvertResourceMixin(ConvertResourceMixin):
    """Mixin for converting ApprovalRequest resources to ApprovalRequestRead format."""

    def __init__(self, user: User) -> None:
        """Initialize ApprovalServiceConvertResourceMixin with current user."""
        super().__init__()
        self.user = user

    def convert_resource(self, resource: ApprovalRequest) -> ApprovalRequestRead:  # type: ignore[override]
        """Convert ApprovalRequest to ApprovalRequestRead format."""
        # Extract data from the resource, excluding FK relationship fields and decided_by
        resource_data = resource.model_dump(exclude={"decided_by", "approver_user_records", "approver_group_records"})

        # Create the ApprovalRequestRead instance with the base data
        result = ApprovalRequestRead(**resource_data)

        # Populate approver_users from FK relationship
        approver_user_records = getattr(resource, "approver_user_records", None) or []
        result.approver_users = [
            ApproverUserSummary(id=user.id, username=user.username) for user in approver_user_records
        ]

        # Populate approver_groups from FK relationship
        approver_group_records = getattr(resource, "approver_group_records", None) or []
        result.approver_groups = [
            ApproverGroupSummary(id=group.id, name=group.name) for group in approver_group_records
        ]

        # Set the decided_by field with UserReference if there's a decider.
        # Check the FK column first to avoid triggering a lazy load (which
        # fails in async context with MissingGreenlet).  The decider
        # relationship may still be None after selectinload if the session
        # state was reset (e.g. after commit in decide()), so fall back to
        # the current user when the decider matches.
        if resource.decided_by is not None:
            decider = getattr(resource, "decider", None)
            if decider is not None:
                decider_name = decider.display_name
            elif resource.decided_by == self.user.id:
                decider_name = self.user.display_name
            else:
                decider_name = ""
            result.decided_by = UserReference(id=resource.decided_by, name=decider_name)

        return result


class ApprovalService(BaseService):
    """Service for approval business logic.

    This service encapsulates all approval-related business operations,
    including CRUD operations, decision processing, and workflow integration.
    """

    def __init__(self, session: AsyncSession, user: User, evaluator: AuthzEvaluator | None = None) -> None:
        """Initialize ApprovalService with database session and user context."""
        super().__init__(
            session,
            user,
            convert_resource_mixin=ApprovalServiceConvertResourceMixin(user),
            enrich_query_mixin=ApprovalEnrichQuery(),
        )
        self.group_membership_service = GroupMembershipService(session)
        self.evaluator = evaluator

    async def list(
        self,
        limit: int = 20,
        cursor: str | None = None,
        sort: str | None = None,
        query_params_items: Iterable[tuple[str, str]] | None = None,
        *,
        include_total: bool = False,
        allowed_projects: AllowedProjectsResult | None = None,
    ) -> ApprovalListResponse:
        """List approval requests with filtering, sorting, and pagination.

        Args:
            limit: Maximum number of approval requests to return (default 20)
            cursor: Cursor token for pagination
            sort: Sort parameter (e.g., "name", "-created_at")
            query_params_items: Raw query parameter items from request (for filtering)
            include_total: Whether to include total count in response
            allowed_projects: Project scope filter from authorization

        Returns:
            ApprovalListResponse with approval requests, pagination metadata, and optional total

        Note:
            Eager-loads approver relationships via ApprovalEnrichQuery mixin to avoid N+1 queries.

        """
        return await self.list_resources(
            model=ApprovalRequest,
            response_type=ApprovalListResponse,
            limit=limit,
            cursor=cursor,
            sort=sort,
            query_params_items=query_params_items,
            include_total=include_total,
            allowed_projects=allowed_projects,
        )

    @staticmethod
    def _approval_eager_loads(*, include_decider: bool = True) -> Sequence[Any]:
        """Return selectinload options for eagerly loading approval relationships.

        This centralizes the relationship loading pattern used across multiple query methods
        to ensure consistency and simplify maintenance when adding new relationships.

        Args:
            include_decider: Whether to include the decider relationship (False for create)

        Returns:
            List of selectinload options

        """
        opts: list[Any] = []
        if include_decider:
            opts.append(selectinload(ApprovalRequest.decider))  # type: ignore[arg-type]
        opts.extend(
            [
                selectinload(ApprovalRequest.approver_user_records),  # type: ignore[arg-type]
                selectinload(ApprovalRequest.approver_group_records),  # type: ignore[arg-type]
            ]
        )
        return opts

    async def _refresh_approval_relationships(self, approval: ApprovalRequest, *, include_decider: bool = True) -> None:
        """Refresh approval relationships from the database.

        This centralizes the relationship refresh pattern used after commit/signal operations
        to ensure consistency when adding new relationships.

        Args:
            approval: The approval request to refresh
            include_decider: Whether to include the decider relationship

        """
        attrs = ["approver_user_records", "approver_group_records"]
        if include_decider:
            attrs.insert(0, "decider")
        await self.session.refresh(approval, attrs)

    async def _get_approval_by_id(self, approval_id: UUID) -> ApprovalRequest | None:
        query = (
            select(ApprovalRequest)
            .where(ApprovalRequest.id == approval_id)
            .options(*ApprovalService._approval_eager_loads())
        )
        result = await self.session.exec(query)
        return result.one_or_none()

    async def _get_approval_request(self, execution_id: UUID, approval_node_id: str) -> ApprovalRequest | None:
        query = (
            select(ApprovalRequest)
            .where(
                ApprovalRequest.execution_id == execution_id,
                ApprovalRequest.approval_node_id == approval_node_id,
            )
            .options(*ApprovalService._approval_eager_loads(include_decider=False))
        )
        result = await self.session.exec(query)
        return result.one_or_none()

    async def get(self, approval_id: UUID) -> ApprovalRequestRead:
        """Get a single approval request by ID.

        Args:
            approval_id: UUID of the approval request

        Returns:
            The approval request

        Raises:
            ApprovalNotFoundError: If approval request not found

        """
        approval: ApprovalRequest | None = await self._get_approval_by_id(approval_id)

        if not approval:
            raise ApprovalNotFoundError(approval_id)

        return cast("ApprovalRequestRead", self.convert_resource_mixin.convert_resource(approval))

    @staticmethod
    def _check_eager_loads(approval: ApprovalRequest) -> None:
        """Ensure approver relationships were eagerly loaded to avoid MissingGreenlet."""
        inspector = sa_inspect(approval)
        approver_users_loaded = inspector is not None and "approver_user_records" not in inspector.unloaded
        approver_groups_loaded = inspector is not None and "approver_group_records" not in inspector.unloaded

        if not approver_users_loaded or not approver_groups_loaded:
            msg = (
                "_is_user_authorized_approver requires approval to be fetched with "
                "eager loading of approver_user_records and approver_group_records. "
                "Use _get_approval_by_id() or selectinload() when fetching."
            )
            raise RuntimeError(msg)

    async def _has_permission(self, approval: ApprovalRequest, action: str = "decide") -> bool:
        """Check evaluator for approval permission (project-scoped or system-level)."""
        from syntara.authz.engine import AuthzRequest, authorize  # noqa: PLC0415
        from syntara.authz.models.project import Project  # noqa: PLC0415

        evaluator = self.evaluator
        if evaluator is None:
            return False

        project_name = ""
        if approval.project_id:
            result = await self.session.exec(select(Project.name).where(Project.id == approval.project_id))
            project_name = result.first() or ""

        authz_request = AuthzRequest(
            user_id=self.user.id,
            action=action,
            resource_type="approval",
            resource_id=str(approval.id),
            resource_project=project_name,
            resource_labels={},
            user_labels=self.user.labels,
            user_metadata=self.user.authz_metadata,
        )

        authz_result = await authorize(self.session, evaluator, authz_request)
        return authz_result.allowed

    async def _is_user_authorized_approver(self, approval: ApprovalRequest, *, action: str = "decide") -> bool:
        """Check if current user is authorized to act on this approval.

        Args:
            approval: The approval request to check authorization for
            action: The authz action to check (e.g. "decide", "delete")

        Authorization logic:
        1. Service principals (cert-authenticated S2S callers) are always authorized
        2. Check evaluator for the specified permission (project-scoped or system-level)
        3. If no approvers configured, any user with the permission can act
        4. If approver_users configured, current user's username must be in the list
        5. If approver_groups configured, current user must be a member of at least one group

        SECURITY: This method performs BOTH authz permission check AND approver list check.
        Used by batch_decide endpoint which doesn't have endpoint-level permission dependency
        to support users with project-scoped (not system-level) approval:decide permission.

        """
        self._check_eager_loads(approval)

        # Cert-authenticated service principals bypass OPA — they are internal
        # S2S callers (e.g. workflow engine cancelling approvals). This mirrors
        # the endpoint-level RequirePermission bypass in authz/dependencies.py.
        from syntara.core.models.principal import KNOWN_SERVICE_CNS, service_principal_id  # noqa: PLC0415

        if self.user.id in {service_principal_id(cn) for cn in KNOWN_SERVICE_CNS}:
            return True

        # SECURITY: Check evaluator for the specified approval permission (project-scoped or system-level)
        # This is required for batch_decide which doesn't have endpoint-level permission check.
        if self.evaluator is None:
            return False

        if not await self._has_permission(approval, action):
            return False

        # SECURITY: When no specific approvers configured (both lists empty), allow if user
        # has the requested permission (checked above via evaluator or at endpoint level).
        # Empty lists = AC5 fallback (any user with the permission can act).
        if not approval.approver_user_records and not approval.approver_group_records:
            return True

        # Check if current user is in the approver lists (user or group membership)
        in_user_list = approval.approver_user_records and self.user.id in {
            user.id for user in approval.approver_user_records
        }
        in_group = approval.approver_group_records and await self.group_membership_service.is_user_in_any_group_by_ids(
            user_id=self.user.id,
            group_ids=[group.id for group in approval.approver_group_records],
        )
        return bool(in_user_list or in_group)

    def _dispatch_authorization_denied(self, approval: ApprovalRequest, action: str) -> None:
        """Dispatch an authorization-denied audit event for an approval action."""
        AuditEventDispatcher.dispatch(
            ApprovalDecisionDeniedEvent(
                approval_id=approval.id,
                execution_id=approval.execution_id,
                approval_node_id=approval.approval_node_id,
                user_id=self.user.id,
                username=self.user.username,
                action=action,
                principal_type=self.user.__dict__.get("__principal_type__"),
            )
        )

    async def _validate_execution_reference(self, execution_id: UUID, project_id: UUID) -> None:
        """Validate that the execution exists and belongs to the expected project.

        Raises:
            ExecutionNotFoundError: If the execution does not exist
            ValueError: If the execution's project_id does not match

        """
        from syntara.workflows.exceptions import ExecutionNotFoundError  # noqa: PLC0415
        from syntara.workflows.models.execution import Execution  # noqa: PLC0415

        execution = await self.session.get(Execution, execution_id)
        if execution is None:
            raise ExecutionNotFoundError(execution_id)
        if execution.project_id != project_id:
            msg = f"project_id {project_id} does not match execution's project {execution.project_id}"
            raise ValueError(msg)

    async def create(
        self,
        request: ApprovalCreateRequest,
    ) -> ApprovalRequestRead:
        """Create a new approval request.

        Args:
            request: Typed approval creation request

        Returns:
            Created approval request

        Raises:
            ExecutionNotFoundError: If the referenced execution does not exist
            ApprovalAlreadyRequestedError: If approval already exists for this execution and approval node

        Transaction Boundaries:
            This operation is fully atomic - approval creation and all junction table inserts
            occur within a single database transaction. If any FK constraint fails (invalid
            user_id or group_id), the entire transaction is rolled back, leaving no orphaned
            approval records. The transaction commits only when all operations succeed.

        """
        # Check if an approval already exists for this execution and approval node
        existing_approval = await self._get_approval_request(request.execution_id, request.approval_node_id)
        if existing_approval is not None:
            raise ApprovalAlreadyRequestedError(request.execution_id, request.approval_node_id)

        project_id = request.project_id
        await self._validate_execution_reference(request.execution_id, project_id)

        # Convert typed models to dicts for database storage
        next_step_approved_dict = (
            request.next_step_approved.model_dump(mode="json") if request.next_step_approved else None
        )
        next_step_rejected_dict = (
            request.next_step_rejected.model_dump(mode="json") if request.next_step_rejected else None
        )
        workflow_context_dict = request.workflow_context.model_dump(mode="json")

        approval = ApprovalRequest(
            execution_id=request.execution_id,
            approval_node_id=request.approval_node_id,
            name=request.name,
            project_id=project_id,
            status=ApprovalRequestStatus.PENDING,
            timeout_at=request.timeout_at,
            next_step_approved=next_step_approved_dict,
            next_step_rejected=next_step_rejected_dict,
            workflow_context=workflow_context_dict,
        )

        self.session.add(approval)
        await self.session.flush()  # Flush to get approval.id for junction tables

        # Populate approver user junction table
        # SECURITY: FK constraints validate UUIDs at database level. Invalid user_id raises
        # IntegrityError, which is caught below and mapped to ValueError (400). This indicates
        # a programming error (passing non-existent UUIDs), not normal user input. Approver
        # resolution happens upstream in the workflow engine, ensuring only valid UUIDs reach
        # this point under normal operation.
        if request.approver_user_ids:
            self.session.add_all(
                ApprovalApproverUser(approval_id=approval.id, user_id=user_id) for user_id in request.approver_user_ids
            )

        # Populate approver group junction table
        if request.approver_group_ids:
            self.session.add_all(
                ApprovalApproverGroup(approval_id=approval.id, group_id=group_id)
                for group_id in request.approver_group_ids
            )

        try:
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            error_msg = str(e).lower()
            # PostgreSQL error codes: 23505 = unique violation, 23503 = FK violation
            pgcode = getattr(e.orig, "pgcode", "")

            # Handle concurrent creation race condition (TOCTOU)
            # Check if it's a unique constraint violation on (execution_id, approval_node_id)
            if pgcode == "23505" and ("execution_id" in error_msg or "approval_node_id" in error_msg):
                raise ApprovalAlreadyRequestedError(request.execution_id, request.approval_node_id) from e

            # Handle FK constraint violations for approver UUIDs
            # These indicate invalid UUIDs were passed (should not happen in normal operation)
            if pgcode == "23503":
                if "approver_user" in error_msg or "user_id" in error_msg:
                    # Extract user_id from request to include in error
                    invalid_ids = request.approver_user_ids or []
                    msg = f"Invalid approver user ID(s): one or more user IDs do not exist. Provided IDs: {invalid_ids}"
                    raise ValueError(msg) from e
                if "approver_group" in error_msg or "group_id" in error_msg:
                    # Extract group_id from request to include in error
                    invalid_ids = request.approver_group_ids or []
                    msg = (
                        f"Invalid approver group ID(s): one or more group IDs do not exist. Provided IDs: {invalid_ids}"
                    )
                    raise ValueError(msg) from e

            # Re-raise if it's a different integrity error
            raise

        logger.info(
            "Created approval request",
            approval_id=approval.id,
            execution_id=request.execution_id,
            approval_node_id=request.approval_node_id,
        )

        AuditEventDispatcher.dispatch(
            ApprovalRequestedEvent(
                approval_id=approval.id,
                execution_id=request.execution_id,
                approval_node_id=request.approval_node_id,
                name=request.name,
                project_id=project_id,
                timeout_at=request.timeout_at,
            )
        )

        # Refresh the approval with eager-loaded relationships for convert_resource
        await self._refresh_approval_relationships(approval, include_decider=False)

        return cast("ApprovalRequestRead", self.convert_resource_mixin.convert_resource(approval))

    async def delete(
        self,
        approval_id: UUID,
    ) -> None:
        """Delete a pending approval request.

        Args:
            approval_id: UUID of the approval request

        Raises:
            ApprovalNotFoundError: If approval request not found
            ApprovalNotAuthorizedError: If the user is not authorized
            ApprovalAlreadyDecidedError: If approval is not in PENDING status

        """
        approval: ApprovalRequest | None = await self._get_approval_by_id(approval_id)
        if not approval:
            raise ApprovalNotFoundError(approval_id)

        if not await self._is_user_authorized_approver(approval, action="delete"):
            self._dispatch_authorization_denied(approval, action="delete")
            raise ApprovalNotAuthorizedError(approval_id, self.user.id)

        if approval.status != ApprovalRequestStatus.PENDING:
            raise ApprovalAlreadyDecidedError(approval_id, approval.status)

        # Atomic delete with status guard to prevent TOCTOU race with concurrent decide()
        stmt = (
            sa_delete(ApprovalRequest)
            .where(ApprovalRequest.id == approval_id)  # type: ignore[arg-type]
            .where(ApprovalRequest.status == ApprovalRequestStatus.PENDING)  # type: ignore[arg-type]
        )
        result = await self.session.exec(stmt)

        if result.rowcount == 0:
            await self.session.rollback()
            approval = await self._get_approval_by_id(approval_id)
            if approval:
                raise ApprovalAlreadyDecidedError(approval_id, approval.status)
            raise ApprovalNotFoundError(approval_id)

        await self.session.commit()

        logger.info(
            "Approval deleted",
            approval_id=approval_id,
            deleted_by=self.user.id,
        )

    async def decide(
        self,
        approval_id: UUID,
        request: ApprovalDecisionRequest,
    ) -> ApprovalRequestRead:
        """Make a decision on an approval request.

        Args:
            approval_id: UUID of the approval request
            request: Typed decision request with status and notes

        Returns:
            Updated approval request

        Raises:
            ApprovalNotFoundError: If approval request not found
            ApprovalAlreadyDecidedError: If approval already has a decision

        """
        # Get the approval request
        approval: ApprovalRequest | None = await self._get_approval_by_id(approval_id)
        if not approval:
            raise ApprovalNotFoundError(approval_id)

        # Check authorization BEFORE status to prevent information leakage
        # SECURITY: Unauthorized users should always get 403 Forbidden regardless of
        # approval state (pending vs already decided). Checking status first would leak
        # whether the approval has been decided via different exception types.
        if not await self._is_user_authorized_approver(approval):
            self._dispatch_authorization_denied(approval, action="decide")
            raise ApprovalNotAuthorizedError(approval_id, self.user.id)

        # Check if already decided
        if approval.status != ApprovalRequestStatus.PENDING:
            raise ApprovalAlreadyDecidedError(approval_id, approval.status)

        # Convert decision status enum to approval request status enum
        status_enum = ApprovalRequestStatus(request.status.value)
        decided_at = datetime.now(UTC)

        # SECURITY: Optimistic locking prevents TOCTOU race condition.
        # UPDATE with WHERE status=PENDING ensures only one concurrent decision succeeds.
        # If two users decide simultaneously, only the first UPDATE affects 1 row; the second
        # affects 0 rows. We detect this and raise AlreadyDecidedError for the loser.
        stmt = (
            update(ApprovalRequest)
            .where(ApprovalRequest.id == approval_id)  # type: ignore[arg-type]
            .where(ApprovalRequest.status == ApprovalRequestStatus.PENDING)  # type: ignore[arg-type]
            .values(
                status=status_enum,
                decided_by=self.user.id,
                decided_at=decided_at,
                decision_notes=request.notes,
            )
        )
        result = await self.session.exec(stmt)

        if result.rowcount == 0:
            # Approval was decided by another user between our check and this UPDATE
            await self.session.rollback()
            # Re-fetch to get current status for error message
            approval = await self._get_approval_by_id(approval_id)
            if approval:
                raise ApprovalAlreadyDecidedError(approval_id, approval.status)
            raise ApprovalNotFoundError(approval_id)

        await self.session.commit()

        # Refresh the in-memory object to reflect database state after UPDATE
        # This loads relationships needed by convert_resource
        await self._refresh_approval_relationships(approval)

        logger.info(
            "Approval decision made",
            approval_id=approval_id,
            status=status_enum.value,
            decided_by=self.user.id,
        )

        # Calculate wait time for audit event using the decided_at timestamp we set
        decided = decided_at.replace(tzinfo=None)
        created = approval.created_at.replace(tzinfo=None)
        wait_time_ms = int((decided - created).total_seconds() * 1000)
        AuditEventDispatcher.dispatch(
            ApprovalDecidedEvent(
                approval_id=approval_id,
                execution_id=approval.execution_id,
                approval_node_id=approval.approval_node_id,
                decision=status_enum.value,
                decided_by=self.user.id,
                decided_at=decided_at,
                wait_time_ms=wait_time_ms,
                decision_notes=request.notes,
                principal_type=self.user.__dict__.get("__principal_type__"),
            )
        )

        # Send signal to workflow engine (best-effort, never blocks the response)
        signal_error: str | None = None
        try:
            async with WorkflowApiClient() as client:
                await client.send_approval_signal(
                    execution_id=approval.execution_id,
                    approval_node_id=approval.approval_node_id,
                    decision=request.status,
                    approval_id=approval_id,
                    decided_by=self.user.username,
                    decided_at=(approval.decided_at or datetime.now(UTC)).isoformat(),
                    decision_notes=request.notes,
                )
        except Exception as e:  # noqa: BLE001
            signal_error = "Workflow signal delivery failed"
            logger.warning(
                "Failed to send approval signal",
                approval_id=approval_id,
                execution_id=approval.execution_id,
                error=str(e),
                exc_info=True,
            )

        # Eagerly load relationships to avoid lazy-load in async context
        await self._refresh_approval_relationships(approval)

        response = cast("ApprovalRequestRead", self.convert_resource_mixin.convert_resource(approval))
        response.signal_delivery_error = signal_error
        return response

    async def _process_single_decision(
        self,
        decision: BatchApprovalDecision,
        approvals: dict[UUID, ApprovalRequest],
    ) -> BatchApprovalResult:
        """Process a single approval decision.

        Args:
            decision: Single typed decision data
            approvals: Dictionary of approval objects by ID

        Returns:
            BatchApprovalResult for this decision

        """
        approval_id = decision.approval_id
        decision_status = decision.status
        notes = decision.notes

        approval = approvals.get(approval_id)
        if not approval:
            return BatchApprovalResult(
                approval_id=approval_id,
                success=False,
                error="Approval not found",
            )

        # Check authorization BEFORE status to prevent information leakage
        # SECURITY: Unauthorized users should always get the same error regardless of
        # approval state (pending vs already decided). Checking status first would leak
        # whether the approval has been decided via error message differences.
        if not await self._is_user_authorized_approver(approval):
            self._dispatch_authorization_denied(approval, action="decide")
            return BatchApprovalResult(
                approval_id=approval_id,
                success=False,
                error="Not authorized to decide this approval",
            )

        # Check if already decided
        # SECURITY: TOCTOU race condition handling - database transaction isolation ensures
        # only one decision commits per approval. Batch processing doesn't change isolation
        # semantics; each approval update is still atomic.
        if approval.status != ApprovalRequestStatus.PENDING:
            return BatchApprovalResult(
                approval_id=approval_id,
                success=False,
                error=f"Approval already {approval.status.value}",
            )

        # Convert decision status enum to approval request status enum
        try:
            status = ApprovalRequestStatus(decision_status.value)
        except ValueError:
            return BatchApprovalResult(
                approval_id=approval_id,
                success=False,
                error=f"Invalid status: {decision_status}",
            )

        # Update the approval
        approval.status = status
        approval.decided_by = self.user.id
        approval.decided_at = datetime.now(UTC)
        approval.decision_notes = notes

        logger.info(
            "Batch approval decision made",
            approval_id=approval_id,
            status=status.value,
            decided_by=self.user.id,
        )

        decided = (approval.decided_at or datetime.now(UTC)).replace(tzinfo=None)
        created = approval.created_at.replace(tzinfo=None)
        wait_time_ms = int((decided - created).total_seconds() * 1000)
        AuditEventDispatcher.dispatch(
            ApprovalDecidedEvent(
                approval_id=approval_id,
                execution_id=approval.execution_id,
                approval_node_id=approval.approval_node_id,
                decision=status.value,
                decided_by=self.user.id,
                decided_at=approval.decided_at,
                wait_time_ms=wait_time_ms,
                decision_notes=notes,
                principal_type=self.user.__dict__.get("__principal_type__"),
            )
        )

        return BatchApprovalResult(
            approval_id=approval_id,
            success=True,
            status=status,
            decided_at=approval.decided_at,
            decided_by=UserReference(id=self.user.id, name=self.user.display_name),
            decision_notes=notes,
        )

    async def _send_workflow_signals(
        self,
        results: Sequence[BatchApprovalResult],
        decisions: Sequence[BatchApprovalDecision],
        approvals: dict[UUID, ApprovalRequest],
    ) -> None:
        """Send workflow signals for successful decisions in parallel.

        Args:
            results: List of batch results
            decisions: List of typed decision data
            approvals: Dictionary of approval objects by ID

        """

        async def send_single_signal(workflow_client: WorkflowApiClient, decision: BatchApprovalDecision) -> None:
            """Send a single workflow signal with error handling."""
            try:
                approval_id = decision.approval_id
                approval = approvals[approval_id]
                await workflow_client.send_approval_signal(
                    execution_id=approval.execution_id,
                    approval_node_id=approval.approval_node_id,
                    decision=decision.status,
                    approval_id=approval_id,
                    decided_by=self.user.username,
                    decided_at=(approval.decided_at or datetime.now(UTC)).isoformat(),
                    decision_notes=decision.notes,
                )
            except Exception as e:
                logger.exception(
                    "Failed to send approval signal for batch decision",
                    approval_id=decision.approval_id,
                    error=str(e),
                )

        # Collect tasks for successful decisions with approved/rejected status only
        async with WorkflowApiClient() as client:
            tasks = [
                send_single_signal(client, decision)
                for result_obj, decision in zip(results, decisions, strict=False)
                if result_obj.success
                and decision.status in (BatchApprovalDecisionStatus.APPROVED, BatchApprovalDecisionStatus.REJECTED)
            ]

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    async def batch_decide(self, request: BatchApprovalRequest) -> BatchApprovalResponse:
        """Process multiple approval decisions in batch with row-level locking.

        Args:
            request: Typed batch approval request with decisions

        Returns:
            BatchApprovalResponse with individual results and counts

        Note:
            Uses row-level locking to prevent race conditions during batch operations.

        """
        results: list[BatchApprovalResult] = []
        approval_ids = [decision.approval_id for decision in request.decisions]

        # Fetch all approvals with row-level locking to prevent race conditions
        # Eager-load approver relationships for authorization checks
        query = (
            select(ApprovalRequest)
            .where(ApprovalRequest.id.in_(approval_ids))  # type: ignore[attr-defined]
            .options(*ApprovalService._approval_eager_loads(include_decider=False))
            .with_for_update()
        )
        result = await self.session.exec(query)
        approvals = {approval.id: approval for approval in result.all()}

        # Process each decision
        for decision in request.decisions:
            try:
                result_obj = await self._process_single_decision(decision, approvals)
                results.append(result_obj)
            except Exception as e:
                logger.exception(
                    "Failed to process approval decision",
                    approval_id=decision.approval_id,
                    error=str(e),
                )
                results.append(
                    BatchApprovalResult(
                        approval_id=decision.approval_id,
                        success=False,
                        error=str(e),
                    )
                )

        # Commit all changes at once
        await self.session.commit()

        # Send workflow signals for successful decisions
        await self._send_workflow_signals(results, request.decisions, approvals)

        # Calculate totals and return response
        total_success = sum(1 for r in results if r.success)
        total_failed = len(results) - total_success

        return BatchApprovalResponse(
            results=results,
            total_success=total_success,
            total_failed=total_failed,
        )
