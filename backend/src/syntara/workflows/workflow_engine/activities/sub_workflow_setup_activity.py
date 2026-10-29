"""Setup activity for Sub-workflow (Reference Mode) execution.

Resolves the child workflow from the database, validates the selected
trigger, creates a child Execution record, and returns the data needed
for the parent OrchestratorWorkflow to call ``execute_child_workflow``.

Follows the ScheduledExecutionLauncher pattern: class-based activity
that receives ``session_factory`` and ``task_queue`` at construction.

Idempotency: uses a deterministic child execution ID derived from
(parent_execution_id, node_id). If the child Execution already exists, the
activity resumes it from the version pinned on that record rather than
re-resolving the currently-published version, so a retry that races a
republish or unpublish of the child cannot change the definition the child
runs, and no duplicate execution is created.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid5

import structlog
from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName, NodeType

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.workflows.models.execution import Execution

logger = structlog.stdlib.get_logger(__name__)

_SUB_WORKFLOW_NAMESPACE = UUID("a3e4c7f0-1b2d-4e5f-8a9c-0d1e2f3a4b5c")

_MAX_SUB_WORKFLOW_DEPTH = 10


class SubWorkflowSetupActivity:
    """Temporal activity that prepares a child workflow execution.

    Instantiated once at worker startup with shared dependencies.
    """

    def __init__(
        self,
        session_factory: Callable[..., AsyncSession],
        task_queue: str,
    ) -> None:
        """Initialize with shared session factory and task queue."""
        self._session_factory = session_factory
        self._task_queue = task_queue

    @activity.defn(name=ActivityName.SUB_WORKFLOW)
    async def run(
        self,
        parameters: dict[str, Any],
        parent_execution_id: str,
        parent_node_id: str,
        created_by_user_id: str,
        current_depth: int,
        invocation_node_id: str | None = None,
    ) -> dict[str, Any]:
        """Resolve child workflow and prepare execution record.

        Args:
            parameters: Resolved node parameters (workflow_id, trigger_node_id, input_mapping).
            parent_execution_id: Parent execution ID for lineage tracking.
            parent_node_id: Node ID of the SUB_WORKFLOW step in the parent.
            created_by_user_id: User who started the parent execution.
            current_depth: Current sub-workflow nesting depth.
            invocation_node_id: Iteration-aware invocation identity, used only for
                child execution ID derivation. Defaults to ``parent_node_id`` (the
                canvas node id) outside loops; inside a ``for_each`` it carries the
                ``_iter_{n}`` suffix chain so each iteration gets a distinct child.

        Returns:
            Dict with all data needed to call execute_child_workflow.

        Raises:
            ApplicationError: Non-retryable, if child workflow is missing,
                unpublished, disabled, trigger not found, wrong trigger type,
                depth exceeded, or project mismatch.

        """
        if current_depth >= _MAX_SUB_WORKFLOW_DEPTH:
            msg = (
                f"Sub-workflow nesting depth {current_depth} exceeds maximum "
                f"({_MAX_SUB_WORKFLOW_DEPTH}). This may indicate a cyclic invocation."
            )
            raise ApplicationError(msg, type="SubWorkflowDepthExceeded", non_retryable=True)

        child_workflow_id_str = parameters.get("workflow_id")
        if not child_workflow_id_str:
            msg = "Sub-workflow node is missing required 'workflow_id' parameter"
            raise ApplicationError(msg, type="ConfigError", non_retryable=True)

        trigger_node_id = parameters.get("trigger_node_id")
        if not trigger_node_id:
            msg = "Sub-workflow node is missing required 'trigger_node_id' parameter"
            raise ApplicationError(msg, type="ConfigError", non_retryable=True)

        try:
            child_workflow_id = UUID(child_workflow_id_str)
        except ValueError:
            msg = f"Invalid workflow_id format: {child_workflow_id_str}"
            raise ApplicationError(msg, type="ConfigError", non_retryable=True) from None

        # parent_node_id is the canvas node identity, kept for lineage metadata;
        # invocation_node_id is the iteration-aware identity used only here so that
        # distinct for_each iterations derive distinct child executions.
        invocation_id = invocation_node_id or parent_node_id
        child_execution_id = uuid5(_SUB_WORKFLOW_NAMESPACE, f"{parent_execution_id}:{invocation_id}")
        child_execution_id_str = str(child_execution_id)

        return await self._prepare_child_execution(
            child_workflow_id=child_workflow_id,
            child_execution_id=child_execution_id,
            child_execution_id_str=child_execution_id_str,
            trigger_node_id=trigger_node_id,
            input_mapping=parameters.get("input_mapping", {}),
            parent_execution_id=parent_execution_id,
            parent_node_id=parent_node_id,
            created_by_user_id=created_by_user_id,
            current_depth=current_depth,
        )

    async def _prepare_child_execution(
        self,
        *,
        child_workflow_id: UUID,
        child_execution_id: UUID,
        child_execution_id_str: str,
        trigger_node_id: str,
        input_mapping: dict[str, Any],
        parent_execution_id: str,
        parent_node_id: str,
        created_by_user_id: str,
        current_depth: int,
    ) -> dict[str, Any]:
        from sqlmodel import select  # noqa: PLC0415

        from syntara.workflows.exceptions import WorkflowNotPublishedError  # noqa: PLC0415
        from syntara.workflows.models.execution import Execution, ExecutionStatus  # noqa: PLC0415
        from syntara.workflows.models.workflow import Workflow  # noqa: PLC0415
        from syntara.workflows.models.workflow_version import WorkflowVersion  # noqa: PLC0415
        from syntara.workflows.utils.workflow_metadata import (  # noqa: PLC0415
            build_workflow_metadata,
            resolve_user_display_name,
        )

        # Idempotent retry: if the child execution already exists, resume from the
        # version pinned on that record. The published version is deliberately NOT
        # re-resolved here, so a republish or unpublish occurring between setup
        # attempts cannot change the definition the already-created child runs.
        async with self._session_factory() as session:
            existing = await session.get(Execution, child_execution_id)
            if existing is not None:
                return await self._resume_pinned_child_execution(
                    session,
                    existing=existing,
                    child_workflow_id=child_workflow_id,
                    child_execution_id_str=child_execution_id_str,
                    trigger_node_id=trigger_node_id,
                    input_mapping=input_mapping,
                    created_by_user_id=created_by_user_id,
                    current_depth=current_depth,
                )

        # New invocation: resolve the currently-published version, validate it, and
        # create the child execution pinned to that version.
        async with self._session_factory() as session:
            result = await session.exec(
                select(Workflow, WorkflowVersion)
                .join(WorkflowVersion, WorkflowVersion.id == Workflow.published_version_id)  # type: ignore[arg-type]
                .where(Workflow.id == child_workflow_id)
            )
            row = result.first()
            if row is None:
                raise ApplicationError(
                    str(WorkflowNotPublishedError(child_workflow_id)),
                    type="WorkflowNotPublishedError",
                    non_retryable=True,
                )

            child_workflow, child_version = row

            if not child_workflow.is_enabled:
                msg = (
                    f"Workflow '{child_workflow_id}' is disabled and cannot be "
                    f"invoked as a sub-workflow. Re-enable it before retrying."
                )
                raise ApplicationError(msg, type="WorkflowDisabledError", non_retryable=True)

            self._validate_trigger(child_version.workflow_definition, trigger_node_id)
            self._validate_input(child_version.workflow_definition, trigger_node_id, input_mapping)

            author_name = await resolve_user_display_name(session, child_workflow.created_by)

            child_wf_name = child_workflow.name
            child_wf_id = child_workflow.id
            child_wf_project_id = child_workflow.project_id
            child_version_id = child_version.id
            child_version_number = child_version.version
            workflow_def = child_version.workflow_definition
            now = datetime.now(UTC)

            temporal_workflow_id = f"{child_wf_name}-{child_execution_id_str}"

            child_metadata = build_workflow_metadata(
                workflow_name=child_wf_name,
                workflow_id=child_wf_id,
                workflow_version=child_version_number,
                workflow_published=True,
                workflow_author=author_name,
                project_id=child_wf_project_id,
                execution_id=child_execution_id_str,
                execution_mode="sub_workflow",
                created_by=created_by_user_id,
                created_by_user_id=created_by_user_id,
                created_at=now.isoformat(),
                workflow_version_id=child_version_id,
            )
            child_metadata["sub_workflow_depth"] = current_depth + 1

            execution = Execution(
                id=child_execution_id,
                workflow_id=child_wf_id,
                workflow_version_id=child_version_id,
                project_id=child_wf_project_id,
                temporal_workflow_id=temporal_workflow_id,
                status=ExecutionStatus.PENDING,
                input_data=input_mapping,
                trigger_node_id=trigger_node_id,
                trigger_type=ActivityName.SUBWORKFLOW_TRIGGER.value,
                interface=None,
                created_by=UUID(created_by_user_id),
                updated_by=UUID(created_by_user_id),
                execution_metadata={
                    "trigger_type": ActivityName.SUBWORKFLOW_TRIGGER,
                    "parent_execution_id": parent_execution_id,
                    "parent_node_id": parent_node_id,
                    "sub_workflow_depth": current_depth + 1,
                },
            )
            session.add(execution)
            await session.commit()

        logger.info(
            "Child execution created for sub-workflow",
            child_execution_id=child_execution_id_str,
            child_workflow_id=str(child_wf_id),
            parent_execution_id=parent_execution_id,
            parent_node_id=parent_node_id,
        )

        return {
            "execution_id": child_execution_id_str,
            "temporal_workflow_id": temporal_workflow_id,
            "workflow_definition": workflow_def,
            "trigger_node_id": trigger_node_id,
            "input_data": input_mapping,
            "task_queue": self._task_queue,
            "workflow_metadata": child_metadata,
            "child_workflow_id": str(child_wf_id),
            "child_workflow_name": child_wf_name,
            "child_workflow_version": child_version_number,
        }

    async def _resume_pinned_child_execution(
        self,
        session: AsyncSession,
        *,
        existing: Execution,
        child_workflow_id: UUID,
        child_execution_id_str: str,
        trigger_node_id: str,
        input_mapping: dict[str, Any],
        created_by_user_id: str,
        current_depth: int,
    ) -> dict[str, Any]:
        """Resume an already-created child execution from its pinned version.

        The child ``Execution`` record pins ``workflow_version_id`` at creation
        time. On a setup-activity retry the pinned version is reloaded by id and
        its stored definition returned, regardless of what is currently published
        for the child workflow. This guarantees that a republish or unpublish
        between setup attempts cannot change the definition the child runs, and
        that an unpublish after creation does not turn a valid resume into a
        non-retryable failure.
        """
        from syntara.workflows.models.workflow import Workflow  # noqa: PLC0415
        from syntara.workflows.models.workflow_version import WorkflowVersion  # noqa: PLC0415
        from syntara.workflows.utils.workflow_metadata import (  # noqa: PLC0415
            build_workflow_metadata,
            resolve_user_display_name,
        )

        if existing.workflow_id != child_workflow_id:
            msg = (
                f"Existing child execution '{child_execution_id_str}' belongs to workflow "
                f"'{existing.workflow_id}', not the requested '{child_workflow_id}'. "
                f"Refusing to resume a mismatched execution."
            )
            raise ApplicationError(msg, type="ConfigError", non_retryable=True)

        pinned_version = await session.get(WorkflowVersion, existing.workflow_version_id)
        if pinned_version is None:
            msg = (
                f"Pinned workflow version '{existing.workflow_version_id}' for child "
                f"execution '{child_execution_id_str}' no longer exists."
            )
            raise ApplicationError(msg, type="WorkflowVersionMissingError", non_retryable=True)

        child_workflow = await session.get(Workflow, existing.workflow_id)
        if child_workflow is None:
            msg = f"Workflow '{existing.workflow_id}' for child execution '{child_execution_id_str}' no longer exists."
            raise ApplicationError(msg, type="WorkflowMissingError", non_retryable=True)

        author_name = await resolve_user_display_name(session, child_workflow.created_by)
        created_at = existing.created_at or datetime.now(UTC)

        child_metadata = build_workflow_metadata(
            workflow_name=child_workflow.name,
            workflow_id=child_workflow.id,
            workflow_version=pinned_version.version,
            workflow_published=True,
            workflow_author=author_name,
            project_id=child_workflow.project_id,
            execution_id=child_execution_id_str,
            execution_mode="sub_workflow",
            created_by=created_by_user_id,
            created_by_user_id=created_by_user_id,
            created_at=created_at.isoformat(),
            workflow_version_id=existing.workflow_version_id,
        )
        child_metadata["sub_workflow_depth"] = current_depth + 1

        logger.info(
            "Child execution already exists; resuming from pinned version (idempotent retry)",
            child_execution_id=child_execution_id_str,
            pinned_version=pinned_version.version,
            workflow_version_id=str(existing.workflow_version_id),
        )

        resolved_input = existing.input_data if existing.input_data is not None else input_mapping

        return {
            "execution_id": child_execution_id_str,
            "temporal_workflow_id": existing.temporal_workflow_id,
            "workflow_definition": pinned_version.workflow_definition,
            "trigger_node_id": trigger_node_id,
            "input_data": resolved_input,
            "task_queue": self._task_queue,
            "workflow_metadata": child_metadata,
            "child_workflow_id": str(child_workflow.id),
            "child_workflow_name": child_workflow.name,
            "child_workflow_version": pinned_version.version,
        }

    @staticmethod
    def _validate_trigger(workflow_def: dict[str, Any], trigger_node_id: str) -> None:
        """Validate that the specified trigger exists and is a subworkflow trigger."""
        for trigger in workflow_def.get("triggers", []):
            if trigger.get("id") == trigger_node_id:
                trigger_type = trigger.get("type", "")
                if trigger_type != NodeType.SUBWORKFLOW_TRIGGER:
                    msg = (
                        f"Trigger '{trigger_node_id}' has type '{trigger_type}', "
                        f"expected '{NodeType.SUBWORKFLOW_TRIGGER}'. "
                        f"Sub-workflow invocation requires a subworkflow_trigger node."
                    )
                    raise ApplicationError(msg, type="InvalidTriggerType", non_retryable=True)
                return
        msg = f"Trigger node '{trigger_node_id}' not found in child workflow definition"
        raise ApplicationError(msg, type="TriggerNotFoundError", non_retryable=True)

    @staticmethod
    def _validate_input(
        workflow_def: dict[str, Any],
        trigger_node_id: str,
        input_data: dict[str, Any],
    ) -> None:
        """Validate sub-workflow input against the child trigger's declared input schema.

        A no-op when the trigger declares no ``input_schema``. Otherwise fills schema
        defaults into ``input_data`` and raises a non-retryable error naming the
        offending field when the input does not conform. Runs before the child
        execution is created so an invalid invocation fails fast without an orphan
        child.
        """
        import jsonschema  # noqa: PLC0415

        from syntara.workflows.json_schema_validation import apply_schema_defaults  # noqa: PLC0415

        trigger = next(
            (t for t in workflow_def.get("triggers", []) if t.get("id") == trigger_node_id),
            None,
        )
        input_schema = (trigger or {}).get("parameters", {}).get("input_schema")
        if not input_schema:
            return

        try:
            apply_schema_defaults(input_data, input_schema)
        except jsonschema.ValidationError as exc:
            msg = f"Sub-workflow input validation failed for trigger '{trigger_node_id}': {exc.message}"
            raise ApplicationError(msg, type="SubWorkflowInputValidationError", non_retryable=True) from None
