"""Authorization dependencies for FastAPI endpoints."""

import time
from uuid import UUID

import structlog
from fastapi import Depends, Request
from fastapi.exceptions import RequestValidationError
from sqlmodel import SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth.dependencies import get_current_user
from syntara.authz.engine import (
    AllowedProjectsResult,
    AuthzRequest,
    AuthzResult,
    VisibilityResult,
    authorize,
    resolve_allowed_projects,
    resolve_visibility,
)
from syntara.authz.evaluator import AuthzEvaluator
from syntara.authz.exceptions import AuthorizationDeniedError
from syntara.authz.models.project import Project
from syntara.core.database.session import get_db
from syntara.core.models.base import NamedResource
from syntara.core.models.user import User

logger = structlog.stdlib.get_logger(__name__)


def _record_authz_duration(start: float, resource_type: str, action: str) -> None:
    """Record authz check duration via the metrics recorder (fire-and-forget)."""
    try:
        from syntara.metrics.dependencies import get_metrics_recorder  # noqa: PLC0415
        from syntara.metrics.types import MetricType  # noqa: PLC0415

        duration_ms = (time.perf_counter() - start) * 1000
        get_metrics_recorder().record(
            MetricType.AUTHZ_DURATION,
            duration_ms,
            unit="ms",
            labels={"resource_type": resource_type, "action": action},
        )
    except Exception:  # noqa: BLE001
        logger.debug("authz_metrics_recording_failed", exc_info=True)


def get_authz_evaluator(request: Request) -> AuthzEvaluator:
    """Get the authorization evaluator from app state.

    Args:
        request: FastAPI request.

    Returns:
        Authorization evaluator instance.

    """
    evaluator: AuthzEvaluator = request.app.state.authz_evaluator
    return evaluator


