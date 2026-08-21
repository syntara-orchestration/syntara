"""Workflow service layer for business logic.

This service encapsulates workflow-related business logic, separating it from
HTTP/API concerns in the FastAPI endpoints.
"""

import threading
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy.exc import IntegrityError
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.authz.engine import AllowedProjectsResult, AuthzRequest, authorize
from syntara.authz.evaluator import AuthzEvaluator
from syntara.authz.exceptions import AuthorizationDeniedError
from syntara.authz.models import Project
from syntara.core.exceptions import SafeValueError, assert_project_id_unchanged
from syntara.core.models import User
from syntara.core.services import BaseService
from syntara.core.services.extensions import ConvertResourceMixin
from syntara.credentials.lib.auth_types import AUTH_TYPE_URL
from syntara.credentials.models.credential import Credential
from syntara.credentials.models.credential_type import CredentialType
from syntara.metrics.dependencies import get_metrics_recorder
from syntara.metrics.types import ComponentLabel, MetricType
from syntara.workflows.audit.workflow_lifecycle import WorkflowAction, WorkflowLifecycleEvent
from syntara.workflows.audit.workflow_version import (
    WorkflowVersionCreatedEvent,
    WorkflowVersionExportedEvent,
    WorkflowVersionPublishedEvent,
    WorkflowVersionRestoredEvent,
    WorkflowVersionUnpublishedEvent,
)
from syntara.workflows.exceptions import (
    BuiltinWorkflowDeleteError,
    BuiltinWorkflowModifyError,
    ScheduledTriggerSyncError,
    WorkflowNameConflictError,
    WorkflowNotFoundError,
    WorkflowNotPublishedError,
    WorkflowPublishValidationError,
    WorkflowVersionConflictError,
    WorkflowVersionNotFoundError,
)
from syntara.workflows.models import Workflow, WorkflowListResponse, WorkflowRead, WorkflowVersion
from syntara.workflows.models.validation_finding import (
    ValidationCategory,
    ValidationFinding,
    ValidationResult,
    ValidationSeverity,
)
from syntara.workflows.models.workflow_definition import WorkflowDefinition
from syntara.workflows.models.workflow_publish_event import PublishAction, WorkflowPublishEvent
from syntara.workflows.services.scheduled_trigger_service import ScheduledTriggerService
from syntara.workflows.services.webhook_trigger_service import WEBHOOK_TRIGGER_TYPES, WebhookTriggerService
from syntara.workflows.services.workflow_diff import generate_change_summary
from syntara.workflows.validators import (
    get_system_continue_on_failure,
    validate_workflow_references,
    workflow_validator,
)

if TYPE_CHECKING:
    from syntara.workflows.models import WorkflowVersionListResponse
    from syntara.workflows.utils.serialization import VersionPublishTimestamps

logger = structlog.stdlib.get_logger(__name__)

# Running counters for workflow creation success rate (FR-010).
_workflow_creation_counts: list[int] = [0, 0]  # [successes, total]

# Thread lock to protect counter from race conditions during concurrent access
_workflow_creation_lock = threading.Lock()


def reset_workflow_creation_counters() -> None:
    """Clear the workflow creation counters (testing helper)."""
    with _workflow_creation_lock:
        _workflow_creation_counts[:] = [0, 0]


def _has_validation_issues(result: ValidationResult) -> bool:
    """Return True when the validation result has errors or warnings."""
    return result.error_count > 0 or result.warning_count > 0


class WorkflowConvertResourceMixin(ConvertResourceMixin):
    """Workflow-specific resource conversion to WorkflowRead format."""

    def convert_resource(self, resource: Workflow) -> WorkflowRead:  # type: ignore[override]
        """Convert Workflow to WorkflowRead format."""
        return WorkflowRead.model_validate(resource)


