"""Project service for business logic."""

from collections.abc import Iterable
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import delete, update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.engine import AllowedProjectsResult, assign_authenticated_group_project_user, assign_project_admin
from syntara.authz.models.assignments import RoleAssignment
from syntara.authz.models.project import Project
from syntara.core.models import User
from syntara.core.services import BaseService
from syntara.projects.schemas import ProjectListResponse

logger = structlog.stdlib.get_logger(__name__)


class ProjectService(BaseService):
    """Service for project CRUD and role management."""

    def __init__(self, session: AsyncSession, user: User) -> None:
        """Initialize with database session and current user."""
        super().__init__(session, user)

    async def create_project(
        self,
        name: str,
        description: str | None = None,
        labels: dict[str, Any] | None = None,
    ) -> Project:
        """Create a project and assign the creator as project-admin.

        Args:
            name: Project name (must be unique).
            description: Optional description.
            labels: Optional key-value labels.

        Returns:
            The created project.

        """
        project = Project(
            name=name,
            description=description,
            labels=labels or {},
        )
        self.session.add(project)
        await self.session.flush()

        # Auto-assign creator as project-admin
        await assign_project_admin(self.session, self.user.id, project.id)

        # If this is a default project, grant all authenticated users access
        if project.is_default:
            await assign_authenticated_group_project_user(self.session, project.id)

        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def get_project(self, project_id: UUID) -> Project:
        """Get a project by ID.

        Args:
            project_id: Project UUID.

        Returns:
            The project.

        Raises:
            ProjectNotFoundError: If project not found.

        """
        result = await self.session.exec(select(Project).where(Project.id == project_id))
        project = result.first()
        if not project:
            from syntara.authz.exceptions import ProjectNotFoundError  # noqa: PLC0415

            msg = f"Project {project_id} not found"
            raise ProjectNotFoundError(msg)
        return project

    async def list_projects(
        self,
        allowed_projects: AllowedProjectsResult | None = None,
    ) -> list[Project]:
        """List projects, filtered by authorization.

        Args:
            allowed_projects: When provided, filters to only projects the user
                can access. If all_projects is True, no filtering is applied.

        Returns:
            List of projects.

        """
        query = select(Project)

        if allowed_projects is not None and not allowed_projects.all_projects:
            if not allowed_projects.project_ids:
                return []
            query = query.where(Project.id.in_(allowed_projects.project_ids))  # type: ignore[attr-defined]

        result = await self.session.exec(query)
        return list(result.all())

    async def list_projects_cursor(
        self,
        limit: int = 20,
        cursor: str | None = None,
        sort: str | None = None,
        query_params_items: Iterable[tuple[str, str]] | None = None,
        *,
        include_total: bool = False,
        allowed_projects: AllowedProjectsResult | None = None,
    ) -> ProjectListResponse:
        """List projects with cursor-based pagination.

        Args:
            limit: Maximum number of projects to return (default 20)
            cursor: Cursor token for pagination
            sort: Sort parameter (e.g., "name", "-created_at")
            query_params_items: Raw query parameter items from request (for filtering)
            include_total: Whether to include total count in response
            allowed_projects: Authorization filter for project visibility

        Returns:
            ProjectListResponse with projects, pagination metadata, and optional total

        """
        # For projects, allowed_projects maps directly to id_restriction since
        # the allowed project IDs ARE the resource IDs being listed.
        id_restriction: list[UUID] | None = None
        if allowed_projects is not None and not allowed_projects.all_projects:
            if not allowed_projects.project_ids:
                return ProjectListResponse(resources=[], next=None, prev=None, total=0 if include_total else None)
            id_restriction = allowed_projects.project_ids

        return await self.list_resources(
            model=Project,
            response_type=ProjectListResponse,
            limit=limit,
            cursor=cursor,
            sort=sort or "-created_at",
            query_params_items=query_params_items,
            include_total=include_total,
            id_restriction=id_restriction,
        )

    async def update_project(
        self,
        project_id: UUID,
        name: str | None = None,
        description: str | None = None,
        labels: dict[str, Any] | None = None,
    ) -> Project:
        """Update a project.

        Args:
            project_id: Project UUID.
            name: New name (optional).
            description: New description (optional).
            labels: New labels (optional).

        Returns:
            The updated project.

        Raises:
            SafeValueError: If project not found.

        """
        project = await self.get_project(project_id)
        if project.is_builtin:
            from syntara.authz.exceptions import BuiltinProtectionError  # noqa: PLC0415

            msg = f"The built-in '{project.name}' project cannot be modified"
            raise BuiltinProtectionError(msg)
        if name is not None:
            project.name = name
        if description is not None:
            project.description = description
        if labels is not None:
            project.labels = labels
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def delete_project(self, project_id: UUID) -> None:
        """Hard-delete a project and cascade-delete all project-scoped resources.

        All child resources (workflows, executions, invocations, credentials,
        etc.) are permanently removed. The audit log serves as the historical
        record.

        Args:
            project_id: Project UUID.

        Raises:
            ProjectNotFoundError: If project not found.

        """
        project = await self.get_project(project_id)
        if project.is_builtin:
            from syntara.authz.exceptions import BuiltinProtectionError  # noqa: PLC0415

            msg = f"The built-in '{project.name}' project cannot be deleted"
            raise BuiltinProtectionError(msg)
        if project.is_default:
            from syntara.authz.exceptions import DefaultProjectProtectionError  # noqa: PLC0415

            msg = "Default project cannot be deleted"
            raise DefaultProjectProtectionError(msg)
        await self._check_no_active_executions(project_id)
        await self._check_credentials_not_referenced_by_integrations(project.id, project.name)
        await self._cascade_cleanup_project_resources(project_id)
        await self.session.delete(project)
        await self.session.commit()

    async def _check_no_active_executions(self, project_id: UUID) -> None:
        """Raise 409 if the project has any non-terminal executions.

        Deleting a project cascade-deletes all executions. Purging in-flight
        executions would orphan Temporal workflows, so we require the caller
        to cancel or wait for them first.
        """
        from sqlalchemy import func  # noqa: PLC0415

        from syntara.authz.exceptions import ProjectHasActiveExecutionsError  # noqa: PLC0415
        from syntara.workflows.models.execution import TERMINAL_EXECUTION_STATUSES, Execution  # noqa: PLC0415

        result = await self.session.exec(
            select(func.count())
            .select_from(Execution)
            .where(
                Execution.project_id == project_id,
                col(Execution.status).not_in(TERMINAL_EXECUTION_STATUSES),
            )
        )
        active_count = result.one() or 0
        if active_count:
            raise ProjectHasActiveExecutionsError(project_id, active_count)

    async def _check_credentials_not_referenced_by_integrations(self, project_id: UUID, project_name: str) -> None:
        """Raise 409 if any credential in this project is still referenced by an integration.

        Integrations are not project-scoped — a global integration can reference
        a project credential as its management credential. The ON DELETE RESTRICT
        FK on integrations.management_credential_id makes the database reject the
        bulk credential DELETE in the cascade, so we fail early with an actionable
        message instead of letting PostgreSQL surface a generic constraint error.

        Accepts plain values instead of the Project ORM object to avoid any risk
        of lazy-loading ORM attributes outside a greenlet context after the async
        queries inside this method.
        """
        from sqlalchemy import func  # noqa: PLC0415

        from syntara.credentials.exceptions import ProjectCredentialInUseError  # noqa: PLC0415
        from syntara.credentials.models.credential import Credential  # noqa: PLC0415
        from syntara.integrations.models.integration import Integration  # noqa: PLC0415

        cred_ids_subq = select(Credential.id).where(Credential.project_id == project_id).scalar_subquery()

        count_result = await self.session.exec(
            select(func.count()).where(
                Integration.management_credential_id.in_(cred_ids_subq)  # type: ignore[union-attr]
            )
        )
        total_count = count_result.one()
        if not total_count:
            return

        names_result = await self.session.exec(
            select(Integration.name, Credential.name)
            .join(Credential, Integration.management_credential_id == Credential.id)  # type: ignore[arg-type]
            .where(Integration.management_credential_id.in_(cred_ids_subq))  # type: ignore[union-attr]
            .order_by(Integration.name)
            .limit(5)
        )
        rows = list(names_result.all())
        integration_names = [r[0] for r in rows]
        credential_names = list(dict.fromkeys(r[1] for r in rows))

        raise ProjectCredentialInUseError(project_name, credential_names, integration_names, total_count)

    async def _cascade_cleanup_project_resources(self, project_id: UUID) -> None:
        """Delete all project-scoped resources before hard-deleting the project.

        Uses bulk SQL for efficiency. Ordering respects FK constraints.
        External side-effects (Temporal schedules, file storage) are best-effort.
        """
        from sqlalchemy import func as sa_func  # noqa: PLC0415
        from sqlmodel import col  # noqa: PLC0415

        from syntara.agent_orchestrator.models.invocation import Invocation  # noqa: PLC0415
        from syntara.approvals.models.approval_request import ApprovalRequest  # noqa: PLC0415
        from syntara.authz.exceptions import ProjectHasActiveExecutionsError  # noqa: PLC0415
        from syntara.authz.models.policy import Policy  # noqa: PLC0415
        from syntara.authz.models.role import Role  # noqa: PLC0415
        from syntara.core.models.secret import EncryptedSecret, Secret  # noqa: PLC0415
        from syntara.credentials.models.credential import Credential  # noqa: PLC0415
        from syntara.files.models.file_metadata import FileMetadata  # noqa: PLC0415
        from syntara.integrations.models.integration import IntegrationProjectAssignment  # noqa: PLC0415
        from syntara.service_accounts.models.service_account import ServiceAccount  # noqa: PLC0415
        from syntara.service_accounts.models.service_account_credential import ServiceAccountCredential  # noqa: PLC0415
        from syntara.workflows.models.execution import TERMINAL_EXECUTION_STATUSES, Execution  # noqa: PLC0415
        from syntara.workflows.models.webhook_trigger import WebhookTrigger  # noqa: PLC0415
        from syntara.workflows.models.workflow import Workflow  # noqa: PLC0415
        from syntara.workflows.models.workflow_version import WorkflowVersion  # noqa: PLC0415

        # Step 1: Lock workflow rows FOR UPDATE to prevent new executions from being
        # created while we check and delete.  Any concurrent create_execution() will
        # block on the workflow SELECT until this transaction commits or rolls back,
        # closing the TOCTOU race between the active-execution check and the DELETE.
        result = await self.session.exec(select(Workflow).where(Workflow.project_id == project_id).with_for_update())
        locked_workflows = list(result.all())
        locked_wf_ids = [w.id for w in locked_workflows]

        if locked_wf_ids:
            non_terminal_count = await self.session.scalar(
                select(sa_func.count())
                .select_from(Execution)
                .where(
                    col(Execution.workflow_id).in_(locked_wf_ids),
                    col(Execution.status).not_in(TERMINAL_EXECUTION_STATUSES),
                )
            )
            if non_terminal_count:
                raise ProjectHasActiveExecutionsError(project_id, non_terminal_count)

        # --- External cleanup (best-effort, must run BEFORE DB deletes) ---
        # _cleanup_file_storage reads FileMetadata rows to get storage paths,
        # so it must precede the file_metadata DELETE below.
        await self._cleanup_temporal_schedules(project_id)
        await self._cleanup_file_storage(project_id)

        # --- Delete child resources (order respects FK constraints) ---

        # 1. Approval requests
        await self.session.exec(
            delete(ApprovalRequest).where(ApprovalRequest.project_id == project_id)  # type: ignore[arg-type]
        )

        # 2. Invocations
        await self.session.exec(
            delete(Invocation).where(Invocation.project_id == project_id)  # type: ignore[arg-type]
        )

        # 3. Executions (must precede workflow deletion)
        await self.session.exec(
            delete(Execution).where(Execution.project_id == project_id)  # type: ignore[arg-type]
        )

        # 4. Workflows (clear published_version_id first to avoid self-ref FK,
        #    delete webhook triggers, then versions before workflows — FK is RESTRICT, not CASCADE)
        await self.session.exec(
            update(Workflow)
            .where(Workflow.project_id == project_id)  # type: ignore[arg-type]
            .values(published_version_id=None, is_enabled=False)
        )
        wf_ids_subq = select(Workflow.id).where(Workflow.project_id == project_id).scalar_subquery()
        await self.session.exec(
            delete(WebhookTrigger).where(WebhookTrigger.workflow_id.in_(wf_ids_subq))  # type: ignore[attr-defined]
        )
        await self.session.exec(delete(WorkflowVersion).where(col(WorkflowVersion.workflow_id).in_(wf_ids_subq)))
        await self.session.exec(
            delete(Workflow).where(Workflow.project_id == project_id)  # type: ignore[arg-type]
        )

        # 5. Credentials + secrets
        secret_ids_result = await self.session.exec(
            select(Credential.secret_id).where(
                Credential.project_id == project_id,
                Credential.secret_id.isnot(None),  # type: ignore[union-attr]
            )
        )
        secret_ids = list(secret_ids_result.all())

        await self.session.exec(
            delete(Credential).where(Credential.project_id == project_id)  # type: ignore[arg-type]
        )
        if secret_ids:
            await self.session.exec(delete(EncryptedSecret).where(col(EncryptedSecret.secret_id).in_(secret_ids)))
            await self.session.exec(delete(Secret).where(col(Secret.id).in_(secret_ids)))

        # 6. File metadata
        await self.session.exec(
            delete(FileMetadata).where(FileMetadata.project_id == project_id)  # type: ignore[arg-type]
        )

        # 7. Integration project assignments (junction table)
        await self.session.exec(
            delete(IntegrationProjectAssignment).where(IntegrationProjectAssignment.project_id == project_id)  # type: ignore[arg-type]
        )

        # 8. Service account credentials (must precede service_accounts — FK has no CASCADE)
        sa_ids_subq = select(ServiceAccount.id).where(ServiceAccount.project_id == project_id).scalar_subquery()
        await self.session.exec(
            delete(ServiceAccountCredential).where(col(ServiceAccountCredential.service_account_id).in_(sa_ids_subq))
        )

        # 8b. Service accounts
        await self.session.exec(
            delete(ServiceAccount).where(ServiceAccount.project_id == project_id)  # type: ignore[arg-type]
        )

        # 9. Role assignments
        await self.session.exec(
            delete(RoleAssignment).where(RoleAssignment.project_id == project_id)  # type: ignore[arg-type]
        )

        # 10. Custom roles
        await self.session.exec(
            delete(Role).where(Role.project_id == project_id)  # type: ignore[arg-type]
        )

        # 11. Custom policies
        await self.session.exec(
            delete(Policy).where(Policy.project_id == project_id)  # type: ignore[arg-type]
        )

        logger.info("Cascade-deleted project resources", project_id=str(project_id))

    async def _cleanup_temporal_schedules(self, project_id: UUID) -> None:
        """Best-effort cleanup of Temporal scheduled triggers for all project workflows."""
        try:
            from syntara.workflows.exceptions import ScheduledTriggerSyncError  # noqa: PLC0415
            from syntara.workflows.models.workflow import Workflow  # noqa: PLC0415
            from syntara.workflows.services.scheduled_trigger_service import ScheduledTriggerService  # noqa: PLC0415

            result = await self.session.exec(select(Workflow.id).where(Workflow.project_id == project_id))
            workflow_ids = list(result.all())
            if workflow_ids:
                trigger_svc = ScheduledTriggerService()
                for wf_id in workflow_ids:
                    try:
                        await trigger_svc.delete_triggers_for_workflow(str(wf_id))
                    except (OSError, RuntimeError, ScheduledTriggerSyncError):
                        logger.warning(
                            "Failed to clean Temporal triggers for workflow",
                            workflow_id=str(wf_id),
                            project_id=str(project_id),
                            exc_info=True,
                        )
        except (OSError, RuntimeError, ImportError, ScheduledTriggerSyncError):
            logger.warning(
                "Failed to clean Temporal schedules for project",
                project_id=str(project_id),
                exc_info=True,
            )

    async def _cleanup_file_storage(self, project_id: UUID) -> None:
        """Best-effort cleanup of files from object storage."""
        try:
            from syntara.files.exceptions import FileError, FileStorageUnavailableError  # noqa: PLC0415
            from syntara.files.file_manager import FileManager  # noqa: PLC0415
            from syntara.files.models.file_metadata import FileMetadata  # noqa: PLC0415

            result = await self.session.exec(select(FileMetadata).where(FileMetadata.project_id == project_id))
            files = list(result.all())
            if files:
                fm = FileManager()
                retriever = fm.get_retriever()
                for f in files:
                    try:
                        await retriever.delete_file(f.file_path)
                        if f.converted_content_path:
                            await retriever.delete_file(f.converted_content_path)
                    except (OSError, FileError):
                        logger.warning(
                            "Failed to delete file from storage",
                            file_id=str(f.id),
                            path=f.file_path,
                            exc_info=True,
                        )
        except (OSError, ImportError, FileError, FileStorageUnavailableError):
            logger.warning(
                "Failed to clean file storage for project",
                project_id=str(project_id),
                exc_info=True,
            )
