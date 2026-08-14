"""Project API endpoints.

CRUD for projects and project-scoped role assignment management.
Authorization is enforced via PermissionChecker dependency on each endpoint.
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Path, Query, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.approvals.models.approval_request import ApprovalListResponse
from syntara.approvals.models.query_params import ApprovalListParams
from syntara.approvals.services.approval_service import ApprovalService
from syntara.audit.decorators import audit
from syntara.audit.models.audit_event import EventCategory
from syntara.auth import get_current_user
from syntara.authz.dependencies import PermissionChecker, VisibilityFilter
from syntara.authz.engine import AllowedProjectsResult, VisibilityResult
from syntara.authz.exceptions import PolicyNotFoundError, RoleNotFoundError
from syntara.authz.role_assignment_router import (
    ProjectRoleAssignmentListParams,
    RoleAssignmentCreate,
    RoleAssignmentListResponse,
    RoleAssignmentRead,
    _parse_contains_filters,
    _redact_project_names,
)
from syntara.authz.schemas import (
    PolicyListParams,
    PolicyListResponse,
    PolicyRead,
    PolicyUpdate,
    RoleListParams,
    RoleListResponse,
    RoleRead,
    RoleUpdate,
)
from syntara.authz.services.policy_service import PolicyService
from syntara.authz.services.role_assignment_service import RoleAssignmentService
from syntara.authz.services.role_service import RoleService
from syntara.core.database.session import get_db
from syntara.core.models import User
from syntara.core.syntara_router import NO_PERMISSION, SyntaraRouter
from syntara.credentials.exceptions import CredentialNotFoundError
from syntara.credentials.models import (
    CredentialCreate,
    CredentialListParams,
    CredentialListResponse,
    CredentialRead,
    CredentialUpdate,
)
from syntara.credentials.models.credential import Credential, CredentialWorkflowRef, ProjectCredentialCreate
from syntara.credentials.router import get_credential_service
from syntara.credentials.services.credential_service import CredentialService
from syntara.projects.schemas import (
    ProjectCreate,
    ProjectListParams,
    ProjectListResponse,
    ProjectPolicyCreate,
    ProjectRead,
    ProjectRoleCreate,
    ProjectUpdate,
)
from syntara.projects.service import ProjectService
from syntara.workflows.models import WorkflowListParams
from syntara.workflows.models.workflow import WorkflowListResponse
from syntara.workflows.services import WorkflowService

router = SyntaraRouter(prefix="/projects", tags=["Projects"])

_perm_project_read = PermissionChecker("project", "read", project_param="project_id")
_perm_project_update = PermissionChecker("project", "update", project_param="project_id")
_perm_project_delete = PermissionChecker("project", "delete", project_param="project_id")
_perm_workflow_read = PermissionChecker("workflow", "read", project_param="project_id")
_perm_approval_read = PermissionChecker("approval", "read", project_param="project_id")
_perm_role_assignment_assign = PermissionChecker("role-assignment", "assign", project_param="project_id")
_perm_role_assignment_revoke = PermissionChecker("role-assignment", "revoke", project_param="project_id")
_perm_role_create = PermissionChecker("role", "create", project_param="project_id")
_perm_role_read = PermissionChecker("role", "read", project_param="project_id")
_perm_role_update = PermissionChecker("role", "update", project_param="project_id")
_perm_role_delete = PermissionChecker("role", "delete", project_param="project_id")
_perm_policy_create = PermissionChecker("policy", "create", project_param="project_id")
_perm_policy_read = PermissionChecker("policy", "read", project_param="project_id")
_perm_policy_update = PermissionChecker("policy", "update", project_param="project_id")
_perm_policy_delete = PermissionChecker("policy", "delete", project_param="project_id")
_perm_credential_create = PermissionChecker("credential", "create", project_param="project_id")
_perm_credential_read = PermissionChecker("credential", "read", project_param="project_id")
_perm_credential_update = PermissionChecker(
    "credential",
    "update",
    project_param="project_id",
    resource_model=Credential,
    resource_id_param="credential_id",
    owner_field="created_by",
)
_perm_credential_delete = PermissionChecker("credential", "delete", project_param="project_id")


def get_project_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProjectService:
    """Dependency provider for ProjectService."""
    return ProjectService(db, current_user)


def get_role_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RoleService:
    """Dependency provider for RoleService."""
    return RoleService(db, current_user)


def get_policy_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PolicyService:
    """Dependency provider for PolicyService."""
    return PolicyService(db, current_user)


def _get_role_assignment_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RoleAssignmentService:
    return RoleAssignmentService(db, current_user)


# ============================================================================
# Project CRUD
# ============================================================================


@router.post(
    "",
    summary="Create project",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(PermissionChecker("project", "create"))],
    operation_id="create_project",
    response_description="Project created",
)
@audit(EventCategory.USER_ACTION)
async def create_project(
    body: ProjectCreate,
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectRead:
    """Create a new project.

    The creator is automatically assigned the project-admin role.
    Requires: project:create permission.
    """
    project = await service.create_project(
        name=body.name,
        description=body.description,
        labels=body.labels,
    )
    return ProjectRead.model_validate(project)


@router.get(
    "",
    summary="List projects",
    operation_id="list_projects",
    response_description="Paginated list of accessible projects",
)
async def list_projects(
    request: Request,
    service: Annotated[ProjectService, Depends(get_project_service)],
    visibility: Annotated[VisibilityResult, Depends(VisibilityFilter("project", "read"))],
    params: Annotated[ProjectListParams, Query()],
) -> ProjectListResponse:
    """List projects the current user has read access to."""
    return await service.list_projects_cursor(
        limit=params.limit,
        cursor=params.cursor,
        sort=params.sort,
        query_params_items=request.query_params.items(),
        include_total=params.include_total,
        allowed_projects=visibility.to_allowed_projects(),
    )


@router.get(
    "/{project_id}",
    summary="Get project",
    dependencies=[Depends(_perm_project_read)],
    operation_id="get_project",
    response_description="Project details",
)
async def get_project(
    project_id: UUID,
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectRead:
    """Get a project by ID."""
    project = await service.get_project(project_id)
    return ProjectRead.model_validate(project)


async def _do_update_project(
    project_id: UUID,
    body: ProjectUpdate,
    service: ProjectService,
) -> ProjectRead:
    """Shared implementation for PATCH and PUT project updates."""
    project = await service.update_project(
        project_id=project_id,
        name=body.name,
        description=body.description,
        labels=body.labels,
    )
    return ProjectRead.model_validate(project)


@router.patch(
    "/{project_id}",
    summary="Update project",
    dependencies=[Depends(_perm_project_update)],
    operation_id="update_project",
    response_description="Updated project",
)
@audit(EventCategory.USER_ACTION)
async def update_project(
    project_id: UUID,
    body: ProjectUpdate,
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectRead:
    """Patch a project. Requires: project:update permission scoped to this project."""
    return await _do_update_project(project_id, body, service)


@router.put(
    "/{project_id}",
    summary="Replace project",
    dependencies=[Depends(_perm_project_update)],
    operation_id="replace_project",
    response_description="Updated project",
)
@audit(EventCategory.USER_ACTION)
async def replace_project(
    project_id: UUID,
    body: ProjectUpdate,
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectRead:
    """Replace a project. Requires: project:update permission scoped to this project."""
    return await _do_update_project(project_id, body, service)


@router.delete(
    "/{project_id}",
    summary="Delete project",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_perm_project_delete)],
    operation_id="delete_project",
    response_description="Project deleted",
)
@audit(EventCategory.USER_ACTION)
async def delete_project(
    project_id: UUID,
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> None:
    """Delete a project (soft-delete). Requires: project:delete permission scoped to this project."""
    await service.delete_project(project_id)


# ============================================================================
# Project Workflows
# ============================================================================


def get_workflow_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> WorkflowService:
    """Dependency provider for WorkflowService."""
    return WorkflowService(db, current_user)


@router.get(
    "/{project_id}/workflows",
    summary="List project workflows",
    dependencies=[Depends(_perm_workflow_read)],
    operation_id="list_project_workflows",
    response_description="Paginated list of workflows in the project",
)
async def list_project_workflows(
    project_id: UUID,
    request: Request,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
    params: Annotated[WorkflowListParams, Query()],
) -> WorkflowListResponse:
    """List workflows belonging to a specific project.

    Returns only workflows with project_id matching the given project.
    Requires: workflow:read permission scoped to this project.
    """
    allowed = AllowedProjectsResult(all_projects=False, project_ids=[project_id])
    result = await service.list_workflows_cursor(
        limit=params.limit,
        cursor=params.cursor,
        sort=params.sort,
        query_params_items=request.query_params.items(),
        include_total=params.include_total,
        allowed_projects=allowed,
    )
    await service.populate_published_version_numbers(result.resources)
    return result


# ============================================================================
# Project Approvals
# ============================================================================


def get_approval_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApprovalService:
    """Dependency provider for ApprovalService."""
    return ApprovalService(db, current_user)


@router.get(
    "/{project_id}/approvals",
    summary="List project approvals",
    dependencies=[Depends(_perm_approval_read)],
    operation_id="list_project_approvals",
    response_description="Paginated list of approvals in the project",
)
async def list_project_approvals(
    project_id: UUID,
    request: Request,
    service: Annotated[ApprovalService, Depends(get_approval_service)],
    params: Annotated[ApprovalListParams, Depends()],
) -> ApprovalListResponse:
    """List approval requests belonging to a specific project.

    Returns only approvals with project_id matching the given project.
    Requires: approval:read permission scoped to this project.
    """
    allowed = AllowedProjectsResult(all_projects=False, project_ids=[project_id])
    return await service.list(
        limit=params.limit,
        cursor=params.cursor,
        sort=params.sort,
        query_params_items=request.query_params.items(),
        include_total=params.include_total,
        allowed_projects=allowed,
    )


# ============================================================================
# Project Role Assignments (convenience endpoints calling RoleAssignmentService)
# ============================================================================


@router.post(
    "/{project_id}/role_assignments",
    summary="Create project role assignment",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_perm_role_assignment_assign)],
    operation_id="create_project_role_assignment",
    response_description="Role assignment created",
)
@audit(EventCategory.SECURITY_EVENT)
async def create_project_role_assignment(
    project_id: UUID,
    body: RoleAssignmentCreate,
    service: Annotated[RoleAssignmentService, Depends(_get_role_assignment_service)],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
) -> RoleAssignmentRead:
    """Assign a role to a user or group within a project."""
    await project_service.get_project(project_id)
    result = await service.assign(
        principal_id=body.principal_id,
        group_id=body.group_id,
        role_name=body.role_name,
        project_id=project_id,
    )
    return RoleAssignmentRead.model_validate(result)


@router.get(
    "/{project_id}/role_assignments",
    summary="List project role assignments",
    dependencies=[NO_PERMISSION],
    operation_id="list_project_role_assignments",
    response_description="List of role assignments",
)
async def list_project_role_assignments(
    project_id: UUID,
    request: Request,
    params: Annotated[ProjectRoleAssignmentListParams, Depends()],
    service: Annotated[RoleAssignmentService, Depends(_get_role_assignment_service)],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
    visibility: Annotated[VisibilityResult, Depends(VisibilityFilter("role-assignment", "read"))],
) -> RoleAssignmentListResponse:
    """List role assignments for a project with policy-driven visibility.

    Users with ``role-assignment:read:any`` see all assignments in the project.
    Users with ``role-assignment:read:project`` for this project see all.
    Users with ``role-assignment:read:self`` see only their own (direct and via groups).
    """
    await project_service.get_project(project_id)

    can_see_all = visibility.unrestricted or project_id in visibility.allowed_project_ids
    restrict_user_id = None if can_see_all else visibility.self_user_id
    restrict_group_ids = (
        None if can_see_all else (list(visibility.self_group_ids) if visibility.has_self_scope else None)
    )

    contains = _parse_contains_filters(request)
    result = await service.list(
        limit=params.limit,
        cursor=params.cursor,
        sort=params.sort,
        principal_id=params.principal_id,
        group_id=params.group_id,
        principal_name=params.principal_name,
        principal_name_contains=contains.get("principal_name_contains"),
        role_name=params.role_name,
        role_name_contains=contains.get("role_name_contains"),
        project_id=project_id,
        include_total=params.include_total,
        restrict_user_id=restrict_user_id,
        restrict_group_ids=restrict_group_ids,
    )

    _redact_project_names(result["resources"], visibility.readable_project_ids)

    return RoleAssignmentListResponse(
        resources=[RoleAssignmentRead.model_validate(r) for r in result["resources"]],
        next=result["next"],
        prev=result["prev"],
        total=result["total"],
    )


@router.delete(
    "/{project_id}/role_assignments/{assignment_id}",
    summary="Delete project role assignment",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_perm_role_assignment_revoke)],
    operation_id="delete_project_role_assignment",
    response_description="Assignment removed",
)
@audit(EventCategory.SECURITY_EVENT)
async def delete_project_role_assignment(
    project_id: UUID,
    assignment_id: UUID,
    service: Annotated[RoleAssignmentService, Depends(_get_role_assignment_service)],
) -> None:
    """Remove a role assignment from a project."""
    await service.revoke(assignment_id, project_id=project_id)


# ============================================================================
# Project-scoped Roles (CRUD)
# ============================================================================


@router.post(
    "/{project_id}/roles",
    summary="Create project role",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_perm_role_create)],
    operation_id="create_project_role",
)
@audit(EventCategory.SECURITY_EVENT)
async def create_project_role(
    project_id: UUID,
    body: ProjectRoleCreate,
    service: Annotated[RoleService, Depends(get_role_service)],
) -> RoleRead:
    """Create a role scoped to this project. Requires: role:create permission."""
    role = await service.create_role(
        name=body.name,
        description=body.description,
        policies=body.policies,
        labels=body.labels,
        project_id=project_id,
    )
    return await service.to_role_read(role)


@router.get(
    "/{project_id}/roles",
    summary="List project roles",
    dependencies=[Depends(_perm_role_read)],
    operation_id="list_project_roles",
)
async def list_project_roles(
    project_id: Annotated[UUID, Path(description="Project UUID")],
    request: Request,
    params: Annotated[RoleListParams, Depends()],
    service: Annotated[RoleService, Depends(get_role_service)],
) -> RoleListResponse:
    """List roles visible within this project.

    Includes project-owned roles and global roles with scope "project".
    """
    return await service.list_project_roles(
        project_id=project_id,
        limit=params.limit,
        cursor=params.cursor,
        sort=params.sort,
        query_params_items=request.query_params.items(),
        include_total=params.include_total,
    )


@router.get(
    "/{project_id}/roles/{role_id}",
    summary="Get project role",
    dependencies=[Depends(_perm_role_read)],
    operation_id="get_project_role",
)
async def get_project_role(
    project_id: UUID,
    role_id: UUID,
    service: Annotated[RoleService, Depends(get_role_service)],
) -> RoleRead:
    """Get a single role, verifying it belongs to this project."""
    role = await service.get_role(role_id)
    if role.project_id != project_id:
        msg = f"Role {role_id} not found in project {project_id}"
        raise RoleNotFoundError(msg)
    return await service.to_role_read(role)


async def _do_update_project_role(
    project_id: UUID,
    role_id: UUID,
    body: RoleUpdate,
    service: RoleService,
) -> RoleRead:
    """Shared implementation for PATCH and PUT project role updates."""
    role = await service.get_role(role_id)
    if role.project_id != project_id:
        msg = f"Role {role_id} not found in project {project_id}"
        raise RoleNotFoundError(msg)
    role = await service.update_role(
        role_id=role_id,
        name=body.name,
        description=body.description,
        policies=body.policies,
        labels=body.labels,
    )
    return await service.to_role_read(role)


@router.patch(
    "/{project_id}/roles/{role_id}",
    summary="Update project role",
    dependencies=[Depends(_perm_role_update)],
    operation_id="update_project_role",
)
@audit(EventCategory.SECURITY_EVENT)
async def update_project_role(
    project_id: UUID,
    role_id: UUID,
    body: RoleUpdate,
    service: Annotated[RoleService, Depends(get_role_service)],
) -> RoleRead:
    """Patch a project role. Builtin roles cannot be modified."""
    return await _do_update_project_role(project_id, role_id, body, service)


@router.put(
    "/{project_id}/roles/{role_id}",
    summary="Replace project role",
    dependencies=[Depends(_perm_role_update)],
    operation_id="replace_project_role",
)
@audit(EventCategory.SECURITY_EVENT)
async def replace_project_role(
    project_id: UUID,
    role_id: UUID,
    body: RoleUpdate,
    service: Annotated[RoleService, Depends(get_role_service)],
) -> RoleRead:
    """Replace a project role. Builtin roles cannot be modified."""
    return await _do_update_project_role(project_id, role_id, body, service)


@router.delete(
    "/{project_id}/roles/{role_id}",
    summary="Delete project role",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_perm_role_delete)],
    operation_id="delete_project_role",
)
@audit(EventCategory.SECURITY_EVENT)
async def delete_project_role(
    project_id: UUID,
    role_id: UUID,
    service: Annotated[RoleService, Depends(get_role_service)],
) -> None:
    """Delete a project role. Builtin roles cannot be deleted."""
    role = await service.get_role(role_id)
    if role.project_id != project_id:
        msg = f"Role {role_id} not found in project {project_id}"
        raise RoleNotFoundError(msg)
    await service.delete_role(role_id)


# ============================================================================
# Project-scoped Policies (CRUD)
# ============================================================================


def _is_global_project_scoped(policy_read: PolicyRead) -> bool:
    """Check if a policy is a global policy with project scope in its statements."""
    if policy_read.project_id is not None:
        return False
    return any(stmt.get("scope") == "project" for stmt in policy_read.statements)


@router.post(
    "/{project_id}/policies",
    summary="Create project policy",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_perm_policy_create)],
    operation_id="create_project_policy",
)
@audit(EventCategory.SECURITY_EVENT)
async def create_project_policy(
    project_id: UUID,
    body: ProjectPolicyCreate,
    service: Annotated[PolicyService, Depends(get_policy_service)],
) -> PolicyRead:
    """Create a policy scoped to this project. Requires: policy:create permission."""
    policy = await service.create_policy(
        name=body.name,
        description=body.description,
        statements=[s.model_dump(exclude_none=True) for s in body.statements],
        labels=body.labels,
        project_id=project_id,
    )
    return PolicyRead.model_validate(policy)


@router.get(
    "/{project_id}/policies",
    summary="List project policies",
    dependencies=[Depends(_perm_policy_read)],
    operation_id="list_project_policies",
)
async def list_project_policies(
    project_id: Annotated[UUID, Path(description="Project UUID")],
    request: Request,
    params: Annotated[PolicyListParams, Depends()],
    service: Annotated[PolicyService, Depends(get_policy_service)],
) -> PolicyListResponse:
    """List policies visible within this project.

    Includes project-owned policies and global policies with scope "project".
    """
    return await service.list_project_policies(
        project_id=project_id,
        limit=params.limit,
        cursor=params.cursor,
        sort=params.sort,
        query_params_items=request.query_params.items(),
        include_total=params.include_total,
    )


@router.get(
    "/{project_id}/policies/{policy_id}",
    summary="Get project policy",
    dependencies=[Depends(_perm_policy_read)],
    operation_id="get_project_policy",
)
async def get_project_policy(
    project_id: UUID,
    policy_id: UUID,
    service: Annotated[PolicyService, Depends(get_policy_service)],
) -> PolicyRead:
    """Get a single policy, if it belongs to this project or is a global project-scoped policy."""
    policy = await service.get_policy(policy_id)
    policy_read = PolicyRead.model_validate(policy)
    if policy.project_id == project_id or _is_global_project_scoped(policy_read):
        return policy_read
    msg = f"Policy {policy_id} not found in project {project_id}"
    raise PolicyNotFoundError(msg)


async def _do_update_project_policy(
    project_id: UUID,
    policy_id: UUID,
    body: PolicyUpdate,
    service: PolicyService,
) -> PolicyRead:
    """Shared implementation for PATCH and PUT project policy updates."""
    policy = await service.get_policy(policy_id)
    if policy.project_id != project_id:
        msg = f"Policy {policy_id} not found in project {project_id}"
        raise PolicyNotFoundError(msg)
    statements = None
    if body.statements is not None:
        statements = [s.model_dump(exclude_none=True) for s in body.statements]
    policy = await service.update_policy(
        policy_id=policy_id,
        name=body.name,
        description=body.description,
        statements=statements,
        labels=body.labels,
    )
    return PolicyRead.model_validate(policy)


@router.patch(
    "/{project_id}/policies/{policy_id}",
    summary="Update project policy",
    dependencies=[Depends(_perm_policy_update)],
    operation_id="update_project_policy",
)
@audit(EventCategory.SECURITY_EVENT)
async def update_project_policy(
    project_id: UUID,
    policy_id: UUID,
    body: PolicyUpdate,
    service: Annotated[PolicyService, Depends(get_policy_service)],
) -> PolicyRead:
    """Patch a project policy. Only project-owned policies can be modified."""
    return await _do_update_project_policy(project_id, policy_id, body, service)


@router.put(
    "/{project_id}/policies/{policy_id}",
    summary="Replace project policy",
    dependencies=[Depends(_perm_policy_update)],
    operation_id="replace_project_policy",
)
@audit(EventCategory.SECURITY_EVENT)
async def replace_project_policy(
    project_id: UUID,
    policy_id: UUID,
    body: PolicyUpdate,
    service: Annotated[PolicyService, Depends(get_policy_service)],
) -> PolicyRead:
    """Replace a project policy. Only project-owned policies can be modified."""
    return await _do_update_project_policy(project_id, policy_id, body, service)


@router.delete(
    "/{project_id}/policies/{policy_id}",
    summary="Delete project policy",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_perm_policy_delete)],
    operation_id="delete_project_policy",
)
@audit(EventCategory.SECURITY_EVENT)
async def delete_project_policy(
    project_id: UUID,
    policy_id: UUID,
    service: Annotated[PolicyService, Depends(get_policy_service)],
) -> None:
    """Delete a project policy. Only project-owned policies can be deleted."""
    policy = await service.get_policy(policy_id)
    if policy.project_id != project_id:
        msg = f"Policy {policy_id} not found in project {project_id}"
        raise PolicyNotFoundError(msg)
    await service.delete_policy(policy_id)


# ============================================================================
# Project-scoped Credentials (CRUD)
# ============================================================================


@router.post(
    "/{project_id}/credentials",
    summary="Create project credential",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_perm_credential_create)],
    operation_id="create_project_credential",
)
@audit(EventCategory.USER_ACTION, event_action="credential_create")
async def create_project_credential(
    project_id: UUID,
    data: ProjectCredentialCreate,
    service: Annotated[CredentialService, Depends(get_credential_service)],
) -> CredentialRead:
    """Create a new credential in this project. Requires: credential:create permission."""
    create_data = CredentialCreate(
        name=data.name,
        description=data.description,
        credential_type_id=data.credential_type_id,
        inputs=data.inputs,
        labels=data.labels,
        project_id=project_id,
    )
    return await service.create_credential(create_data)


@router.get(
    "/{project_id}/credentials",
    summary="List project credentials",
    dependencies=[Depends(_perm_credential_read)],
    operation_id="list_project_credentials",
    response_description="Paginated list of credentials in the project",
)
async def list_project_credentials(
    project_id: UUID,
    request: Request,
    service: Annotated[CredentialService, Depends(get_credential_service)],
    params: Annotated[CredentialListParams, Query()],
) -> CredentialListResponse:
    """List credentials belonging to this project. Requires: credential:read permission.

    The ``for_action`` parameter is accepted for API consistency but not enforced here.
    Use ``GET /credentials?for_action=use`` for use-permission-filtered listing.
    """
    allowed = AllowedProjectsResult(all_projects=False, project_ids=[project_id])
    # Strip for_action — not a DB-filterable field (not implemented on this endpoint)
    filtered_query_params = [(k, v) for k, v in request.query_params.items() if k != "for_action"]
    return await service.list_credentials(
        limit=params.limit,
        cursor=params.cursor,
        sort=params.sort,
        query_params_items=filtered_query_params,
        include_total=params.include_total,
        allowed_projects=allowed,
    )


@router.get(
    "/{project_id}/credentials/{credential_id}",
    summary="Get project credential",
    dependencies=[Depends(_perm_credential_read)],
    operation_id="get_project_credential",
)
async def get_project_credential(
    project_id: UUID,
    credential_id: UUID,
    service: Annotated[CredentialService, Depends(get_credential_service)],
) -> CredentialRead:
    """Get a credential in this project. Secret fields masked as $encrypted$."""
    raw = await service.get_credential_raw(credential_id)
    if raw.project_id != project_id:
        msg = f"Credential {credential_id} not found in project {project_id}"
        raise CredentialNotFoundError(msg)
    return await service.get_credential(credential_id)


@router.patch(
    "/{project_id}/credentials/{credential_id}",
    summary="Update project credential",
    dependencies=[Depends(_perm_credential_update)],
    operation_id="update_project_credential",
)
@audit(EventCategory.USER_ACTION, event_action="credential_update", capture_args={"credential_id"})
async def update_project_credential(
    project_id: UUID,
    credential_id: UUID,
    data: CredentialUpdate,
    service: Annotated[CredentialService, Depends(get_credential_service)],
) -> CredentialRead:
    """Update a credential in this project. Requires: credential:update permission."""
    raw = await service.get_credential_raw(credential_id)
    if raw.project_id != project_id:
        msg = f"Credential {credential_id} not found in project {project_id}"
        raise CredentialNotFoundError(msg)
    return await service.update_credential(credential_id, data)


@router.delete(
    "/{project_id}/credentials/{credential_id}",
    summary="Delete project credential",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_perm_credential_delete)],
    operation_id="delete_project_credential",
)
@audit(EventCategory.USER_ACTION, event_action="credential_delete", capture_args={"credential_id"})
async def delete_project_credential(
    project_id: UUID,
    credential_id: UUID,
    service: Annotated[CredentialService, Depends(get_credential_service)],
) -> None:
    """Delete a credential in this project. Requires: credential:delete permission."""
    raw = await service.get_credential_raw(credential_id)
    if raw.project_id != project_id:
        msg = f"Credential {credential_id} not found in project {project_id}"
        raise CredentialNotFoundError(msg)
    await service.delete_credential(credential_id)


@router.get(
    "/{project_id}/credentials/{credential_id}/workflows",
    summary="Get project credential workflows",
    dependencies=[Depends(_perm_credential_read)],
    operation_id="get_project_credential_workflows",
)
async def get_project_credential_workflows(
    project_id: UUID,
    credential_id: UUID,
    service: Annotated[CredentialService, Depends(get_credential_service)],
) -> list[CredentialWorkflowRef]:
    """Get workflows that reference this credential. Requires: credential:read permission."""
    raw = await service.get_credential_raw(credential_id)
    if raw.project_id != project_id:
        msg = f"Credential {credential_id} not found in project {project_id}"
        raise CredentialNotFoundError(msg)
    return await service.get_credential_workflows(credential_id)
