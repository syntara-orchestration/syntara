"""Service layer for form prompt operations."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from sqlalchemy import asc, desc, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select, update

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy import Select
    from sqlmodel.ext.asyncio.session import AsyncSession
    from sqlmodel.sql._expression_select_cls import SelectOfScalar

    from syntara.authz.engine import AllowedProjectsResult
    from syntara.core.models import User

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.core.models.user_reference import UserReference, UserReferenceType
from syntara.core.services import BaseService, GroupMembershipService
from syntara.core.services.extensions import EnrichQueryMixin
from syntara.core.services.user_reference_resolution import DELETED_USER_NAME, UserReferenceResolverMixin
from syntara.core.utils.cursor import (
    SortDirection,
    decode_cursor,
    deserialize_column_sort_value,
    extract_keyset_from_cursor,
)
from syntara.core.utils.pagination import PaginationResult, generate_response
from syntara.core.utils.sorting import parse_sort
from syntara.forms.audit.form_prompt import (
    FormPromptCreatedEvent,
    FormPromptExpiredEvent,
    FormPromptSubmittedEvent,
)
from syntara.forms.exceptions import (
    FormPromptAlreadyRequestedError,
    FormPromptAlreadyRespondedError,
    FormPromptNotAuthorizedError,
    FormPromptNotFoundError,
    InvalidResponderReferenceError,
)
from syntara.forms.models.api_models import (
    BatchFormPromptRequest,
    BatchFormPromptUpdate,
    BatchUpdateResponse,
    BatchUpdateResult,
    FormPromptCreateRequest,
    FormPromptStatus,
    FormPromptSummary,
    ResponderGroupSummary,
    ResponderUserSummary,
    can_transition,
)
from syntara.forms.models.form_prompt import FormPrompt, FormPromptListRead, FormPromptListResponse, FormPromptRead
from syntara.forms.models.form_prompt_responders import FormPromptResponderGroup, FormPromptResponderUser
from syntara.forms.validators.submission import validate_form_submission, validate_prompt_submission_state
from syntara.metrics.dependencies import get_metrics_recorder
from syntara.metrics.types import ComponentLabel, MetricType
from syntara.workflows.exceptions import ExecutionNotFoundError
from syntara.workflows.models.execution import Execution
from syntara.workflows.models.workflow import Workflow

logger = structlog.stdlib.get_logger(__name__)


class FormPromptEnrichQuery(EnrichQueryMixin):
    """Eagerly load responder for list conversion and user-reference resolution."""

    def enrich(  # type: ignore[override]
        self,
        query: Select[tuple[FormPrompt]] | SelectOfScalar[tuple[FormPrompt]],
    ) -> Select[tuple[FormPrompt]] | SelectOfScalar[tuple[FormPrompt]]:
        """Add selectinload for the responder relationship."""
        return query.options(
            selectinload(FormPrompt.responder),  # type: ignore[arg-type]
        )


class FormPromptService(UserReferenceResolverMixin, BaseService):
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
        super().__init__(
            session=session,
            user=user,
            enrich_query_mixin=FormPromptEnrichQuery(),
        )

    async def _get_form_prompt_record(self, prompt_id: UUID) -> FormPrompt | None:
        """Fetch a prompt with relationships required by ``FormPromptRead`` eagerly loaded."""
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
        return result.one_or_none()

    async def _validate_responder(self, prompt: FormPrompt) -> None:
        """Ensure the current user is configured to respond to this prompt."""
        responder_users = prompt.responder_user_records
        responder_groups = prompt.responder_group_records

        # Empty responder lists preserve the permission-based fallback.
        if not responder_users and not responder_groups:
            return

        if self.user.id in {responder.id for responder in responder_users}:
            return

        if responder_groups and await GroupMembershipService(self.session).is_user_in_any_group_by_ids(
            user_id=self.user.id,
            group_ids=[group.id for group in responder_groups],
        ):
            return

        raise FormPromptNotAuthorizedError(prompt.id, self.user.id)

    @staticmethod
    def _to_read_model(prompt: FormPrompt, *, signal_delivery_error: str | None = None) -> FormPromptRead:
        """Convert a prompt with loaded relationships to its API response model."""
        read = FormPromptRead.model_validate(
            prompt.model_dump(
                exclude={
                    "responded_by",
                    "responder_user_records",
                    "responder_group_records",
                    "responder",
                    "temporal_activity_id",
                }
            )
        )
        read.responder_users = [
            ResponderUserSummary(id=user.id, username=user.username) for user in prompt.responder_user_records
        ]
        read.responder_groups = [
            ResponderGroupSummary(id=group.id, name=group.name) for group in prompt.responder_group_records
        ]
        if prompt.responded_by is not None:
            responder = prompt.responder
            read.responded_by = (
                UserReference(id=prompt.responded_by, name=responder.display_name, type=UserReferenceType.USER)
                if responder is not None
                else UserReference(id=prompt.responded_by, name=DELETED_USER_NAME, type=UserReferenceType.DELETED_USER)
            )
        read.signal_delivery_error = signal_delivery_error
        return read

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

    async def _validate_execution_project(self, request: FormPromptCreateRequest) -> Execution:
        execution = await self.session.get(Execution, request.execution_id)
        if execution is None:
            raise ExecutionNotFoundError(request.execution_id)
        if execution.project_id != request.project_id:
            msg = f"project_id {request.project_id} does not match execution's project {execution.project_id}"
            raise ValueError(msg)
        return execution

    async def create(self, request: FormPromptCreateRequest) -> FormPromptSummary:
        """Create a new form prompt.

        Args:
            request: Form prompt creation request

        Returns:
            Created form prompt summary

        Raises:
            FormPromptAlreadyRequestedError: If a prompt for this already exists

        """
        execution = await self._validate_execution_project(request)

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

            # Stage the business audit record in this transaction so the prompt
            # and its lifecycle event commit or roll back together.
            AuditEventDispatcher.dispatch(
                FormPromptCreatedEvent(
                    prompt_id=form_prompt.id,
                    workflow_id=execution.workflow_id,
                    execution_id=request.execution_id,
                    prompt_node_id=request.prompt_node_id,
                    initiated_by=execution.created_by,
                    created_at=form_prompt.created_at,
                ),
                # AuditEventDispatcher is typed for sync Session; the transactional outbox only calls
                # add(), which AsyncSession also supports synchronously.
                session=self.session,  # type: ignore[arg-type]
            )

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

    def _apply_sorting(
        self,
        query: Select[tuple[FormPrompt]] | SelectOfScalar[tuple[FormPrompt]],
        sort: str | None,
        model: type[FormPrompt],
        *,
        reverse_for_backward: bool = False,
    ) -> tuple[
        Select[tuple[FormPrompt]] | SelectOfScalar[tuple[FormPrompt]],
        str,
        SortDirection,
    ]:
        """Sort by workflow name via execution → workflow join."""
        sort_field, sort_direction = parse_sort(sort, model.__sortable_fields__)
        if sort_field != "workflow_name":
            return super()._apply_sorting(
                query,
                sort,
                model,
                reverse_for_backward=reverse_for_backward,
            )

        actual_sort_direction = sort_direction
        if reverse_for_backward:
            actual_sort_direction = SortDirection.ASC if sort_direction == SortDirection.DESC else SortDirection.DESC

        query = query.join(Execution, FormPrompt.execution_id == Execution.id)
        query = query.join(Workflow, Execution.workflow_id == Workflow.id)
        name_col = Workflow.name
        id_col = FormPrompt.id
        if actual_sort_direction == SortDirection.ASC:
            query = query.order_by(asc(name_col), asc(id_col))
        else:
            query = query.order_by(desc(name_col), desc(id_col))
        return query, sort_field, sort_direction

    def _apply_cursor_pagination(
        self,
        query: Select[tuple[FormPrompt]] | SelectOfScalar[tuple[FormPrompt]],
        cursor: str | None,
        sort_field: str,
        sort_direction: SortDirection,
        model: type[FormPrompt],
    ) -> tuple[
        Select[tuple[FormPrompt]] | SelectOfScalar[tuple[FormPrompt]],
        bool,
    ]:
        """Keyset pagination for workflow name sort uses Workflow.name."""
        if sort_field != "workflow_name":
            return super()._apply_cursor_pagination(
                query,
                cursor,
                sort_field,
                sort_direction,
                model,
            )

        if not cursor:
            return query, False

        needs_reverse = False
        cursor_data = decode_cursor(cursor)
        cursor_sort_field, cursor_sort_value, resource_id, created_at, direction = extract_keyset_from_cursor(
            cursor_data
        )

        use_sort_col = (
            cursor_sort_value is not None
            and cursor_sort_field is not None
            and cursor_sort_field != "created_at"
            and cursor_sort_field == sort_field
        )

        if resource_id:
            try:
                cursor_id = UUID(resource_id)
            except ValueError:
                return query, needs_reverse

            if use_sort_col:
                sort_col = Workflow.name
                cursor_sv = deserialize_column_sort_value(str(cursor_sort_value), sort_col)
                query, needs_reverse = self._apply_keyset_filter(
                    query,
                    sort_col,
                    cursor_sv,
                    FormPrompt.id,
                    cursor_id,
                    sort_direction,
                    direction,
                )
            elif created_at:
                try:
                    cursor_timestamp = datetime.fromisoformat(created_at)
                except ValueError:
                    return query, needs_reverse
                query, needs_reverse = self._apply_keyset_filter(
                    query,
                    FormPrompt.created_at,
                    cursor_timestamp,
                    FormPrompt.id,
                    cursor_id,
                    sort_direction,
                    direction,
                )

        return query, needs_reverse

    async def _workflow_names_for_prompts(self, prompts: list[FormPrompt]) -> dict[UUID, str]:
        if not prompts:
            return {}
        execution_ids = {prompt.execution_id for prompt in prompts}
        execution_result = await self.session.exec(
            select(Execution)
            .where(Execution.id.in_(execution_ids))  # type: ignore[attr-defined]
            .options(selectinload(Execution.workflow))  # type: ignore[arg-type]
        )
        executions = {execution.id: execution for execution in execution_result.all()}
        names: dict[UUID, str] = {}
        for prompt in prompts:
            execution = executions.get(prompt.execution_id)
            workflow = execution.workflow if execution is not None else None
            names[prompt.id] = workflow.name if workflow is not None else ""
        return names

    async def _fetch_and_paginate(
        self,
        query: Select[tuple[FormPrompt]] | SelectOfScalar[tuple[FormPrompt]],
        model: type[FormPrompt],
        query_params: dict[str, str],
        filter_context: tuple,
        sort: str | None,
        cursor: str | None,
        limit: int,
        *,
        include_total: bool,
        is_backward: bool,
        special_field_handlers: dict[str, Any] | None,
        allowed_projects: AllowedProjectsResult | None,
        id_restriction: list[UUID] | None = None,
        sort_context: tuple[str, SortDirection] = ("created_at", SortDirection.DESC),
    ) -> tuple[list[FormPrompt], PaginationResult]:
        sort_field_name, sort_direction = sort_context
        if sort_field_name != "workflow_name":
            return await super()._fetch_and_paginate(
                query,
                model,
                query_params,
                filter_context,
                sort,
                cursor,
                limit,
                include_total=include_total,
                is_backward=is_backward,
                special_field_handlers=special_field_handlers,
                allowed_projects=allowed_projects,
                id_restriction=id_restriction,
                sort_context=sort_context,
            )

        filters, label_filters = filter_context
        result = await self.session.exec(query)  # type: ignore[arg-type]
        resources = list(result.all())

        if is_backward:
            resources.reverse()

        total_count = None
        if include_total:
            total_count = await self._get_total_count(
                filters,
                model,
                special_field_handlers,
                label_filters,
                allowed_projects,
                id_restriction=id_restriction,
            )

        is_first_page = False
        if is_backward and len(resources) > 0:
            has_items_before = await self._check_has_items_before(
                first_item=resources[0],
                query_params=query_params,
                filters=filters,
                sort=sort,
                model=model,
                special_field_handlers=special_field_handlers,
                allowed_projects=allowed_projects,
            )
            is_first_page = not has_items_before

        workflow_names = await self._workflow_names_for_prompts(resources)

        pagination = generate_response(
            items=resources,
            limit=limit,
            cursor=cursor,
            include_total=include_total,
            total_count=total_count,
            is_first_page=is_first_page,
            sort_field=sort_field_name,
            sort_direction=sort_direction,
            sort_value_fn=lambda item: workflow_names.get(item.id, ""),
        )

        trimmed: list[FormPrompt] = pagination["trimmed_items"]  # type: ignore[assignment]
        return trimmed, pagination

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
        executions_by_id: dict[UUID, Execution] = {}

        async def _fetch_executions(prompts: list[FormPrompt]) -> None:
            if not prompts:
                return
            execution_ids = {prompt.execution_id for prompt in prompts}
            execution_result = await self.session.exec(
                select(Execution)
                .where(Execution.id.in_(execution_ids))  # type: ignore[attr-defined]
                .options(
                    selectinload(Execution.workflow),  # type: ignore[arg-type]
                    selectinload(Execution.workflow_version),  # type: ignore[arg-type]
                )
            )
            executions_by_id.clear()
            executions_by_id.update({execution.id: execution for execution in execution_result.all()})

        def _to_list_read(prompt: FormPrompt) -> FormPromptListRead:
            execution = executions_by_id.get(prompt.execution_id)
            workflow_id: UUID | None = None
            workflow_version: int | None = None
            workflow_name: str | None = None
            if execution is not None:
                workflow_id = execution.workflow_id
                workflow = execution.workflow
                workflow_name = workflow.name if workflow is not None else None
                version_record = execution.workflow_version
                if version_record is not None:
                    workflow_version = version_record.version

            list_read = FormPromptListRead(
                id=prompt.id,
                created_at=prompt.created_at,
                execution_id=prompt.execution_id,
                project_id=prompt.project_id,
                prompt_node_id=prompt.prompt_node_id,
                name=prompt.name,
                status=prompt.status,
                timeout_at=prompt.timeout_at,
                responded_at=prompt.responded_at,
                workflow_id=workflow_id,
                workflow_version=workflow_version,
                workflow_name=workflow_name or "Unknown",
            )
            if prompt.responded_by is not None:
                list_read.responded_by = UserReference(
                    id=prompt.responded_by,
                    name="",
                    type=UserReferenceType.USER,
                )
            return list_read

        return await self.list_resources(
            model=FormPrompt,
            response_type=FormPromptListResponse,
            response_type_converter=_to_list_read,
            post_query_callback=_fetch_executions,
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
        form_prompt = await self._get_form_prompt_record(prompt_id)
        if form_prompt is None:
            raise FormPromptNotFoundError(prompt_id)
        return self._to_read_model(form_prompt)

    async def _apply_prompt_status_update(
        self,
        update_request: BatchFormPromptUpdate,
        prompt: FormPrompt | None,
        execution: Execution | None,
    ) -> tuple[BatchUpdateResult, bool, FormPromptExpiredEvent | None]:
        """Apply one guarded status transition and build its expiry event if changed."""
        if prompt is None:
            return (
                BatchUpdateResult(
                    prompt_id=str(update_request.prompt_id), success=False, error="Form prompt not found"
                ),
                False,
                None,
            )

        target_status_value = update_request.status.value
        if prompt.status == target_status_value:
            return (
                BatchUpdateResult(
                    prompt_id=str(update_request.prompt_id),
                    success=True,
                    message=f"Already {target_status_value}",
                ),
                True,
                None,
            )

        current_status = FormPromptStatus(prompt.status)
        target_status = FormPromptStatus(target_status_value)
        if not can_transition(current_status, target_status):
            return (
                BatchUpdateResult(
                    prompt_id=str(update_request.prompt_id),
                    success=False,
                    error=f"Cannot transition from {current_status.value} to {target_status.value}",
                ),
                False,
                None,
            )

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
        if update_result.rowcount == 0:
            return (
                BatchUpdateResult(
                    prompt_id=str(update_request.prompt_id),
                    success=False,
                    error=f"Status changed (was {current_status.value}, concurrent update detected)",
                ),
                False,
                None,
            )

        expired_event = None
        if target_status == FormPromptStatus.EXPIRED:
            # execution_id is a soft reference; if its execution was hard-deleted,
            # expiry still succeeds but the audit event has no workflow/user context.
            expired_event = FormPromptExpiredEvent(
                prompt_id=prompt.id,
                workflow_id=execution.workflow_id if execution is not None else None,
                execution_id=prompt.execution_id,
                prompt_node_id=prompt.prompt_node_id,
                initiated_by=execution.created_by if execution is not None else None,
                expired_at=datetime.now(UTC),
                timeout_at=prompt.timeout_at,
            )
        return BatchUpdateResult(prompt_id=str(update_request.prompt_id), success=True), True, expired_event

    async def batch_update_status(self, request: BatchFormPromptRequest) -> BatchUpdateResponse:
        """Batch update form prompt statuses with concurrency safety and project scoping.

        Uses conditional UPDATE to prevent race conditions - only updates prompts that are
        in a valid source status for the transition. Enforces project-level authorization.

        Args:
            request: Batch update request

        Returns:
            Typed batch update response with results and counts

        """
        prompt_ids = [update_request.prompt_id for update_request in request.updates]
        query = select(FormPrompt).where(FormPrompt.id.in_(prompt_ids))  # type: ignore[attr-defined]
        result = await self.session.exec(query)
        prompts_by_id = {p.id: p for p in result.all()}
        expiring_prompt_ids = {
            item.prompt_id for item in request.updates if item.status.value == FormPromptStatus.EXPIRED.value
        }
        execution_ids = {
            prompts_by_id[prompt_id].execution_id for prompt_id in expiring_prompt_ids if prompt_id in prompts_by_id
        }
        executions_by_id: dict[UUID, Execution] = {}
        if execution_ids:
            execution_result = await self.session.exec(
                select(Execution).where(Execution.id.in_(execution_ids))  # type: ignore[attr-defined]
            )
            executions_by_id = {execution.id: execution for execution in execution_result.all()}

        results: list[BatchUpdateResult] = []
        expired_events: list[FormPromptExpiredEvent] = []
        success_count = 0
        failed_count = 0
        for update_request in request.updates:
            prompt = prompts_by_id.get(update_request.prompt_id)
            execution = executions_by_id.get(prompt.execution_id) if prompt is not None else None
            update_result, succeeded, expired_event = await self._apply_prompt_status_update(
                update_request,
                prompt,
                execution,
            )
            results.append(update_result)
            if succeeded:
                success_count += 1
            else:
                failed_count += 1
            if expired_event is not None:
                expired_events.append(expired_event)

        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

        # Emit from the state-transition path after commit: the workflow activity only
        # has a pre-update snapshot, while this path can exclude retries and failed updates.
        for expired_event in expired_events:
            AuditEventDispatcher.dispatch(expired_event)

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
    ) -> FormPromptRead:
        """Submit a response to a form prompt.

        Validates the submission, persists it to the database, and sends a signal
        to the workflow engine to resume the paused workflow.

        Args:
            prompt_id: Form prompt ID
            submitted_data: Raw submitted form data

        Returns:
            Updated form prompt read model with response data and signal status

        Raises:
            FormPromptNotFoundError: If prompt does not exist
            FormPromptNotAuthorizedError: If the current user is not a configured responder
            FormPromptExpiredError: If prompt has expired
            FormPromptCancelledError: If prompt has been cancelled
            FormPromptAlreadyRespondedError: If prompt already has a response
            FormDataValidationError: If form data fails validation

        """
        # Load the prompt, validate its state, then validate the submitted fields.
        prompt = await self._get_form_prompt_record(prompt_id)
        if prompt is None:
            raise FormPromptNotFoundError(prompt_id)

        await self._validate_responder(prompt)
        validate_prompt_submission_state(prompt)
        cleaned_data = validate_form_submission(prompt.form_definition, submitted_data)

        logger.info(
            "Validated form submission",
            prompt_id=prompt_id,
            field_count=len(cleaned_data),
        )

        responded_at = datetime.now(UTC)
        handoff_started = time.monotonic()

        # SECURITY: Optimistic locking prevents TOCTOU race condition.
        # UPDATE with WHERE status=PENDING ensures only one concurrent submission succeeds.
        stmt = (
            update(FormPrompt)
            .where(FormPrompt.id == prompt_id)  # type: ignore[arg-type]
            .where(FormPrompt.status == FormPromptStatus.PENDING)  # type: ignore[arg-type]
            .where(
                or_(
                    FormPrompt.timeout_at.is_(None),  # type: ignore[union-attr]
                    FormPrompt.timeout_at > responded_at,  # type: ignore[arg-type, operator]
                )
            )
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
                validate_prompt_submission_state(prompt)
                raise FormPromptAlreadyRespondedError(prompt_id, prompt.status)
            raise FormPromptNotFoundError(prompt_id)

        execution = await self.session.get(Execution, prompt.execution_id)
        await self.session.commit()

        # Refresh to get the updated state
        await self.session.refresh(
            prompt,
            attribute_names=["status", "response_data", "responded_by", "responded_at"],
        )
        prompt.status = FormPromptStatus.SUBMITTED
        prompt.response_data = cleaned_data
        prompt.responded_by = self.user.id
        prompt.responded_at = responded_at

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
        else:
            # Single-process monotonic interval starting at `handoff_started`,
            # taken alongside `responded_at` above: immune to cross-host clock
            # offset and to NTP step corrections. Covers persisting the
            # submission (UPDATE + commit), the HTTP hop to the workflow engine
            # including retries, and the Temporal complete_async_activity RPC.
            try:
                get_metrics_recorder().record(
                    MetricType.FORM_PROMPT_SUBMISSION_HANDOFF,
                    (time.monotonic() - handoff_started) * 1000,
                    unit="ms",
                    component=ComponentLabel.API_SERVICE,
                )
            except Exception:  # noqa: BLE001
                logger.warning("Failed to record form prompt submission handoff metric (non-fatal)")

        # Emit the lifecycle event with metadata only
        AuditEventDispatcher.dispatch(
            FormPromptSubmittedEvent(
                prompt_id=prompt_id,
                workflow_id=execution.workflow_id if execution is not None else None,
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

        # Return the eagerly-loaded read model, keeping transient signal status
        # only on this response.
        if signal_error:
            logger.error("Signal delivery failed", prompt_id=prompt_id, error=signal_error)

        read = self._to_read_model(prompt, signal_delivery_error=signal_error)
        read.responded_by = UserReference(id=self.user.id, name=self.user.display_name, type=UserReferenceType.USER)
        return read
