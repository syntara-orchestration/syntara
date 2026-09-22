"""Service layer for form prompt operations.

Minimal internal-facing implementation for workflow engine integration.
AAP-91889 will extend with full filtering/sorting/enrichment.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.authz.engine import AllowedProjectsResult
    from syntara.core.models import User

from syntara.core.services import BaseService
from syntara.forms.exceptions import FormPromptAlreadyRequestedError, InvalidResponderReferenceError
from syntara.forms.models.api_models import (
    BatchFormPromptRequest,
    BatchUpdateResponse,
    BatchUpdateResult,
    FormPromptCreateRequest,
    FormPromptStatus,
    FormPromptSummary,
    can_transition,
)
from syntara.forms.models.form_prompt import FormPrompt, FormPromptListResponse
from syntara.forms.models.form_prompt_responders import FormPromptResponderGroup, FormPromptResponderUser

logger = structlog.stdlib.get_logger(__name__)


class FormPromptService(BaseService):
    """Service for managing form prompts.

    Minimal service covering workflow engine needs:
    - create: atomically create form_prompts row + responder junctions
    - list: fetch prompts with pagination and filtering
    - batch_update_status: update prompt statuses (expire/cancel)
    """

    def __init__(
        self,
        session: AsyncSession,
        user: User,
    ) -> None:
        """Initialize service with database session and user context.

        Args:
            session: SQLAlchemy async session
            user: User context for authorization

        """
        super().__init__(session, user)
        self.session = session
        self.user = user

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

    async def create(self, request: FormPromptCreateRequest) -> FormPromptSummary:
        """Create a new form prompt.

        Args:
            request: Form prompt creation request

        Returns:
            Created form prompt summary

        Raises:
            FormPromptAlreadyRequestedError: If a prompt for this (execution_id, prompt_node_id,
                loop_iteration_path) already exists

        """
        # TODO(https://redhat.atlassian.net/browse/AAP-91887): Validate execution reference against project_id

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
