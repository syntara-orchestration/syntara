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

    from syntara.authz.evaluator import AuthzEvaluator
    from syntara.workflows.models.execution import Execution
    from syntara.workflows.models.workflow import Workflow

logger = structlog.stdlib.get_logger(__name__)

_SUB_WORKFLOW_NAMESPACE = UUID("a3e4c7f0-1b2d-4e5f-8a9c-0d1e2f3a4b5c")

_MAX_SUB_WORKFLOW_DEPTH = 10


async def authorize_child_invocation(
    session: AsyncSession,
    evaluator: AuthzEvaluator,
    *,
    actor_id: UUID,
    child_workflow: Workflow,
) -> None:
    """Enforce execute-permission for a sub-workflow invocation.

    Authorizes the propagated initiator identity against the child workflow's own
    project, mirroring the direct-execution check in ``create_execution``
    (``execution:run``, project-scoped). The project is resolved from the
    authoritative workflow record, never from caller-supplied input, so a caller
    cannot spoof a project it is permitted to run in.

    Fails closed: a missing or disabled principal, or an explicit deny, raises a non-retryable
    ``ApplicationError``; transient evaluator or database errors propagate unchanged
    so Temporal retries them instead of treating the failure as a grant.

    For scheduled parents the propagated identity is the workflow author
    (AAP-95035); authorizing the author is a V1 decision pending Product/Security
    review (tracked under AAP-91266).
    """
    from sqlmodel import select  # noqa: PLC0415

    from syntara.authz.engine import AuthzRequest, authorize  # noqa: PLC0415
    from syntara.authz.models.project import Project  # noqa: PLC0415
    from syntara.core.models.user import User  # noqa: PLC0415

    project_result = await session.exec(select(Project.name).where(Project.id == child_workflow.project_id))
    resource_project = project_result.first() or ""

    # Reject a missing OR disabled principal. Deactivating a user revokes their
    # sessions but leaves role assignments intact, and the authz resolver does not
    # filter disabled users, so an in-flight parent must not launch a child after
    # its initiator is disabled. The HTTP path is covered by session auth; the
    # worker has no session, so fail closed here.
    actor = await session.get(User, actor_id)
    if actor is None or not actor.is_enabled:
        msg = "Sub-workflow invocation principal is missing or disabled; refusing to create child execution."
        raise ApplicationError(msg, type="SubWorkflowAuthorizationError", non_retryable=True)

    authz_result = await authorize(
        session,
        evaluator,
        AuthzRequest(
            user_id=actor_id,
            action="run",
            resource_type="execution",
            resource_id="",
            resource_project=resource_project,
            user_labels=actor.labels,
            user_metadata=actor.authz_metadata,
        ),
    )
    if not authz_result.allowed or authz_result.denied:
        logger.info(
            "Sub-workflow invocation authorization denied",
            actor_id=str(actor_id),
            child_workflow_id=str(child_workflow.id),
            denied_by=authz_result.denied_by,
        )
        msg = "Not authorized to run child workflow."
        raise ApplicationError(msg, type="SubWorkflowAuthorizationError", non_retryable=True)