class PermissionChecker:
    """FastAPI dependency that checks authorization via the authz evaluator.

    Usage:
        @router.post("", dependencies=[Depends(PermissionChecker("workflow", "create"))])
        async def create_workflow(...):
            ...

    For project-scoped checks, pass project_param to extract the project name
    from the path:
        Depends(PermissionChecker("project", "update", project_param="project_id"))

    """

    def __init__(
        self,
        resource_type: str,
        action: str,
        *,
        project_param: str | None = None,
        resource_model: type[SQLModel] | None = None,
        resource_id_param: str | None = None,
        body_project_field: str | None = None,
        form_project_field: str | None = None,
    ) -> None:
        """Initialize permission checker.

        Args:
            resource_type: The resource type (e.g., "workflow", "project").
            action: The action being performed (e.g., "read", "create", "delete").
            project_param: Path parameter name for project-scoped checks. When set,
                the checker looks up the project name from the database using this
                path parameter's UUID value.
            resource_model: SQLModel class with a project_id field. When set together
                with resource_id_param, the checker looks up the resource's project_id
                to enable project-scoped permission checks on single-resource endpoints.
            resource_id_param: Path parameter name for the resource ID (used with
                resource_model to look up project_id).
            body_project_field: JSON body field name containing a project UUID (e.g.,
                "project_id"). Used for create endpoints where the project context
                comes from the request body rather than the URL path.
            form_project_field: Multipart form field name containing a project UUID.
                Used for multipart/form-data endpoints where ``body_project_field``
                cannot be used (``request.json()`` fails on multipart forms).

        """
        self.resource_type = resource_type
        self.action = action
        self.project_param = project_param
        self.resource_model = resource_model
        self.resource_id_param = resource_id_param
        self.body_project_field = body_project_field
        self.form_project_field = form_project_field

    async def _resolve_project_name(self, db: AsyncSession, project_id: str | UUID) -> str:
        """Look up project name by ID, returning empty string if not found."""
        result = await db.exec(
            select(Project.name).where(
                Project.id == (project_id if isinstance(project_id, UUID) else UUID(str(project_id))),
                Project.deleted_at.is_(None),  # type: ignore[union-attr]
            )
        )
        return result.first() or ""

    async def _resolve_project_from_resource(self, db: AsyncSession, resource_id: str) -> str:
        """Look up project name from a resource's project_id field."""
        if not self.resource_model or not resource_id:
            return ""
        model = self.resource_model
        try:
            rid = UUID(str(resource_id))
        except ValueError:
            raise RequestValidationError(
                [
                    {
                        "type": "uuid_parsing",
                        "loc": ("path", self.resource_id_param or "id"),
                        "msg": f"Invalid UUID format: {resource_id}",
                        "input": resource_id,
                    }
                ]
            ) from None
        res = await db.exec(
            select(model.project_id).where(model.id == rid)  # type: ignore[attr-defined]
        )
        proj_id = res.first()
        if not proj_id:
            return ""
        return await self._resolve_project_name(db, proj_id)

    async def _resolve_resource_labels(self, db: AsyncSession, resource_id: str) -> dict[str, str]:
        """Look up resource labels by ID."""
        if not self.resource_model or not resource_id:
            return {}
        model = self.resource_model
        try:
            rid = UUID(str(resource_id))
        except ValueError:
            raise RequestValidationError(
                [
                    {
                        "type": "uuid_parsing",
                        "loc": ("path", self.resource_id_param or "id"),
                        "msg": f"Invalid UUID format: {resource_id}",
                        "input": resource_id,
                    }
                ]
            ) from None
        res = await db.exec(
            select(model.labels).where(model.id == rid)  # type: ignore[attr-defined]
        )
        return res.first() or {}

    async def _resolve_resource_name(self, db: AsyncSession, resource_id: str) -> str:
        """Look up resource name by ID for audit logging."""
        if not self.resource_model or not resource_id:
            return ""
        model = self.resource_model
        if not issubclass(model, NamedResource):
            return ""
        try:
            rid = UUID(str(resource_id))
        except ValueError:
            raise RequestValidationError(
                [
                    {
                        "type": "uuid_parsing",
                        "loc": ("path", self.resource_id_param or "id"),
                        "msg": f"Invalid UUID format: {resource_id}",
                        "input": resource_id,
                    }
                ]
            ) from None
        res = await db.exec(select(col(model.name)).where(model.id == rid))
        return res.first() or ""

    async def _resolve_project_from_path(self, request: Request, db: AsyncSession) -> str:
        """Resolve project name from the project_param path parameter."""
        if not self.project_param:
            return ""
        project_id = request.path_params.get(self.project_param, "")
        if not project_id:
            return ""
        resource_project = await self._resolve_project_name(db, project_id)
        if not resource_project:
            from syntara.authz.exceptions import ProjectNotFoundError  # noqa: PLC0415

            msg = f"Project {project_id} not found"
            raise ProjectNotFoundError(msg)
        return resource_project

    async def _resolve_resource_project(
        self, request: Request, db: AsyncSession
    ) -> tuple[str, str, str, dict[str, str]]:
        """Resolve resource_id, resource_name, resource_project, and resource_labels from the request context.

        Returns:
            Tuple of (resource_id, resource_name, resource_project, resource_labels).

        """
        if self.resource_id_param:
            resource_id = request.path_params.get(self.resource_id_param, "")
        else:
            resource_id = request.path_params.get("id", request.path_params.get("workflow_id", ""))

        resource_project = ""
        resource_labels: dict[str, str] = {}

        if self.project_param:
            resource_project = await self._resolve_project_from_path(request, db)
            if resource_project and self.resource_type == "project":
                # Project endpoints (e.g. PUT /projects/{project_id}) don't set
                # resource_id_param, so resource_id would be empty. Use project_id
                # from the path as the resource ID for scope matching.
                resource_id_from_project_path = request.path_params.get(self.project_param, "")
                resource_id = resource_id_from_project_path

        if not resource_project and self.resource_model and self.resource_id_param and resource_id:
            resource_project = await self._resolve_project_from_resource(db, resource_id)

        if self.resource_model and resource_id:
            resource_labels = await self._resolve_resource_labels(db, resource_id)

        if not resource_project and self.body_project_field:
            resource_project = await self._resolve_project_from_body(request, db)

        if not resource_project and self.form_project_field:
            resource_project = await self._resolve_project_from_form(request, db)

        resource_id_str = str(resource_id) if resource_id else ""
        resource_name = await self._resolve_resource_name(db, resource_id_str)

        return resource_id_str, resource_name, resource_project, resource_labels

    async def _resolve_project_from_body(self, request: Request, db: AsyncSession) -> str:
        """Extract and resolve project from the request body.

        Returns:
            The project name, or empty string if not found.

        """
        body = await request.json()
        if not isinstance(body, dict):
            raise RequestValidationError(
                [
                    {
                        "type": "value_error",
                        "loc": ("body",),
                        "msg": "Request body must be a JSON object",
                        "input": body,
                    }
                ]
            )
        body_project_id = body.get(self.body_project_field)
        if body_project_id:
            project_name = await self._resolve_project_name(db, body_project_id)
            if not project_name:
                from syntara.authz.exceptions import ProjectNotFoundError  # noqa: PLC0415

                msg = f"Project {body_project_id} not found"
                raise ProjectNotFoundError(msg)
            return project_name
        return ""

    async def _resolve_project_from_form(self, request: Request, db: AsyncSession) -> str:
        """Extract and resolve project from a multipart form field.

        Returns:
            The project name, or empty string if not found.

        """
        if not self.form_project_field:
            return ""
        form = await request.form()
        form_project_id = form.get(self.form_project_field)
        if form_project_id and isinstance(form_project_id, str):
            project_name = await self._resolve_project_name(db, form_project_id)
            if not project_name:
                from syntara.authz.exceptions import ProjectNotFoundError  # noqa: PLC0415

                msg = f"Project {form_project_id} not found"
                raise ProjectNotFoundError(msg)
            return project_name
        return ""

    async def __call__(
        self,
        request: Request,
        current_user: User = Depends(get_current_user),  # noqa: B008
        db: AsyncSession = Depends(get_db),  # noqa: B008
    ) -> None:
        """Check if the current user is authorized.

        Args:
            request: FastAPI request.
            current_user: The authenticated user (ensures auth runs before authz).
            db: Database session.

        Raises:
            AuthorizationDeniedError: If the user is not authorized.

        """
        if getattr(request.state, "is_cert_authenticated", False):
            return

        start = time.perf_counter()
        evaluator = get_authz_evaluator(request)
        resource_id, resource_name, resource_project, resource_labels = await self._resolve_resource_project(
            request, db
        )

        authz_request = AuthzRequest(
            user_id=current_user.id,
            action=self.action,
            resource_type=self.resource_type,
            resource_id=resource_id,
            resource_project=resource_project,
            resource_labels=resource_labels,
            user_labels=current_user.labels,
            user_metadata=current_user.authz_metadata,
        )

        authz_result: AuthzResult = await authorize(db, evaluator, authz_request)
        _record_authz_duration(start, self.resource_type, self.action)

        if not authz_result.allowed:
            from syntara.audit.dispatcher import AuditEventDispatcher  # noqa: PLC0415
            from syntara.authz.audit.authorization_denied import AuthorizationDeniedEvent  # noqa: PLC0415

            AuditEventDispatcher.dispatch(
                AuthorizationDeniedEvent(
                    user_id=current_user.id,
                    username=current_user.username,
                    resource_id=resource_id,
                    resource_type=self.resource_type,
                    resource_name=resource_name,
                    action=self.action,
                    denied_by=authz_result.denied_by,
                    principal_type=current_user.__dict__.get("__principal_type__"),
                )
            )
            logger.info(
                "Authorization denied",
                user_id=str(current_user.id),
                resource_type=self.resource_type,
                action=self.action,
                denied_by=authz_result.denied_by,
            )
            msg = f"Not authorized to perform {self.action} on {self.resource_type}"
            raise AuthorizationDeniedError(msg)


