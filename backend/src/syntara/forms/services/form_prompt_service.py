"""Service layer for form prompt operations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select, update

if TYPE_CHECKING:
    from collections.abc import Iterable
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.authz.engine import AllowedProjectsResult
    from syntara.core.models import User

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.core.models.user_reference import UserReference
from syntara.core.services.base import BaseService
from syntara.forms.audit.form_prompt import FormPromptSubmittedEvent
from syntara.forms.exceptions import (
    FormPromptAlreadyRequestedError,
    FormPromptAlreadyRespondedError,
    FormPromptNotFoundError,
    InvalidResponderReferenceError,
)
from syntara.forms.models.api_models import (
    BatchFormPromptRequest,
    BatchUpdateResponse,
    BatchUpdateResult,
    FormPromptCreateRequest,
    FormPromptStatus,
    FormPromptSummary,
    ResponderGroupSummary,
    ResponderUserSummary,
    can_transition,
)
from syntara.forms.models.form_prompt import FormPrompt, FormPromptListResponse, FormPromptRead
from syntara.forms.models.form_prompt_responders import FormPromptResponderGroup, FormPromptResponderUser
from syntara.forms.validators.submission import validate_form_submission, validate_prompt_submission_state
from syntara.workflows.exceptions import ExecutionNotFoundError
from syntara.workflows.models.execution import Execution

logger = structlog.stdlib.get_logger(__name__)


class FormPromptService(BaseService):
    """Service for managing form prompts.

    Service covering workflow engine needs:
    - create: atomically create form_prompts row + responder junctions
    - list: fetch prompts with pagination and filtering
    - batch_update_status: update prompt statuses (expire/cancel)
    - submit: validate and persist form submission, send workflow signal
    """

    def __init__(
        self,
        session: AsyncSession,
        user: User,
    ) -> None:
        """Initialize service with database session and user context.

        Args:
            session: SQLAlchemy async session
            user: Current authenticated user or service principal

        """
        super().__init__(session=session, user=user)

    def _map_fk_error_to_domain_exception(
        self,
        error_str: str,
        request: FormPromptCreateRequest,
    ) -> InvalidResponderReferenceError | None:
        """Map foreign key violation to domain exception.

        Args:
            error_str: String representation of the IntegrityError
            request: The create request containing responder IDs

        Returns:
            InvalidResponderReferenceError if FK violation detected, None otherwise

        """
        # FK violations on responder tables
        if "form_prompt_responder_users" in error_str and "user_id" in error_str:
            # Extract UUID from error message if possible, otherwise use first ID
            invalid_id = request.responder_user_ids[0] if request.responder_user_ids else None
            if invalid_id:
                entity_type = "user"
                return InvalidResponderReferenceError(entity_type, invalid_id)

        if "form_prompt_responder_groups" in error_str and "group_id" in error_str:
            # Extract UUID from error message if possible, otherwise use first ID
            invalid_id = request.responder_group_ids[0] if request.responder_group_ids else None
            if invalid_id:
                entity_type = "group"
                return InvalidResponderReferenceError(entity_type, invalid_id)

        return None

    async def _validate_execution_project(self, request: FormPromptCreateRequest) -> None:
        execution = await self.session.get(Execution, request.execution_id)
        if execution is None:
            raise ExecutionNotFoundError(request.execution_id)
        if execution.project_id != request.project_id:
            msg = f"project_id {request.project_id} does not match execution's project {execution.project_id}"
            raise ValueError(msg)

    async def create(self, request: FormPromptCreateRequest) -> FormPromptSummary:
        """Create a new form prompt.

        Args:
            request: Form prompt creation request

        Returns:
            Created form prompt summary

        Raises:
            FormPromptAlreadyRequestedError: If a prompt for this already exists

        """
        await self._validate_execution_project(request)

        try:
            # Create the prompt
            form_prompt = FormPrompt(
                execution_id=request.execution_id,
                project_id=request.project_id,
                prompt_node_id=request.prompt_node_id,
                name=request.name,
                message=request.message,
                loop_iteration_path=request.loop_iteration_path,
                temporal_activity_id=request.temporal_activity_id,
                timeout_at=request.timeout_at,
                form_definition=request.form_definition,
                submit_label=request.submit_label,
                success_message=request.success_message,
                timezone=request.timezone,
                css_override=request.css_override,
                status=FormPromptStatus.PENDING,
            )
            self.session.add(form_prompt)
            await self.session.flush()  # Trigger constraint check

            # Add responder junctions
            if request.responder_user_ids:
                for user_id in request.responder_user_ids:
                    responder_user = FormPromptResponderUser(
                        form_prompt_id=form_prompt.id,
                        user_id=user_id,
                    )
                    self.session.add(responder_user)

            if request.responder_group_ids:
                for group_id in request.responder_group_ids:
                    responder_group = FormPromptResponderGroup(
                        form_prompt_id=form_prompt.id,
                        group_id=group_id,
                    )
                    self.session.add(responder_group)

            await self.session.commit()

            logger.info(
                "Created form prompt",
                prompt_id=form_prompt.id,
                execution_id=request.execution_id,
                prompt_node_id=request.prompt_node_id,
            )

            # Return summary for internal workflow engine endpoints
            return FormPromptSummary.model_validate(form_prompt)

        except IntegrityError as e:
            await self.session.rollback()
            error_str = str(e)

            # Map database constraint violations to domain errors
            if "uix_execution_prompt_node_path" in error_str:
                raise FormPromptAlreadyRequestedError(
                    request.execution_id,
                    request.prompt_node_id,
                    request.loop_iteration_path,
                ) from e

            # Map FK violations to domain exceptions
            fk_error = self._map_fk_error_to_domain_exception(error_str, request)
            if fk_error:
                raise fk_error from e

            # Unexpected integrity errors - abort transaction
            raise
        except Exception:
            await self.session.rollback()
            raise

    async def list(
        self,
        limit: int = 20,
        cursor: str | None = None,
        sort: str | None = None,
        query_params_items: Iterable[tuple[str, str]] | None = None,
        *,
        include_total: bool = False,
        allowed_projects: AllowedProjectsResult | None = None,
    ) -> FormPromptListResponse:
        """List form prompts with filtering, sorting, and pagination.

        Args:
            limit: Maximum number of form prompts to return (default 20)
            cursor: Cursor token for pagination
            sort: Sort parameter (e.g., "name", "-created_at")
            query_params_items: Raw query parameter items from request (for filtering)
            include_total: Whether to include total count in response
            allowed_projects: Project scope filter from authorization

        Returns:
            FormPromptListResponse with form prompts, pagination metadata, and optional total

        """
        return await self.list_resources(
            model=FormPrompt,
            response_type=FormPromptListResponse,
            limit=limit,
            cursor=cursor,
            sort=sort,
            query_params_items=query_params_items,
            include_total=include_total,
            allowed_projects=allowed_projects,
        )

    async def get(self, prompt_id: UUID) -> FormPromptRead:
        """Get a single form prompt by ID.

        Args:
            prompt_id: UUID of the form prompt

        Returns:
            The form prompt with responder and submitter details

        Raises:
            FormPromptNotFoundError: If the form prompt does not exist

        """
        query = (
            select(FormPrompt)
            .where(FormPrompt.id == prompt_id)
            .options(
                selectinload(FormPrompt.responder),  # type: ignore[arg-type]
                selectinload(FormPrompt.responder_user_records),  # type: ignore[arg-type]
                selectinload(FormPrompt.responder_group_records),  # type: ignore[arg-type]
            )
        )
        result = await self.session.exec(query)
        form_prompt = result.one_or_none()
        if form_prompt is None:
            raise FormPromptNotFoundError(prompt_id)

        read = FormPromptRead.model_validate(
            form_prompt.model_dump(
                exclude={"responded_by", "responder_user_records", "responder_group_records", "responder"}
            )
        )
        read.responder_users = [
            ResponderUserSummary(id=user.id, username=user.username) for user in form_prompt.responder_user_records
        ]
        read.responder_groups = [
            ResponderGroupSummary(id=group.id, name=group.name) for group in form_prompt.responder_group_records
        ]
        if form_prompt.responded_by is not None:
            responder = form_prompt.responder
            read.responded_by = UserReference(
                id=form_prompt.responded_by,
                name=responder.display_name if responder is not None else "",
            )

        return read

    async def batch_update_status(self, request: BatchFormPromptRequest) -> BatchUpdateResponse:
        """Batch update form prompt statuses with concurrency safety and project scoping.

        Uses conditional UPDATE to prevent race conditions - only updates prompts that are
        in a valid source status for the transition. Enforces project-level authorization.

        Args:
            request: Batch update request

        Returns:
            Typed batch update response with results and counts

        """
        results: list[BatchUpdateResult] = []
        success_count = 0
        failed_count = 0

        # Load all prompts to check existence and current status
        prompt_ids = [update_request.prompt_id for update_request in request.updates]
        query = select(FormPrompt).where(FormPrompt.id.in_(prompt_ids))  # type: ignore[attr-defined]
        result = await self.session.exec(query)
        prompts_by_id = {p.id: p for p in result.all()}

        for update_request in request.updates:
            prompt = prompts_by_id.get(update_request.prompt_id)
            if prompt is None:
                results.append(
                    BatchUpdateResult(
                        prompt_id=str(update_request.prompt_id),
                        success=False,
                        error="Form prompt not found",
                    )
                )
                failed_count += 1
                continue

            # Check current status and transition validity
            current_status = FormPromptStatus(prompt.status)
            target_status = FormPromptStatus(update_request.status.value)

            if not can_transition(current_status, target_status):
                # Idempotent: if already at target status, treat as success
                if current_status == target_status:
                    results.append(
                        BatchUpdateResult(
                            prompt_id=str(update_request.prompt_id),
                            success=True,
                            message=f"Already {target_status.value}",
                        )
                    )
                    success_count += 1
                else:
                    results.append(
                        BatchUpdateResult(
                            prompt_id=str(update_request.prompt_id),
                            success=False,
                            error=f"Cannot transition from {current_status.value} to {target_status.value}",
                        )
                    )
                    failed_count += 1
                continue

            # SECURITY: Conditional UPDATE prevents race conditions.
            # Only updates prompts still in the expected current status.
            # If status changed between check and update, rowcount will be 0.
            update_values: dict[str, Any] = {"status": target_status}
            if update_request.notes is not None:
                update_values["notes"] = update_request.notes

            stmt = (
                update(FormPrompt)
                .where(FormPrompt.id == update_request.prompt_id)  # type: ignore[arg-type]
                .where(FormPrompt.status == current_status)  # type: ignore[arg-type]
                .values(**update_values)
            )

            update_result = await self.session.exec(stmt)
            affected_rows = update_result.rowcount

            if affected_rows == 0:
                # Status changed between check and update (race condition)
                results.append(
                    BatchUpdateResult(
                        prompt_id=str(update_request.prompt_id),
                        success=False,
                        error=f"Status changed (was {current_status.value}, concurrent update detected)",
                    )
                )
                failed_count += 1
            else:
                results.append(
                    BatchUpdateResult(
                        prompt_id=str(update_request.prompt_id),
                        success=True,
                    )
                )
                success_count += 1

        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

        logger.info(
            "Batch updated form prompt statuses",
            total=len(request.updates),
            success=success_count,
            failed=failed_count,
        )

        return BatchUpdateResponse(
            results=results,
            total_success=success_count,
            total_failed=failed_count,
        )

    async def submit(
        self,
        prompt_id: UUID,
        submitted_data: dict[str, Any],
    ) -> FormPrompt:
        """Submit a response to a form prompt.

        Validates the submission, persists it to the database, and sends a signal
        to the workflow engine to resume the paused workflow.

        Args:
            prompt_id: Form prompt ID
            submitted_data: Raw submitted form data

        Returns:
            Updated form prompt with response data

        Raises:
            FormPromptNotFoundError: If prompt does not exist
            FormPromptExpiredError: If prompt has expired
            FormPromptCancelledError: If prompt has been cancelled
            FormPromptAlreadyRespondedError: If prompt already has a response
            FormDataValidationError: If form data fails validation

        """
        # Load the prompt, validate its state, then validate the submitted fields.
        prompt = await self.session.get(FormPrompt, prompt_id)
        if prompt is None:
            raise FormPromptNotFoundError(prompt_id)

        validate_prompt_submission_state(prompt)
        cleaned_data = validate_form_submission(prompt.form_definition, submitted_data)

        logger.info(
            "Validated form submission",
            prompt_id=prompt_id,
            field_count=len(cleaned_data),
        )

        responded_at = datetime.now(UTC)

        # SECURITY: Optimistic locking prevents TOCTOU race condition.
        # UPDATE with WHERE status=PENDING ensures only one concurrent submission succeeds.
        stmt = (
            update(FormPrompt)
            .where(FormPrompt.id == prompt_id)  # type: ignore[arg-type]
            .where(FormPrompt.status == FormPromptStatus.PENDING)  # type: ignore[arg-type]
            .values(
                status=FormPromptStatus.SUBMITTED,
                response_data=cleaned_data,
                responded_by=self.user.id,
                responded_at=responded_at,
            )
        )
        result = await self.session.exec(stmt)
        rowcount = result.rowcount

        if rowcount == 0:
            # Prompt was submitted by another user between our check and this UPDATE
            await self.session.rollback()
            # Re-fetch to get current status for error message
            prompt = await self.session.get(FormPrompt, prompt_id)
            if prompt:
                raise FormPromptAlreadyRespondedError(prompt_id, prompt.status)
            raise FormPromptNotFoundError(prompt_id)

        await self.session.commit()

        # Refresh to get the updated state
        await self.session.refresh(prompt)

        # Calculate wait time for telemetry
        submitted = responded_at.replace(tzinfo=None)
        created = prompt.created_at.replace(tzinfo=None)
        wait_time_ms = int((submitted - created).total_seconds() * 1000)

        logger.info(
            "Form prompt submitted",
            prompt_id=prompt_id,
            execution_id=prompt.execution_id,
            responded_by=self.user.id,
            field_count=len(cleaned_data),
            wait_time_ms=wait_time_ms,
        )

        # Send signal to workflow engine (best-effort, never blocks the response)
        signal_error: str | None = None
        try:
            from syntara.forms.clients.workflow_client import WorkflowApiClient  # noqa: PLC0415

            async with WorkflowApiClient() as client:
                await client.send_form_signal(
                    execution_id=prompt.execution_id,
                    form_prompt_id=prompt.prompt_node_id,
                    form_response={
                        "outcome": "submitted",
                        "response_data": cleaned_data,
                        "responded_by": self.user.username,
                        "responded_at": responded_at.isoformat(),
                        "prompt_id": str(prompt_id),
                    },
                    temporal_activity_id=prompt.temporal_activity_id,
                )
        except Exception as e:  # noqa: BLE001
            signal_error = "Workflow signal delivery failed"
            logger.warning(
                "Failed to send form submission signal",
                prompt_id=prompt_id,
                execution_id=prompt.execution_id,
                error=str(e),
                exc_info=True,
            )

        # Emit audit event with telemetry data
        AuditEventDispatcher.dispatch(
            FormPromptSubmittedEvent(
                prompt_id=prompt_id,
                execution_id=prompt.execution_id,
                prompt_node_id=prompt.prompt_node_id,
                submitted_by=self.user.id,
                submitted_at=responded_at,
                wait_time_ms=wait_time_ms,
                field_count=len(cleaned_data),
                outcome="submitted",
                principal_type=self.user.__dict__.get("__principal_type__"),
            )
        )

        # Store the error as transient response metadata (not persisted to DB).
        if signal_error:
            prompt.signal_delivery_error = signal_error
            logger.error("Signal delivery failed", prompt_id=prompt_id, error=signal_error)

        return prompt