class WorkflowService(BaseService):
    """Service for workflow business logic.

    This service encapsulates all workflow-related business operations,
    including CRUD operations, validation, and version management.
    """

    def __init__(self, session: AsyncSession, user: User, opa_client: AuthzEvaluator | None = None) -> None:
        """Initialize WorkflowService with database session and user context."""
        super().__init__(session, user, convert_resource_mixin=WorkflowConvertResourceMixin())
        self.opa_client = opa_client

    @staticmethod
    def _emit_lifecycle_event(
        *,
        workflow_id: UUID,
        workflow_name: str,
        action: WorkflowAction,
        version: int | None = None,
        project_id: UUID | None = None,
        error_type: str | None = None,
        new_version_created: bool = False,
        change_summary: dict[str, Any] | None = None,
    ) -> None:
        AuditEventDispatcher.dispatch(
            WorkflowLifecycleEvent(
                workflow_id=workflow_id,
                workflow_name=workflow_name,
                action=action,
                version=version,
                project_id=project_id,
                error_type=error_type,
            )
        )
        if new_version_created and version is not None:
            AuditEventDispatcher.dispatch(
                WorkflowVersionCreatedEvent(
                    workflow_id=workflow_id,
                    workflow_name=workflow_name,
                    version=version,
                    change_summary=change_summary,
                )
            )

    async def _sync_all_trigger_types(
        self,
        webhook_service: WebhookTriggerService,
        workflow_id: UUID,
        workflow_definition: dict[str, Any],
        *,
        is_enabled: bool,
    ) -> None:
        for trigger_type in WEBHOOK_TRIGGER_TYPES:
            await webhook_service.sync_webhook_triggers(
                workflow_id=workflow_id,
                workflow_definition=workflow_definition,
                is_enabled=is_enabled,
                trigger_type=trigger_type,
            )

    async def _get_version_or_none(self, workflow_id: UUID, version: int) -> WorkflowVersion | None:
        """Fetch a single workflow version by workflow ID and version number."""
        result = await self.session.exec(
            select(WorkflowVersion).filter(
                WorkflowVersion.workflow_id == workflow_id,  # type: ignore[arg-type]
                WorkflowVersion.version == version,  # type: ignore[arg-type]
                WorkflowVersion.deleted_at.is_(None),  # type: ignore[union-attr]
            )
        )
        return result.one_or_none()

    async def _create_version_record(
        self,
        workflow: Workflow,
        workflow_definition: dict[str, Any],
        change_description: str | None,
    ) -> WorkflowVersion | None:
        """Create a new version record without validation.

        Includes change detection — skips creation if the definition
        matches the current version. Callers are responsible for
        validation.
        """
        current_version = await self._get_version_or_none(workflow.id, workflow.current_version)

        if current_version:
            try:
                stored_normalized = WorkflowDefinition.model_validate(current_version.workflow_definition).model_dump(
                    exclude_defaults=True
                )
            except Exception:  # noqa: BLE001
                stored_normalized = current_version.workflow_definition
            if stored_normalized == workflow_definition:
                return None

        count_result = await self.session.exec(
            select(func.max(WorkflowVersion.version)).filter(
                WorkflowVersion.workflow_id == workflow.id  # type: ignore[arg-type]
            )
        )
        max_version = count_result.one()
        next_version = (max_version or 0) + 1

        schema_version = workflow_definition.get("schema_version")
        new_version = WorkflowVersion(
            id=uuid4(),
            workflow_id=workflow.id,
            version=next_version,
            schema_version=schema_version,
            workflow_definition=workflow_definition,
            change_description=change_description or f"Version {next_version}",
            created_by=self.user.id,
        )

        workflow.current_version = next_version
        self.session.add(new_version)
        return new_version

    async def _create_and_flush_version(
        self,
        workflow: Workflow,
        fallback: WorkflowVersion,
        workflow_definition: dict[str, Any],
        change_description: str | None,
    ) -> WorkflowVersion:
        """Create a new version and flush, returning it or *fallback* if unchanged."""
        new_version = await self._create_version_record(
            workflow,
            workflow_definition=workflow_definition,
            change_description=change_description,
        )
        if new_version:
            await self.session.flush()
            return new_version
        return fallback

    @staticmethod
    async def _sync_scheduled_triggers(
        workflow_id: UUID,
        workflow_definition: dict[str, Any],
    ) -> None:
        """Create/update Temporal Schedules for scheduled trigger nodes.

        Only called on publish.  Unpublish and delete use
        ``_delete_scheduled_triggers`` for best-effort cleanup; the
        schedule reconciliation worker handles any orphans that remain
        when Temporal is unreachable.
        """
        scheduled_service = ScheduledTriggerService()
        await scheduled_service.sync_scheduled_triggers(
            workflow_id=str(workflow_id),
            workflow_definition=workflow_definition,
        )

    @staticmethod
    async def _delete_scheduled_triggers(workflow_id: UUID) -> None:
        """Best-effort deletion of Temporal Schedules for a workflow.

        Swallows errors so the caller (unpublish / delete) always succeeds.
        The schedule reconciliation worker will clean up any orphans that
        remain when Temporal is unreachable.
        """
        try:
            scheduled_service = ScheduledTriggerService()
            await scheduled_service.delete_triggers_for_workflow(
                workflow_id=str(workflow_id),
            )
        except ScheduledTriggerSyncError:
            logger.warning(
                "Best-effort scheduled trigger deletion failed — reconciliation worker will clean up orphans",
                workflow_id=str(workflow_id),
                exc_info=True,
            )

    @staticmethod
    def _extract_credential_ids(workflow_definition: dict[str, Any]) -> set[str]:
        """Return the set of credential UUIDs referenced in workflow node parameters.

        Extracts from:
        - node.parameters.credential_id (HTTP request, AAP, etc.)
        - node.parameters.integration_connections[].credential_id (Task Agent)
        """
        cred_ids: set[str] = set()
        for node in workflow_definition.get("nodes", []):
            params = node.get("parameters", {})
            if cred_id := params.get("credential_id"):
                cred_ids.add(cred_id)
            for conn in params.get("integration_connections") or []:
                if cred_id := conn.get("credential_id"):
                    cred_ids.add(cred_id)
        return cred_ids

    async def _validate_credential_project_scope(
        self,
        workflow_definition: dict[str, Any],
        project_id: UUID,
        previous_credential_ids: set[str] | None = None,
    ) -> None:
        """Validate credential references: project scope and credential:use authorization.

        Checks two things:
        1. All referenced credentials exist and belong to the specified project.
        2. The current user has credential:use permission on newly added credentials
           (diff-based: skips credentials already present in the previous version).

        Args:
            workflow_definition: The workflow definition containing node parameters.
            project_id: The project the workflow belongs to.
            previous_credential_ids: Credential IDs from the previous version
                (None for new workflows — all credentials treated as new).

        Raises:
            SafeValueError: If any credential is missing or in the wrong project.
            AuthorizationDeniedError: If the user lacks credential:use on a new credential.

        """
        credential_ids = self._extract_credential_ids(workflow_definition)

        if not credential_ids:
            return

        stmt = select(Credential.id, Credential.project_id).where(
            Credential.id.in_(credential_ids),  # type: ignore[attr-defined]
        )
        result = await self.session.exec(stmt)
        rows = result.all()

        found_ids = {str(row[0]) for row in rows}
        missing = credential_ids - found_ids
        wrong_project = any(row[1] != project_id for row in rows)

        if missing or wrong_project:
            msg = "One or more credential references are invalid or belong to a different project."
            raise SafeValueError(msg)

        await self._check_credential_use_permission(credential_ids, previous_credential_ids, project_id)

    async def _check_credential_use_permission(
        self,
        credential_ids: set[str],
        previous_credential_ids: set[str] | None,
        project_id: UUID,
    ) -> None:
        """Check credential:use permission on newly added credentials.

        Args:
            credential_ids: All credential IDs in the current definition.
            previous_credential_ids: Credential IDs from the previous version (None = all new).
            project_id: The project for authorization scoping.

        Raises:
            AuthorizationDeniedError: If the user lacks credential:use on any new credential.

        """
        if self.opa_client is None:
            msg = "Authorization service unavailable; cannot verify credential:use permission"
            raise AuthorizationDeniedError(msg)

        new_credentials = credential_ids - (previous_credential_ids or set())
        if not new_credentials:
            return

        proj_result = await self.session.exec(
            select(Project.name).where(Project.id == project_id, Project.deleted_at.is_(None))  # type: ignore[union-attr]
        )
        project_name = proj_result.first() or ""

        for cred_id in new_credentials:
            authz_result = await authorize(
                self.session,
                self.opa_client,
                AuthzRequest(
                    user_id=self.user.id,
                    action="use",
                    resource_type="credential",
                    resource_id=cred_id,
                    resource_project=project_name,
                    user_labels=self.user.labels,
                    user_metadata=self.user.authz_metadata,
                ),
            )
            if not authz_result.allowed:
                msg = "Not authorized to use one or more credentials in this workflow"
                raise AuthorizationDeniedError(msg)

    async def _validate_no_secret_url_conflicts(
        self,
        workflow_definition: dict[str, Any],
    ) -> None:
        """Reject HTTP request nodes that have both an explicit URL and a Secret URL credential.

        A Secret URL credential provides the request destination; an explicit
        ``parameters.url`` on the same node creates an ambiguous configuration
        where the credential silently wins and the activity record advertises
        the wrong host.
        """
        suspect: dict[str, str] = {}
        for node in workflow_definition.get("nodes", []):
            if node.get("type") != "http_request":
                continue
            params = node.get("parameters", {})
            if params.get("url") and params.get("credential_id"):
                suspect[params["credential_id"]] = node.get("name") or node.get("id", "unknown")

        if not suspect:
            return

        stmt = (
            select(Credential.id, CredentialType.injectors)
            .join(CredentialType, Credential.credential_type_id == CredentialType.id)  # type: ignore[arg-type]
            .where(Credential.id.in_(list(suspect.keys())))  # type: ignore[attr-defined]
        )
        result = await self.session.exec(stmt)
        for cred_id, injectors in result.all():
            extra_vars = (injectors or {}).get("extra_vars", {})
            if extra_vars.get("auth_type") == AUTH_TYPE_URL:
                node_name = suspect[str(cred_id)]
                msg = (
                    f"Node '{node_name}' has both an explicit URL and a Secret URL credential. "
                    "Remove the URL from node parameters or use a different credential type."
                )
                raise SafeValueError(msg)

    def _is_duplicate_name_error(self, e: IntegrityError) -> bool:
        """Check if IntegrityError is due to duplicate workflow name.

        Args:
            e: The IntegrityError to check

        Returns:
            True if error is due to duplicate workflow name constraint

        """
        error_str = str(e)
        return (
            "ix_workflows_name_project_unique" in error_str
            or "workflows.name" in error_str
            or "duplicate key" in error_str.lower()
        )

    async def _flush_with_duplicate_check(self, workflow_name: str) -> None:
        """Flush pending changes with duplicate name error handling.

        Flushes (but does not commit) so the caller can batch additional
        changes into the same transaction before a single atomic commit.

        Args:
            workflow_name: Name of workflow being created/updated

        Raises:
            WorkflowNameConflictError: If duplicate name constraint violated
            IntegrityError: For other integrity constraint violations

        """
        try:
            await self.session.flush()
        except IntegrityError as e:
            await self.session.rollback()
            if self._is_duplicate_name_error(e):
                raise WorkflowNameConflictError(workflow_name) from e
            raise

    async def create_workflow(
        self,
        name: str,
        description: str | None,
        labels: dict[str, Any],
        workflow_definition: dict[str, Any],
        project_id: UUID,
        *,
        is_import: bool = False,
    ) -> tuple[Workflow, WorkflowVersion, ValidationResult]:
        """Create a new V2 workflow with initial version.

        Args:
            name: Workflow name (must be unique)
            description: Optional workflow description
            labels: Optional key-value labels
            workflow_definition: V2 workflow definition as dict (triggers + nodes + edges)
            project_id: Project to assign workflow to
            is_import: When True, missing LLM models are cleared with warnings
                instead of raising errors (allows import of workflows from other instances)

        Returns:
            Tuple of (created workflow, initial version, validation result)

        Raises:
            WorkflowNameConflictError: If workflow name already exists

        """
        recorder = get_metrics_recorder()
        component = ComponentLabel.WORKFLOW_ENGINE
        system_cof = await get_system_continue_on_failure()

        with recorder.time(
            MetricType.WORKFLOW_VALIDATION_DURATION,
            labels={"component": component.value, "operation": "create"},
        ):
            result = workflow_validator.collect_findings(
                workflow_definition,
                system_continue_on_failure=system_cof,
            )

        has_validation_issues = _has_validation_issues(result)
        if has_validation_issues:
            logger.warning(
                "Workflow created with validation issues",
                user_id=str(self.user.id),
                error_count=result.error_count,
                warning_count=result.warning_count,
                findings=[f.message for f in result.findings[:10]],
            )

        from syntara.core.queries.project_queries import assert_project_alive  # noqa: PLC0415

        await assert_project_alive(self.session, project_id)

        project = await self.session.get(Project, project_id)
        if project and project.is_builtin:
            from syntara.authz.exceptions import BuiltinProtectionError  # noqa: PLC0415

            msg = f"Cannot create workflows in built-in project '{project.name}'"
            raise BuiltinProtectionError(msg)

        await self._validate_credential_project_scope(workflow_definition, project_id)
        await self._validate_no_secret_url_conflicts(workflow_definition)
        ref_findings = await validate_workflow_references(
            self.session, workflow_definition, project_id, is_import=is_import
        )
        if ref_findings:
            result = ValidationResult.from_findings([*result.findings, *ref_findings])
            has_validation_issues = True

        schema_version = workflow_definition.get("schema_version")
        workflow_dict = workflow_definition

        # Create workflow
        workflow = Workflow(
            id=uuid4(),
            name=name,
            description=description,
            labels=labels,
            current_version=1,
            created_by=self.user.id,
            is_enabled=False,
            has_validation_issues=has_validation_issues,
            project_id=project_id,
        )

        # Create initial version
        version = WorkflowVersion(
            id=uuid4(),
            workflow_id=workflow.id,
            version=1,
            schema_version=schema_version,
            workflow_definition=workflow_dict,
            created_by=self.user.id,
            change_description="Initial version",
        )

        self.session.add(workflow)
        self.session.add(version)

        # Flush + sync + commit as a single atomic transaction so that a
        # webhook-path conflict rolls back the workflow too.
        try:
            # Flush workflow + version (validates name uniqueness)
            await self._flush_with_duplicate_check(name)
            await self.session.refresh(workflow)
            await self.session.refresh(version)

            # Sync webhook triggers within the same transaction
            webhook_service = WebhookTriggerService(self.session, self.user)
            await self._sync_all_trigger_types(
                webhook_service,
                workflow.id,
                workflow_dict,
                is_enabled=False,
            )

            # Single atomic commit
            await self.session.commit()
        except Exception as exc:
            self._emit_lifecycle_event(
                workflow_id=workflow.id,
                workflow_name=workflow.name,
                action=WorkflowAction.CREATED,
                project_id=workflow.project_id,
                error_type=type(exc).__name__,
            )
            with _workflow_creation_lock:
                _workflow_creation_counts[1] += 1
                rate = _workflow_creation_counts[0] / _workflow_creation_counts[1]
            recorder.record(
                MetricType.WORKFLOW_CREATION_SUCCESS_RATE,
                rate,
                component=component,
            )
            raise

        # Record success only after the full transaction commits
        with _workflow_creation_lock:
            _workflow_creation_counts[0] += 1
            _workflow_creation_counts[1] += 1
            rate = _workflow_creation_counts[0] / _workflow_creation_counts[1]
        recorder.record(
            MetricType.WORKFLOW_CREATION_SUCCESS_RATE,
            rate,
            component=component,
        )

        self._emit_lifecycle_event(
            workflow_id=workflow.id,
            workflow_name=workflow.name,
            action=WorkflowAction.CREATED,
            version=version.version,
            project_id=workflow.project_id,
            new_version_created=True,
        )

        return workflow, version, result

    async def list_workflows_cursor(
        self,
        limit: int = 20,
        cursor: str | None = None,
        sort: str | None = None,
        query_params_items: Iterable[tuple[str, str]] | None = None,
        *,
        include_total: bool = False,
        allowed_projects: AllowedProjectsResult | None = None,
    ) -> WorkflowListResponse:
        """List workflows with filtering, sorting, and pagination.

        Args:
            limit: Maximum number of workflows to return (default 20)
            cursor: Cursor token for pagination
            sort: Sort parameter (e.g., "name", "-created_at")
            query_params_items: Raw query parameter items from request (for filtering)
            include_total: Whether to include total count in response
            allowed_projects: Optional project scope filter for authorization

        Returns:
            WorkflowListResponse with workflows, pagination metadata, and optional total

        """
        # Use unified list_resources method with overridden methods
        return await self.list_resources(
            model=Workflow,
            response_type=WorkflowListResponse,
            limit=limit,
            cursor=cursor,
            sort=sort or "-created_at",  # Default DESC sort if none provided
            query_params_items=query_params_items,
            include_total=include_total,
            allowed_projects=allowed_projects,
        )

    async def get_publish_context(
        self, version_ids: list[UUID]
    ) -> tuple[set[UUID], dict[UUID, "VersionPublishTimestamps"]]:
        """Query workflow_publish_events for publish status and timestamps."""
        from syntara.workflows.utils.serialization import VersionPublishTimestamps  # noqa: PLC0415

        ever_published: set[UUID] = set()
        timestamps: dict[UUID, VersionPublishTimestamps] = {}
        if not version_ids:
            return ever_published, timestamps
        rows = await self.session.exec(
            select(
                WorkflowPublishEvent.version_id,
                WorkflowPublishEvent.action,
                func.max(WorkflowPublishEvent.created_at),
            )
            .where(WorkflowPublishEvent.version_id.in_(version_ids))  # type: ignore[attr-defined]
            .group_by(WorkflowPublishEvent.version_id, WorkflowPublishEvent.action)  # type: ignore[arg-type]
        )
        for vid, action, ts in rows:
            if vid not in timestamps:
                timestamps[vid] = VersionPublishTimestamps()
            if action == PublishAction.PUBLISHED:
                ever_published.add(vid)
                timestamps[vid].published_at = ts
            elif action == PublishAction.UNPUBLISHED:
                timestamps[vid].unpublished_at = ts
        return ever_published, timestamps

    async def list_workflow_versions_cursor(
        self,
        workflow_id: UUID,
        limit: int = 20,
        cursor: str | None = None,
        sort: str | None = None,
        query_params_items: Iterable[tuple[str, str]] | None = None,
        *,
        include_total: bool = False,
    ) -> "WorkflowVersionListResponse":
        """List workflow versions with cursor-based pagination."""
        from syntara.workflows.models import WorkflowVersionListResponse, WorkflowVersionRead  # noqa: PLC0415
        from syntara.workflows.utils.serialization import (  # noqa: PLC0415
            VersionPublishTimestamps,
            deserialize_workflow_version,
        )

        workflow = await self.get_workflow_by_id(workflow_id)
        published_version_id = workflow.published_version_id

        username_map: dict[UUID, str] = {}
        ever_published_ids: set[UUID] = set()
        publish_ts: dict[UUID, VersionPublishTimestamps] = {}

        async def populate_version_context(versions: list[WorkflowVersion]) -> None:
            nonlocal ever_published_ids
            if not versions:
                return
            user_ids = {v.created_by for v in versions if v.created_by is not None}
            if user_ids:
                rows = await self.session.exec(
                    select(User.id, User.username).where(User.id.in_(user_ids))  # type: ignore[attr-defined]
                )
                username_map.update({row[0]: row[1] for row in rows})

            version_ids = [v.id for v in versions]
            batch_published, batch_ts = await self.get_publish_context(version_ids)
            ever_published_ids.update(batch_published)
            publish_ts.update(batch_ts)

        def convert_version(version: WorkflowVersion) -> WorkflowVersionRead:
            version_dict = deserialize_workflow_version(version, published_version_id, ever_published_ids, publish_ts)
            version_read = WorkflowVersionRead.model_validate(version_dict)
            version_read.created_by_username = username_map.get(version.created_by)
            return version_read

        merged_params = [("workflow_id", str(workflow_id))]
        if query_params_items:
            merged_params.extend((k, v) for k, v in query_params_items if k != "workflow_id")

        return await self.list_resources(
            model=WorkflowVersion,
            response_type=WorkflowVersionListResponse,
            response_type_converter=convert_version,
            post_query_callback=populate_version_context,
            limit=limit,
            cursor=cursor,
            sort=sort or "-created_at",
            query_params_items=merged_params,
            include_total=include_total,
        )

    async def populate_published_version_numbers(self, workflows: list[WorkflowRead]) -> None:
        """Batch-populate published_version_number on WorkflowRead objects."""
        version_ids = [w.published_version_id for w in workflows if w.published_version_id is not None]
        if not version_ids:
            return
        rows = await self.session.exec(
            select(WorkflowVersion.id, WorkflowVersion.version).where(
                WorkflowVersion.id.in_(version_ids)  # type: ignore[attr-defined]
            )
        )
        id_to_number = {row[0]: row[1] for row in rows}
        for w in workflows:
            if w.published_version_id is not None:
                w.published_version_number = id_to_number.get(w.published_version_id)

    async def _get_workflow_for_update(self, workflow_id: UUID) -> Workflow:
        """Get a workflow by ID with SELECT FOR UPDATE to prevent concurrent modifications."""
        result = await self.session.exec(
            select(Workflow)
            .filter(
                Workflow.id == workflow_id,  # type: ignore[arg-type]
                Workflow.deleted_at.is_(None),  # type: ignore[union-attr]
            )
            .with_for_update()
        )
        workflow = result.one_or_none()

        if not workflow:
            raise WorkflowNotFoundError(workflow_id)

        return workflow

    async def _check_expected_version(self, workflow: Workflow, expected_version: int | None) -> None:
        """Raise WorkflowVersionConflictError if the workflow has advanced past expected_version."""
        if expected_version is None or expected_version >= workflow.current_version:
            return

        username = "unknown"
        created_at = workflow.updated_at or datetime.now(UTC)
        version_name: str | None = None
        expected_version_name: str | None = None
        expected_created_at: datetime | None = None

        # Fetch both current and expected version rows in a single query
        result = await self.session.exec(
            select(WorkflowVersion, User)
            .outerjoin(User, WorkflowVersion.created_by == User.id)  # type: ignore[arg-type]
            .filter(
                WorkflowVersion.workflow_id == workflow.id,  # type: ignore[arg-type]
                WorkflowVersion.version.in_([workflow.current_version, expected_version]),  # type: ignore[attr-defined]
                WorkflowVersion.deleted_at.is_(None),  # type: ignore[union-attr]
            )
        )
        rows = result.all()

        for version_row, user in rows:
            if version_row.version == workflow.current_version:
                created_at = version_row.created_at or created_at
                version_name = version_row.name
                if user:
                    username = user.username
            elif version_row.version == expected_version:
                expected_version_name = version_row.name
                expected_created_at = version_row.created_at

        raise WorkflowVersionConflictError(
            workflow_id=workflow.id,
            current_version=workflow.current_version,
            expected_version=expected_version,
            created_by_username=username,
            created_at=created_at,
            current_version_name=version_name,
            expected_version_name=expected_version_name,
            expected_created_at=expected_created_at,
        )

    async def _get_webhook_sync_definition(
        self, workflow_id: UUID, workflow: Workflow, fallback_definition: dict[str, Any]
    ) -> dict[str, Any]:
        """Determine the workflow definition to sync to webhook triggers."""
        if workflow.published_version_id is not None:
            pub_result = await self.session.exec(
                select(WorkflowVersion).filter(
                    WorkflowVersion.id == workflow.published_version_id,  # type: ignore[arg-type]
                    WorkflowVersion.deleted_at.is_(None),  # type: ignore[union-attr]
                )
            )
            published_ver = pub_result.one_or_none()
            if published_ver:
                return published_ver.workflow_definition
            logger.warning(
                "Published version record not found",
                workflow_id=workflow_id,
                published_version_id=workflow.published_version_id,
            )
        return fallback_definition

    async def get_workflow_by_id(self, workflow_id: UUID) -> Workflow:
        """Get a workflow by ID.

        Args:
            workflow_id: Workflow UUID

        Returns:
            Workflow instance

        Raises:
            WorkflowNotFoundError: If workflow not found or deleted

        """
        result = await self.session.exec(
            select(Workflow).filter(
                Workflow.id == workflow_id,  # type: ignore[arg-type]
                Workflow.deleted_at.is_(None),  # type: ignore[union-attr]
            )
        )
        workflow = result.one_or_none()

        if not workflow:
            raise WorkflowNotFoundError(workflow_id)

        return workflow

    async def get_workflow_with_version(self, workflow_id: UUID) -> tuple[Workflow, WorkflowVersion]:
        """Get a workflow with its current active version.

        Args:
            workflow_id: Workflow UUID

        Returns:
            Tuple of (workflow, current version)

        Raises:
            WorkflowNotFoundError: If workflow not found or deleted
            WorkflowVersionNotFoundError: If current version not found

        """
        # Get workflow
        workflow = await self.get_workflow_by_id(workflow_id)

        # Get current version
        version_result = await self.session.exec(
            select(WorkflowVersion).filter(
                WorkflowVersion.workflow_id == workflow_id,  # type: ignore[arg-type]
                WorkflowVersion.version == workflow.current_version,  # type: ignore[arg-type]
                WorkflowVersion.deleted_at.is_(None),  # type: ignore[union-attr]
            )
        )
        current_version = version_result.one_or_none()

        if not current_version:
            raise WorkflowVersionNotFoundError(workflow_id, workflow.current_version)

        return workflow, current_version

    async def get_version_for_export(
        self,
        workflow_id: UUID,
        version: int,
    ) -> tuple[Workflow, WorkflowVersion]:
        """Get a workflow and specific version for export.

        Args:
            workflow_id: Workflow UUID
            version: Version number to export

        Returns:
            Tuple of (workflow, requested version)

        Raises:
            WorkflowNotFoundError: If workflow not found
            WorkflowVersionNotFoundError: If version not found

        """
        workflow = await self.get_workflow_by_id(workflow_id)
        version_record = await self._get_version_or_none(workflow_id, version)
        if not version_record:
            raise WorkflowVersionNotFoundError(workflow_id, version)
        AuditEventDispatcher.dispatch(
            WorkflowVersionExportedEvent(workflow_id=workflow_id, version=version, workflow_name=workflow.name)
        )
        return workflow, version_record

    async def update_version_metadata(
        self,
        workflow_id: UUID,
        version: int,
        name: str | None = None,
        change_description: str | None = None,
        *,
        fields_set: set[str] | None = None,
    ) -> WorkflowVersion:
        """Update a version's metadata (name, change_description).

        Args:
            workflow_id: Workflow UUID
            version: Version number to update
            name: New version name (or None to clear)
            change_description: New change description (or None to clear)
            fields_set: Fields explicitly present in the request body.
                When provided, only fields in this set are updated —
                this distinguishes "field absent" from "field explicitly null".

        Returns:
            Updated version record

        Raises:
            WorkflowNotFoundError: If workflow not found
            BuiltinWorkflowModifyError: If workflow is builtin
            WorkflowVersionNotFoundError: If version not found

        """
        workflow = await self.get_workflow_by_id(workflow_id)
        if workflow.is_builtin:
            raise BuiltinWorkflowModifyError(workflow.name)

        version_record = await self._get_version_or_none(workflow_id, version)
        if not version_record:
            raise WorkflowVersionNotFoundError(workflow_id, version)

        update_fields = fields_set if fields_set is not None else {"name", "change_description"}
        changed = False
        if "name" in update_fields:
            version_record.name = name
            changed = True
        if "change_description" in update_fields:
            version_record.change_description = change_description
            changed = True

        if not changed:
            return version_record

        version_record.updated_by = self.user.id
        await self.session.commit()
        await self.session.refresh(version_record)
        return version_record

    async def update_workflow_metadata(
        self,
        workflow: Workflow,
        name: str | None = None,
        description: str | None = None,
        labels: dict[str, Any] | None = None,
    ) -> None:
        """Update workflow metadata fields.

        Args:
            workflow: Workflow to update
            name: New name (optional)
            description: New description (optional)
            labels: New labels (optional)

        Raises:
            ValueError: If name is empty string

        Note:
            This method updates the workflow in-place. Caller must commit.

        """
        if name is not None:
            workflow_validator.validate_workflow_name(name)
            workflow.name = name

        if description is not None:
            workflow.description = description

        if labels is not None:
            workflow.labels = labels

        # Always update these fields when any metadata changes
        workflow.updated_at = datetime.now(UTC)
        workflow.updated_by = self.user.id

    async def create_workflow_version(
        self,
        workflow: Workflow,
        workflow_definition: dict[str, Any],
        change_description: str | None,
    ) -> tuple[WorkflowVersion | None, ValidationResult]:
        """Create new V2 workflow version from workflow_definition.

        Validates the definition before creating the version. For restoring
        previously-validated definitions, use ``_create_version_record`` directly.

        Args:
            workflow: Workflow to create version for
            workflow_definition: New V2 workflow definition as dict
            change_description: Description of changes

        Returns:
            Tuple of (new WorkflowVersion if definition changed or None if unchanged, validation result)

        Note:
            This method compares the new definition with the current version.
            If identical, no new version is created (returns None).

        """
        recorder = get_metrics_recorder()
        system_cof = await get_system_continue_on_failure()

        with recorder.time(
            MetricType.WORKFLOW_VALIDATION_DURATION,
            labels={"component": ComponentLabel.WORKFLOW_ENGINE.value, "operation": "version_update"},
        ):
            result = workflow_validator.collect_findings(
                workflow_definition,
                system_continue_on_failure=system_cof,
            )

        workflow.has_validation_issues = _has_validation_issues(result)
        if workflow.has_validation_issues:
            logger.warning(
                "Workflow version saved with validation issues",
                workflow_id=str(workflow.id),
                user_id=str(self.user.id),
                error_count=result.error_count,
                warning_count=result.warning_count,
                findings=[f.message for f in result.findings[:10]],
            )

        if workflow.project_id is not None:
            previous_cred_ids: set[str] | None = None
            if workflow.current_version is not None:
                prev_version = await self._get_version_or_none(workflow.id, workflow.current_version)
                if prev_version and prev_version.workflow_definition:
                    previous_cred_ids = self._extract_credential_ids(prev_version.workflow_definition)
            await self._validate_credential_project_scope(workflow_definition, workflow.project_id, previous_cred_ids)
            await self._validate_no_secret_url_conflicts(workflow_definition)
            ref_findings = await validate_workflow_references(self.session, workflow_definition, workflow.project_id)
            if ref_findings:
                result = ValidationResult.from_findings([*result.findings, *ref_findings])
                workflow.has_validation_issues = True

        version = await self._create_version_record(workflow, workflow_definition, change_description)
        return version, result

    async def update_workflow(
        self,
        workflow_id: UUID,
        name: str | None = None,
        description: str | None = None,
        labels: dict[str, Any] | None = None,
        *,
        project_id: UUID | None = None,
        workflow_definition: dict[str, Any] | None = None,
        change_description: str | None = None,
        expected_version: int | None = None,
    ) -> tuple[Workflow, WorkflowVersion, ValidationResult | None]:
        """Update workflow metadata and/or create new version.

        Args:
            workflow_id: UUID of workflow to update
            name: New name (optional)
            description: New description (optional)
            labels: New labels (optional)
            project_id: Rejected if different from stored value (immutable after creation)
            workflow_definition: New V2 workflow definition as dict (optional, creates version)
            change_description: Description of changes (for version history)
            expected_version: Version the client was editing (optimistic concurrency)

        Returns:
            Tuple of (updated workflow, current version, validation result or None)

        Raises:
            WorkflowNotFoundError: If workflow not found
            WorkflowNameConflictError: If new name conflicts
            WorkflowVersionConflictError: If expected_version is stale
            ValueError: If name is empty

        """
        workflow = await self._get_workflow_for_update(workflow_id)

        assert_project_id_unchanged(workflow.project_id, project_id)

        if workflow.is_builtin:
            raise BuiltinWorkflowModifyError(workflow.name)

        await self._check_expected_version(workflow, expected_version)

        # Update metadata fields
        if any([name is not None, description is not None, labels is not None]):
            await self.update_workflow_metadata(
                workflow,
                name=name,
                description=description,
                labels=labels,
            )

        # Capture old definition for audit change summary
        old_definition: dict[str, Any] | None = None
        if workflow_definition is not None:
            prev_version = await self._get_version_or_none(workflow.id, workflow.current_version)
            if prev_version:
                old_definition = prev_version.workflow_definition

        # Handle workflow_definition - creates new version
        new_version: WorkflowVersion | None = None
        validation_result: ValidationResult | None = None
        if workflow_definition is not None:
            new_version, validation_result = await self.create_workflow_version(
                workflow,
                workflow_definition=workflow_definition,
                change_description=change_description,
            )

        # Flush with name uniqueness check (stays within the same transaction)
        await self._flush_with_duplicate_check(workflow.name)
        await self.session.refresh(workflow)

        if new_version:
            await self.session.refresh(new_version)

        # Get current version for return
        _, current_version = await self.get_workflow_with_version(workflow_id)

        sync_definition = await self._get_webhook_sync_definition(
            workflow_id, workflow, current_version.workflow_definition
        )

        webhook_service = WebhookTriggerService(self.session, self.user)
        await self._sync_all_trigger_types(
            webhook_service,
            workflow.id,
            sync_definition,
            is_enabled=workflow.is_enabled,
        )

        # Single atomic commit (workflow metadata + version + triggers)
        try:
            await self.session.commit()
        except Exception as exc:
            self._emit_lifecycle_event(
                workflow_id=workflow.id,
                workflow_name=workflow.name,
                action=WorkflowAction.UPDATED,
                project_id=workflow.project_id,
                error_type=type(exc).__name__,
            )
            raise

        # Generate change summary for audit log only
        change_summary = generate_change_summary(old_definition, workflow_definition)

        self._emit_lifecycle_event(
            workflow_id=workflow.id,
            workflow_name=workflow.name,
            action=WorkflowAction.UPDATED,
            version=new_version.version if new_version else current_version.version,
            project_id=workflow.project_id,
            new_version_created=new_version is not None,
            change_summary=change_summary,
        )

        return workflow, current_version, validation_result

    async def publish_workflow_version(  # noqa: C901, PLR0915
        self,
        workflow_id: UUID,
        version: int,
        name: str | None = None,
        change_description: str | None = None,
        workflow_definition: dict[str, Any] | None = None,
        expected_version: int | None = None,
    ) -> tuple[Workflow, WorkflowVersion, str]:
        """Publish a workflow version via pointer update (no copy).

        Creates a ``WorkflowPublishEvent`` and points
        ``workflow.published_version_id`` at the target version.
        If ``workflow_definition`` is provided (atomic save-and-publish),
        a new version is created first via ``_create_version_record``,
        then published.

        Returns a tuple of (workflow, version, warning). Warning is
        populated when the DB commit succeeds but a non-critical post-commit
        operation fails gracefully (e.g. scheduled trigger sync).
        """
        workflow = await self._get_workflow_for_update(workflow_id)

        if workflow.is_builtin:
            raise BuiltinWorkflowModifyError(workflow.name)

        await self._check_expected_version(workflow, expected_version)

        target_version = await self._get_version_or_none(workflow_id, version)
        if not target_version:
            raise WorkflowVersionNotFoundError(workflow_id, version)

        if workflow_definition is not None:
            target_version = await self._create_and_flush_version(
                workflow, target_version, workflow_definition, change_description
            )

        definition = target_version.workflow_definition
        system_cof = await get_system_continue_on_failure()
        result = workflow_validator.collect_findings(
            definition,
            system_continue_on_failure=system_cof,
        )
        if len(definition.get("nodes", [])) == 0:
            result = ValidationResult.from_findings(
                [
                    *result.findings,
                    ValidationFinding(
                        severity=ValidationSeverity.error,
                        category=ValidationCategory.missing_field,
                        message="Workflow must have at least one step",
                    ),
                ]
            )
        if (result.error_count + result.warning_count) > 0:
            raise WorkflowPublishValidationError(result)

        stale_tool_findings: list[ValidationFinding] = []
        if workflow_definition is not None and workflow.project_id is not None:
            # Inline definition provided (atomic save-and-publish). At this point
            # target_version already points to the newly created version, so its
            # workflow_definition equals workflow_definition — diff-based previous_cred_ids
            # would be empty and skip the check. Pass None to treat all credentials in the
            # new definition as candidates for the credential:use check (safe and correct).
            await self._validate_credential_project_scope(
                workflow_definition, workflow.project_id, previous_credential_ids=None
            )
            await self._validate_no_secret_url_conflicts(workflow_definition)
            stale_tool_findings = await validate_workflow_references(
                self.session, workflow_definition, workflow.project_id
            )

        if workflow.published_version_id is not None and workflow.published_version_id != target_version.id:
            unpublish_event = WorkflowPublishEvent(
                workflow_id=workflow.id,
                version_id=workflow.published_version_id,
                action=PublishAction.UNPUBLISHED,
                actor_id=self.user.id,
            )
            self.session.add(unpublish_event)

        publish_event = WorkflowPublishEvent(
            workflow_id=workflow.id,
            version_id=target_version.id,
            action=PublishAction.PUBLISHED,
            actor_id=self.user.id,
        )
        self.session.add(publish_event)

        if name is not None:
            target_version.name = name
        if change_description is not None:
            target_version.change_description = change_description

        workflow.published_version_id = target_version.id
        workflow.is_enabled = True
        workflow.updated_at = datetime.now(UTC)
        workflow.updated_by = self.user.id

        await self._flush_with_duplicate_check(workflow.name)

        webhook_service = WebhookTriggerService(self.session, self.user)
        await self._sync_all_trigger_types(
            webhook_service,
            workflow.id,
            target_version.workflow_definition,
            is_enabled=True,
        )

        try:
            await self.session.commit()
        except Exception as exc:
            AuditEventDispatcher.dispatch(
                WorkflowVersionPublishedEvent(
                    workflow_id=workflow.id,
                    version=target_version.version,
                    workflow_name=workflow.name,
                    project_id=workflow.project_id,
                    error_type=type(exc).__name__,
                )
            )
            raise

        warning: str = ""
        try:
            await self._sync_scheduled_triggers(
                workflow.id,
                target_version.workflow_definition,
            )
        except ScheduledTriggerSyncError as exc:
            logger.warning(
                "Scheduled trigger sync failed during publish",
                workflow_id=str(workflow.id),
                error=str(exc),
            )
            warning = (
                "Scheduled triggers could not be activated because the scheduling service is "
                "temporarily unavailable. They will be activated automatically when the service recovers."
            )

        if stale_tool_findings:
            stale_msg = "; ".join(f.message for f in stale_tool_findings)
            warning = "; ".join(filter(None, [warning, stale_msg]))

        AuditEventDispatcher.dispatch(
            WorkflowVersionPublishedEvent(
                workflow_id=workflow.id,
                version=target_version.version,
                workflow_name=workflow.name,
                project_id=workflow.project_id,
            )
        )

        return workflow, target_version, warning

    async def unpublish_workflow(self, workflow_id: UUID) -> Workflow:
        """Unpublish the currently published version."""
        workflow = await self._get_workflow_for_update(workflow_id)

        if workflow.is_builtin:
            raise BuiltinWorkflowModifyError(workflow.name)

        if workflow.published_version_id is None:
            raise WorkflowNotPublishedError(workflow_id)

        published_version = await self.session.get(WorkflowVersion, workflow.published_version_id)
        if not published_version:
            logger.warning(
                "Published version record not found during unpublish",
                workflow_id=str(workflow_id),
                published_version_id=str(workflow.published_version_id),
            )
        version_number = published_version.version if published_version else 0

        unpublish_event = WorkflowPublishEvent(
            workflow_id=workflow.id,
            version_id=workflow.published_version_id,
            action=PublishAction.UNPUBLISHED,
            actor_id=self.user.id,
        )
        self.session.add(unpublish_event)

        workflow.published_version_id = None
        workflow.is_enabled = False
        workflow.updated_at = datetime.now(UTC)
        workflow.updated_by = self.user.id

        webhook_service = WebhookTriggerService(self.session, self.user)
        if published_version:
            await self._sync_all_trigger_types(
                webhook_service,
                workflow.id,
                published_version.workflow_definition,
                is_enabled=False,
            )

        try:
            await self.session.commit()
        except Exception as exc:
            AuditEventDispatcher.dispatch(
                WorkflowVersionUnpublishedEvent(
                    workflow_id=workflow.id,
                    version=version_number,
                    workflow_name=workflow.name,
                    project_id=workflow.project_id,
                    error_type=type(exc).__name__,
                )
            )
            raise

        AuditEventDispatcher.dispatch(
            WorkflowVersionUnpublishedEvent(
                workflow_id=workflow.id,
                version=version_number,
                workflow_name=workflow.name,
                project_id=workflow.project_id,
            )
        )

        await self._delete_scheduled_triggers(workflow.id)

        return workflow

    async def restore_workflow_version(
        self,
        workflow_id: UUID,
        version: int,
    ) -> tuple[Workflow, WorkflowVersion]:
        """Restore a previous workflow version as a new draft.

        Copies the target version's workflow_definition into a new draft version,
        which becomes the latest version.

        Design decisions (see hakbailey review on PR #1063):

        - **No trigger sync**: Restore only creates a draft — it does not change
          the published version. Trigger sync resolves to the published version's
          definition (unaffected by restore) or disables triggers when unpublished.
          Syncing here would be a no-op that adds data-loss risk, since
          ``WebhookTriggerService.sync_webhook_triggers`` calls ``session.rollback()``
          on ``IntegrityError``, which could discard the uncommitted restore.

        - **No re-validation**: The restored definition was validated when originally
          saved. Skipping validation ensures old versions remain restorable even if
          validation rules tighten — restore is a data-recovery operation that should
          not be gated on current-time constraints.

        Args:
            workflow_id: UUID of the workflow
            version: Version number to restore

        Returns:
            Tuple of (workflow, restored version)

        Raises:
            WorkflowNotFoundError: If workflow not found
            WorkflowVersionNotFoundError: If target version not found

        """
        workflow = await self._get_workflow_for_update(workflow_id)

        if workflow.is_builtin:
            raise BuiltinWorkflowModifyError(workflow.name)

        target_version = await self._get_version_or_none(workflow_id, version)
        if not target_version:
            raise WorkflowVersionNotFoundError(workflow_id, version)

        # Capture current definition for audit change summary
        current_version_record = await self._get_version_or_none(workflow.id, workflow.current_version)
        old_definition = current_version_record.workflow_definition if current_version_record else None

        date_iso = target_version.created_at.isoformat() if target_version.created_at else None
        source_label = target_version.name or date_iso or f"version {version}"
        new_version = await self._create_version_record(
            workflow,
            workflow_definition=target_version.workflow_definition,
            change_description=f"Restored from {source_label}",
        )

        if not new_version:
            _, current_version = await self.get_workflow_with_version(workflow_id)
            return workflow, current_version

        workflow.updated_at = datetime.now(UTC)
        workflow.updated_by = self.user.id

        try:
            await self.session.commit()
        except Exception as exc:
            AuditEventDispatcher.dispatch(
                WorkflowVersionRestoredEvent(
                    workflow_id=workflow.id,
                    restored_from_version=version,
                    new_version=new_version.version,
                    workflow_name=workflow.name,
                    project_id=workflow.project_id,
                    error_type=type(exc).__name__,
                )
            )
            raise

        await self.session.refresh(workflow)
        await self.session.refresh(new_version)

        # Generate change summary for audit log only
        restore_change_summary = generate_change_summary(old_definition, target_version.workflow_definition)

        # Intentional dual emission: "created" tracks total versions, "restored" tracks rollbacks
        self._emit_lifecycle_event(
            workflow_id=workflow.id,
            workflow_name=workflow.name,
            action=WorkflowAction.RESTORED,
            version=new_version.version,
            project_id=workflow.project_id,
            new_version_created=True,
            change_summary=restore_change_summary,
        )
        AuditEventDispatcher.dispatch(
            WorkflowVersionRestoredEvent(
                workflow_id=workflow.id,
                restored_from_version=version,
                new_version=new_version.version,
                workflow_name=workflow.name,
                project_id=workflow.project_id,
            )
        )
        return workflow, new_version

    async def delete_workflow(self, workflow_id: UUID) -> None:
        """Soft delete a workflow.

        Args:
            workflow_id: UUID of workflow to delete

        Raises:
            WorkflowNotFoundError: If workflow not found

        """
        workflow = await self.get_workflow_by_id(workflow_id)

        if workflow.is_builtin:
            raise BuiltinWorkflowDeleteError(workflow.name)

        # Delete associated webhook triggers before soft-deleting the workflow
        webhook_service = WebhookTriggerService(self.session, self.user)
        await webhook_service.delete_triggers_for_workflow(workflow_id)

        # Soft delete
        workflow.soft_delete(self.user.id)
        try:
            await self.session.commit()
        except Exception as exc:
            self._emit_lifecycle_event(
                workflow_id=workflow.id,
                workflow_name=workflow.name,
                action=WorkflowAction.DELETED,
                project_id=workflow.project_id,
                error_type=type(exc).__name__,
            )
            raise

        self._emit_lifecycle_event(
            workflow_id=workflow.id,
            workflow_name=workflow.name,
            action=WorkflowAction.DELETED,
            project_id=workflow.project_id,
        )

        await self._delete_scheduled_triggers(workflow_id)
