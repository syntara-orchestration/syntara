"""Project service for business logic."""

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import delete, update
from sqlmodel import select
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
            SafeValueError: If project not found or deleted.

        """
        result = await self.session.exec(
            select(Project).where(
                Project.id == project_id,
                Project.deleted_at.is_(None),  # type: ignore[union-attr]
            )
        )
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
        """List non-deleted projects, filtered by authorization.

        Args:
            allowed_projects: When provided, filters to only projects the user
                can access. If all_projects is True, no filtering is applied.

        Returns:
            List of projects.

        """
        query = select(Project).where(
            Project.deleted_at.is_(None),  # type: ignore[union-attr]
        )

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
        """Soft-delete a project and cascade-clean all project-scoped resources.

        Args:
            project_id: Project UUID.

        Raises:
            SafeValueError: If project not found.

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
        await self._cascade_cleanup_project_resources(project_id)
        project.soft_delete(self.user.id)
        self.session.add(project)
        await self.session.commit()

    async def _cascade_cleanup_project_resources(self, project_id: UUID) -> None:
        """Remove all project-scoped resources before soft-deleting the project.

        Uses bulk SQL for efficiency. Ordering respects FK constraints.
        Soft-deletable resources are soft-deleted; others are hard-deleted.
        """
        from syntara.approvals.models.approval_request import ApprovalRequest  # noqa: PLC0415
        from syntara.authz.models.policy import Policy  # noqa: PLC0415
        from syntara.authz.models.role import Role  # noqa: PLC0415
        from syntara.core.models.secret import EncryptedSecret, Secret  # noqa: PLC0415
        from syntara.credentials.models.credential import Credential  # noqa: PLC0415
        from syntara.workflows.models.execution import Execution  # noqa: PLC0415
        from syntara.workflows.models.workflow import Workflow  # noqa: PLC0415
        from syntara.workflows.models.workflow_version import WorkflowVersion  # noqa: PLC0415

        now = datetime.now(UTC)
        user_id = self.user.id

        # Step 1: Hard-delete approval requests
        await self.session.exec(
            delete(ApprovalRequest).where(ApprovalRequest.project_id == project_id)  # type: ignore[arg-type]
        )

        # Step 2: Soft-delete executions
        await self.session.exec(
            update(Execution)
            .where(
                Execution.project_id == project_id,  # type: ignore[arg-type]
                Execution.deleted_at.is_(None),  # type: ignore[union-attr]
            )
            .values(deleted_at=now, deleted_by=user_id)
        )

        # Step 3: Soft-delete workflow versions (no direct project_id, found via workflow)
        workflow_ids_subq = select(Workflow.id).where(Workflow.project_id == project_id).scalar_subquery()
        await self.session.exec(
            update(WorkflowVersion)
            .where(
                WorkflowVersion.workflow_id.in_(workflow_ids_subq),  # type: ignore[attr-defined]
                WorkflowVersion.deleted_at.is_(None),  # type: ignore[union-attr]
            )
            .values(deleted_at=now, deleted_by=user_id)
        )

        # Step 4: Soft-delete workflows
        await self.session.exec(
            update(Workflow)
            .where(
                Workflow.project_id == project_id,  # type: ignore[arg-type]
                Workflow.deleted_at.is_(None),  # type: ignore[union-attr]
            )
            .values(deleted_at=now, deleted_by=user_id)
        )

        # Step 5: Collect secret IDs, null FK, delete secrets, then hard-delete credentials
        secret_ids_result = await self.session.exec(
            select(Credential.secret_id).where(
                Credential.project_id == project_id,
                Credential.secret_id.isnot(None),  # type: ignore[union-attr]
            )
        )
        secret_ids = list(secret_ids_result.all())

        # Null secret_id (breaks FK before secret deletion)
        await self.session.exec(
            update(Credential)
            .where(Credential.project_id == project_id)  # type: ignore[arg-type]
            .values(secret_id=None)
        )

        # Delete secrets
        if secret_ids:
            await self.session.exec(
                delete(EncryptedSecret).where(
                    EncryptedSecret.secret_id.in_(secret_ids)  # type: ignore[attr-defined]
                )
            )
            await self.session.exec(
                delete(Secret).where(Secret.id.in_(secret_ids))  # type: ignore[attr-defined]
            )

        # Hard-delete credentials
        await self.session.exec(
            delete(Credential).where(Credential.project_id == project_id)  # type: ignore[arg-type]
        )

        # Step 6: Hard-delete role assignments
        await self.session.exec(
            delete(RoleAssignment).where(RoleAssignment.project_id == project_id)  # type: ignore[arg-type]
        )

        # Step 7: Hard-delete custom roles
        await self.session.exec(
            delete(Role).where(Role.project_id == project_id)  # type: ignore[arg-type]
        )

        # Step 8: Hard-delete custom policies
        await self.session.exec(
            delete(Policy).where(Policy.project_id == project_id)  # type: ignore[arg-type]
        )

        logger.info("Cascade-cleaned project resources", project_id=str(project_id))
