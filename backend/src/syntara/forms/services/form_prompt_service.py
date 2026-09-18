"""Service layer for form prompt operations.

Minimal internal-facing implementation for workflow engine integration.
AAP-91889 will extend with full filtering/sorting/enrichment.
"""

from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from syntara.forms.exceptions import FormPromptAlreadyRequestedError
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


class FormPromptService:
    """Service for managing form prompts.

    Minimal service covering workflow engine needs:
    - create: atomically create form_prompts row + responder junctions
    - list_by_execution: fetch prompts for an execution
    - batch_update_status: update prompt statuses (expire/cancel)
    """

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        """Initialize service with database session.

        Args:
            session: SQLAlchemy async session

        """
        self.session = session

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
        # Check for duplicate
        existing = await self._get_form_prompt(
            request.execution_id,
            request.prompt_node_id,
            request.loop_iteration_path,
        )
        if existing is not None:
            raise FormPromptAlreadyRequestedError(
                request.execution_id, request.prompt_node_id, request.loop_iteration_path
            )

        # TODO(https://redhat.atlassian.net/browse/AAP-91887): Validate execution reference against project_id

        # Create the prompt
        form_prompt = FormPrompt(
            execution_id=request.execution_id,
            project_id=request.project_id,
            prompt_node_id=request.prompt_node_id,
            name=request.name,
            message=request.message,
            loop_iteration_path=request.loop_iteration_path,
            temporal_activity_id=request.temporal_activity_id or request.prompt_node_id,
            timeout_at=request.timeout_at,
            form_definition=request.form_definition,
            submit_label=request.submit_label,
            success_message=request.success_message,
            timezone=request.timezone,
            css_override=request.css_override,
            status=FormPromptStatus.PENDING,
        )
        self.session.add(form_prompt)
        await self.session.flush()  # Get the ID

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

        await self.session.flush()

        logger.info(
            "Created form prompt",
            prompt_id=form_prompt.id,
            execution_id=request.execution_id,
            prompt_node_id=request.prompt_node_id,
        )

        # Return summary for internal workflow engine endpoints
        return FormPromptSummary.model_validate(form_prompt)

    async def list_by_execution(
        self,
        execution_id: UUID,
        status: FormPromptStatus | None = None,
    ) -> FormPromptListResponse:
        """Fetch form prompts for an execution, with optional status filter.

        Args:
            execution_id: Workflow execution ID
            status: Optional status filter

        Returns:
            Paginated response with form prompt summaries

        """
        query = select(FormPrompt).where(FormPrompt.execution_id == execution_id)  # type: ignore[arg-type]
        if status is not None:
            query = query.where(FormPrompt.status == status)  # type: ignore[arg-type]

        result = await self.session.execute(query)
        prompts = list(result.scalars().all())

        logger.debug(
            "Listed form prompts by execution",
            execution_id=execution_id,
            status=status.value if status else None,
            count=len(prompts),
        )

        # Convert to summaries and wrap in paginated response
        summaries = [FormPromptSummary.model_validate(p) for p in prompts]
        return FormPromptListResponse(resources=summaries, next=None, prev=None)

    async def batch_update_status(self, request: BatchFormPromptRequest) -> BatchUpdateResponse:
        """Batch update form prompt statuses.

        Enforces state transition rules via can_transition().
        Already-terminal prompts are skipped (idempotent).

        Args:
            request: Batch update request

        Returns:
            Typed batch update response with results and counts

        """
        results: list[BatchUpdateResult] = []
        success_count = 0
        failed_count = 0

        for update in request.updates:
            try:
                prompt = await self.session.get(FormPrompt, update.prompt_id)
                if prompt is None:
                    results.append(
                        BatchUpdateResult(
                            prompt_id=str(update.prompt_id),
                            success=False,
                            error="Form prompt not found",
                        )
                    )
                    failed_count += 1
                    continue

                # Check transition validity
                current_status = FormPromptStatus(prompt.status)
                target_status = FormPromptStatus(update.status.value)

                if not can_transition(current_status, target_status):
                    # Idempotent: if already at target status, treat as success
                    if current_status == target_status:
                        results.append(
                            BatchUpdateResult(
                                prompt_id=str(update.prompt_id),
                                success=True,
                                message=f"Already {target_status.value}",
                            )
                        )
                        success_count += 1
                    else:
                        results.append(
                            BatchUpdateResult(
                                prompt_id=str(update.prompt_id),
                                success=False,
                                error=f"Cannot transition from {current_status.value} to {target_status.value}",
                            )
                        )
                        failed_count += 1
                    continue

                # Update status
                prompt.status = target_status
                self.session.add(prompt)
                results.append(
                    BatchUpdateResult(
                        prompt_id=str(update.prompt_id),
                        success=True,
                    )
                )
                success_count += 1

            except Exception as e:
                logger.exception(
                    "Error updating form prompt status",
                    prompt_id=update.prompt_id,
                    error=str(e),
                )
                results.append(
                    BatchUpdateResult(
                        prompt_id=str(update.prompt_id),
                        success=False,
                        error=str(e),
                    )
                )
                failed_count += 1

        await self.session.flush()

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

    async def _get_form_prompt(
        self,
        execution_id: UUID,
        prompt_node_id: str,
        loop_iteration_path: list[int],
    ) -> FormPrompt | None:
        """Get form prompt by unique key (execution_id, prompt_node_id, loop_iteration_path).

        Args:
            execution_id: Workflow execution ID
            prompt_node_id: Canvas node ID
            loop_iteration_path: Loop iteration path

        Returns:
            FormPrompt if found, None otherwise

        """
        query = (
            select(FormPrompt)
            .where(FormPrompt.execution_id == execution_id)  # type: ignore[arg-type]
            .where(FormPrompt.prompt_node_id == prompt_node_id)  # type: ignore[arg-type]
            .where(FormPrompt.loop_iteration_path == loop_iteration_path)  # type: ignore[arg-type]
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