class ProjectScopeFilter:
    """FastAPI dependency that resolves which projects a user can access.

    Returns an AllowedProjectsResult that services can use to filter
    LIST queries to only include resources from authorized projects.

    Usage:
        @router.get("")
        async def list_credentials(
            allowed: AllowedProjectsResult = Depends(ProjectScopeFilter("credential", "read")),
        ):
            # Pass allowed to service for query filtering
            ...

    """

    def __init__(self, resource_type: str, action: str) -> None:
        """Initialize project scope filter.

        Args:
            resource_type: The resource type (e.g., "credential", "workflow").
            action: The action being performed (e.g., "read").

        """
        self.resource_type = resource_type
        self.action = action

    async def __call__(
        self,
        request: Request,
        current_user: User = Depends(get_current_user),  # noqa: B008
        db: AsyncSession = Depends(get_db),  # noqa: B008
    ) -> AllowedProjectsResult:
        """Resolve allowed projects for the current user.

        Args:
            request: FastAPI request.
            current_user: The authenticated user.
            db: Database session.

        Returns:
            AllowedProjectsResult with the set of accessible project IDs.

        """
        if getattr(request.state, "is_cert_authenticated", False):
            return AllowedProjectsResult(all_projects=True, project_ids=[])

        start = time.perf_counter()
        evaluator = get_authz_evaluator(request)

        result = await resolve_allowed_projects(
            db=db,
            evaluator=evaluator,
            user_id=current_user.id,
            resource_type=self.resource_type,
            action=self.action,
            user_labels=current_user.labels,
            user_metadata=current_user.authz_metadata,
        )
        _record_authz_duration(start, self.resource_type, self.action)
        return result


class VisibilityFilter:
    """FastAPI dependency that resolves what a user is allowed to see."""

    def __init__(self, resource_type: str, action: str) -> None:
        """Initialize visibility filter."""
        self.resource_type = resource_type
        self.action = action

    async def __call__(
        self,
        request: Request,
        current_user: User = Depends(get_current_user),  # noqa: B008
        db: AsyncSession = Depends(get_db),  # noqa: B008
    ) -> VisibilityResult:
        """Resolve visibility for the current user."""
        if getattr(request.state, "is_cert_authenticated", False):
            return VisibilityResult(unrestricted=True)

        start = time.perf_counter()
        evaluator = get_authz_evaluator(request)

        result = await resolve_visibility(
            db=db,
            evaluator=evaluator,
            user_id=current_user.id,
            resource_type=self.resource_type,
            action=self.action,
            user_labels=current_user.labels,
            user_metadata=current_user.authz_metadata,
        )
        _record_authz_duration(start, self.resource_type, self.action)
        return result