class SubWorkflowSetupActivity:
    """Temporal activity that prepares a child workflow execution.

    Instantiated once at worker startup with shared dependencies.
    """

    def __init__(
        self,
        session_factory: Callable[..., AsyncSession],
        task_queue: str,
        evaluator: AuthzEvaluator | None = None,
    ) -> None:
        """Initialize with shared session factory, task queue, and authz evaluator.

        ``evaluator`` is injected by the worker process and drives child-invocation
        authorization. It defaults to ``None`` so unit/integration tests that do not
        exercise authorization can construct the activity unchanged; when ``None`` the
        execute-permission check is skipped (the worker always supplies one).
        """
        self._session_factory = session_factory
        self._task_queue = task_queue
        self._evaluator = evaluator

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

        # The effective actor must be a valid UUID. A schedule/webhook/event start
        # may not carry one; raise a non-retryable config error rather than letting
        # UUID() raise ValueError and be retried 3x as a transient activity failure.
        try:
            created_by_uuid = UUID(created_by_user_id)
        except (ValueError, TypeError):
            msg = "Sub-workflow invocation is missing a valid created_by_user_id"
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
            created_by_uuid=created_by_uuid,
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
        created_by_uuid: UUID,
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
            resume_result: dict[str, Any] | None = None
            if existing is not None:
                resume_result = await self._resume_pinned_child_execution(
                    session,
                    existing=existing,
                    child_workflow_id=child_workflow_id,
                    child_execution_id_str=child_execution_id_str,
                    trigger_node_id=trigger_node_id,
                    input_mapping=input_mapping,
                    created_by_user_id=created_by_user_id,
                    current_depth=current_depth,
                    parent_execution_id=parent_execution_id,
                )
        if resume_result is not None:
            return resume_result

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

            await self._assert_child_in_parent_project(
                session,
                parent_execution_id=parent_execution_id,
                child_workflow_id=child_workflow_id,
                child_project_id=child_workflow.project_id,
                child_execution_id_str=child_execution_id_str,
            )

            # Execute-permission enforcement runs whenever an evaluator is wired
            # (always in the worker process); it is skipped only when the activity
            # is constructed without one, e.g. tests that do not exercise authz.
            if self._evaluator is not None:
                await authorize_child_invocation(
                    session,
                    self._evaluator,
                    actor_id=created_by_uuid,
                    child_workflow=child_workflow,
                )

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
                created_by=created_by_uuid,
                updated_by=created_by_uuid,
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

    async def _assert_child_in_parent_project(
        self,
        session: AsyncSession,
        *,
        parent_execution_id: str,
        child_workflow_id: UUID,
        child_project_id: UUID,
        child_execution_id_str: str,
    ) -> None:
        """Reject a cross-project sub-workflow invocation before the child is created.

        Loads the parent execution in the caller's session and requires the child
        workflow to share its project. A missing or malformed parent id is rejected
        rather than bypassed, so neither the new-invocation path nor the idempotent
        resume path can create or resume a child across a project boundary.

        This is project isolation only. It is NOT the execute-permission (RBAC) check
        required by ANSTRAT-2347 AC-3; runtime execution authorization is tracked under
        AAP-91266 and must land before the feature reaches devel.

        Raises:
            ApplicationError: Non-retryable ``SubWorkflowProjectScopeError`` when the
                parent execution is missing or malformed, or is in a different project
                from the child workflow.

        """
        from syntara.workflows.models.execution import Execution  # noqa: PLC0415

        try:
            parent_uuid = UUID(parent_execution_id)
        except (ValueError, TypeError):
            msg = (
                f"Sub-workflow invocation has an invalid parent execution id "
                f"'{parent_execution_id}'; refusing to create child execution "
                f"'{child_execution_id_str}' without project-scope validation."
            )
            raise ApplicationError(msg, type="SubWorkflowProjectScopeError", non_retryable=True) from None

        parent = await session.get(Execution, parent_uuid)
        if parent is None:
            msg = (
                f"Parent execution '{parent_execution_id}' not found; refusing to create "
                f"child execution '{child_execution_id_str}' without project-scope validation."
            )
            raise ApplicationError(msg, type="SubWorkflowProjectScopeError", non_retryable=True)

        if parent.project_id != child_project_id:
            # Do not echo the parent/child project ids: a caller denied cross-project
            # access should not learn the other project's identifier from the error.
            msg = (
                f"Cross-project sub-workflow invocation rejected: child workflow "
                f"'{child_workflow_id}' is not in the parent execution's project. "
                f"A sub-workflow must be in the same project as its parent."
            )
            raise ApplicationError(msg, type="SubWorkflowProjectScopeError", non_retryable=True)

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
        parent_execution_id: str,
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

        await self._assert_child_in_parent_project(
            session,
            parent_execution_id=parent_execution_id,
            child_workflow_id=existing.workflow_id,
            child_project_id=child_workflow.project_id,
            child_execution_id_str=child_execution_id_str,
        )

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
