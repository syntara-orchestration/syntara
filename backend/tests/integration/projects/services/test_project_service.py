"""Unit tests for ProjectService.

Tests cover:
- Project CRUD operations (create, get, list, update, delete)
- Auto-assignment of project-admin on create
- Cascading deletion of project-scoped resources
"""

from uuid import uuid4

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.engine import AllowedProjectsResult
from syntara.authz.exceptions import ProjectNotFoundError
from syntara.authz.models.assignments import RoleAssignment
from syntara.authz.models.policy import Policy
from syntara.authz.models.role import Role
from syntara.authz.seed import seed_authz_data
from syntara.core.models import User
from syntara.core.models.group import Group
from syntara.core.models.secret import EncryptedSecret, Secret
from syntara.credentials.models.credential import Credential
from syntara.credentials.models.credential_type import CredentialType
from syntara.projects.service import ProjectService
from syntara.workflows.models.execution import Execution
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from tests.helpers.workflow import create_minimal_workflow_definition


@pytest.fixture
async def seeded_db(test_db_session: AsyncSession) -> AsyncSession:
    """Seed authz data and return the session."""
    await seed_authz_data(test_db_session)
    return test_db_session


# ============================================================================
# Project CRUD
# ============================================================================


@pytest.mark.asyncio
async def test_create_project(seeded_db: AsyncSession, test_user: User) -> None:
    """Create a project and auto-assign creator as project-admin."""
    svc = ProjectService(seeded_db, test_user)
    project = await svc.create_project(
        name="test-project",
        description="A test project",
        labels={"env": "dev"},
    )
    assert project.name == "test-project"
    assert project.description == "A test project"
    assert project.labels == {"env": "dev"}
    assert project.deleted_at is None

    # Creator should be assigned project-admin
    assignments = (await seeded_db.exec(select(RoleAssignment).where(RoleAssignment.project_id == project.id))).all()
    assert len(assignments) == 1
    assert assignments[0].role_name == "project-admin"
    assert assignments[0].principal_id == test_user.id


@pytest.mark.asyncio
async def test_create_project_defaults(seeded_db: AsyncSession, test_user: User) -> None:
    """Create a project with only the required name."""
    svc = ProjectService(seeded_db, test_user)
    project = await svc.create_project(name="minimal-project")
    assert project.name == "minimal-project"
    assert project.description is None
    assert project.labels == {}


@pytest.mark.asyncio
async def test_get_project(seeded_db: AsyncSession, test_user: User) -> None:
    """Get a project by ID."""
    svc = ProjectService(seeded_db, test_user)
    created = await svc.create_project(name="get-project")
    fetched = await svc.get_project(created.id)
    assert fetched.id == created.id
    assert fetched.name == "get-project"


@pytest.mark.asyncio
async def test_get_project_not_found(seeded_db: AsyncSession, test_user: User) -> None:
    """Getting a non-existent project raises SafeValueError."""
    svc = ProjectService(seeded_db, test_user)
    with pytest.raises(ProjectNotFoundError, match="not found"):
        await svc.get_project(uuid4())


@pytest.mark.asyncio
async def test_get_deleted_project_not_found(seeded_db: AsyncSession, test_user: User) -> None:
    """Getting a soft-deleted project raises SafeValueError."""
    svc = ProjectService(seeded_db, test_user)
    project = await svc.create_project(name="deleted-project")
    await svc.delete_project(project.id)
    with pytest.raises(ProjectNotFoundError, match="not found"):
        await svc.get_project(project.id)


@pytest.mark.asyncio
async def test_list_projects_no_filter(seeded_db: AsyncSession, test_user: User) -> None:
    """List all non-deleted projects."""
    svc = ProjectService(seeded_db, test_user)
    await svc.create_project(name="list-p1")
    await svc.create_project(name="list-p2")
    projects = await svc.list_projects()
    names = [p.name for p in projects]
    assert "list-p1" in names
    assert "list-p2" in names


@pytest.mark.asyncio
async def test_list_projects_with_allowed_all(seeded_db: AsyncSession, test_user: User) -> None:
    """List with all_projects=True returns everything."""
    svc = ProjectService(seeded_db, test_user)
    await svc.create_project(name="all-p1")
    allowed = AllowedProjectsResult(all_projects=True, project_ids=[])
    projects = await svc.list_projects(allowed_projects=allowed)
    names = [p.name for p in projects]
    assert "all-p1" in names


@pytest.mark.asyncio
async def test_list_projects_with_allowed_specific(seeded_db: AsyncSession, test_user: User) -> None:
    """List with specific project IDs only returns those projects."""
    svc = ProjectService(seeded_db, test_user)
    p1 = await svc.create_project(name="allowed-p1")
    await svc.create_project(name="not-allowed-p2")
    allowed = AllowedProjectsResult(all_projects=False, project_ids=[p1.id])
    projects = await svc.list_projects(allowed_projects=allowed)
    names = [p.name for p in projects]
    assert "allowed-p1" in names
    assert "not-allowed-p2" not in names


@pytest.mark.asyncio
async def test_list_projects_with_allowed_empty(seeded_db: AsyncSession, test_user: User) -> None:
    """List with empty project IDs returns nothing."""
    svc = ProjectService(seeded_db, test_user)
    await svc.create_project(name="empty-filter-p1")
    allowed = AllowedProjectsResult(all_projects=False, project_ids=[])
    projects = await svc.list_projects(allowed_projects=allowed)
    assert projects == []


# ============================================================================
# Cursor Listing with include_total
# ============================================================================


@pytest.mark.asyncio
async def test_list_projects_cursor_include_total_no_filter(seeded_db: AsyncSession, test_user: User) -> None:
    """include_total returns correct count when no authorization filter is applied."""
    svc = ProjectService(seeded_db, test_user)
    for i in range(5):
        await svc.create_project(name=f"total-p{i}")

    result = await svc.list_projects_cursor(limit=3, include_total=True)
    # 5 created + 1 seeded default project + 1 seeded system project
    assert result.total == 7
    assert len(result.resources) == 3


@pytest.mark.asyncio
async def test_list_projects_cursor_include_total_with_allowed_specific(
    seeded_db: AsyncSession, test_user: User
) -> None:
    """include_total reflects only projects the user is authorized to see."""
    svc = ProjectService(seeded_db, test_user)
    p1 = await svc.create_project(name="visible-p1")
    p2 = await svc.create_project(name="visible-p2")
    await svc.create_project(name="hidden-p3")

    allowed = AllowedProjectsResult(all_projects=False, project_ids=[p1.id, p2.id])
    result = await svc.list_projects_cursor(limit=10, include_total=True, allowed_projects=allowed)
    assert result.total == 2
    names = [r.name for r in result.resources]
    assert "visible-p1" in names
    assert "visible-p2" in names
    assert "hidden-p3" not in names


@pytest.mark.asyncio
async def test_list_projects_cursor_include_total_with_allowed_empty(seeded_db: AsyncSession, test_user: User) -> None:
    """include_total returns 0 when user has no project access."""
    svc = ProjectService(seeded_db, test_user)
    await svc.create_project(name="no-access-p1")

    allowed = AllowedProjectsResult(all_projects=False, project_ids=[])
    result = await svc.list_projects_cursor(limit=10, include_total=True, allowed_projects=allowed)
    assert result.total == 0
    assert result.resources == []


@pytest.mark.asyncio
async def test_list_projects_cursor_include_total_with_all_projects(seeded_db: AsyncSession, test_user: User) -> None:
    """include_total returns full count when all_projects is True."""
    svc = ProjectService(seeded_db, test_user)
    for i in range(4):
        await svc.create_project(name=f"all-access-p{i}")

    allowed = AllowedProjectsResult(all_projects=True, project_ids=[])
    result = await svc.list_projects_cursor(limit=10, include_total=True, allowed_projects=allowed)
    # 4 created + 1 seeded default project + 1 seeded system project
    assert result.total == 6


@pytest.mark.asyncio
async def test_list_projects_cursor_without_include_total(seeded_db: AsyncSession, test_user: User) -> None:
    """Total is None when include_total is False."""
    svc = ProjectService(seeded_db, test_user)
    await svc.create_project(name="no-total-p1")

    result = await svc.list_projects_cursor(limit=10, include_total=False)
    assert result.total is None


# ============================================================================
# Project Updates
# ============================================================================


@pytest.mark.asyncio
async def test_update_project(seeded_db: AsyncSession, test_user: User) -> None:
    """Update project name, description, and labels."""
    svc = ProjectService(seeded_db, test_user)
    project = await svc.create_project(name="update-me", description="original")
    updated = await svc.update_project(
        project.id,
        name="renamed",
        description="updated",
        labels={"version": "2"},
    )
    assert updated.name == "renamed"
    assert updated.description == "updated"
    assert updated.labels == {"version": "2"}


@pytest.mark.asyncio
async def test_update_project_partial(seeded_db: AsyncSession, test_user: User) -> None:
    """Partial update only changes provided fields."""
    svc = ProjectService(seeded_db, test_user)
    project = await svc.create_project(name="partial-update", description="original")
    updated = await svc.update_project(project.id, description="only desc changed")
    assert updated.name == "partial-update"
    assert updated.description == "only desc changed"


@pytest.mark.asyncio
async def test_delete_project(seeded_db: AsyncSession, test_user: User) -> None:
    """Soft-delete a project."""
    svc = ProjectService(seeded_db, test_user)
    project = await svc.create_project(name="delete-me")
    await svc.delete_project(project.id)
    # Should not appear in list
    projects = await svc.list_projects()
    assert not any(p.name == "delete-me" for p in projects)


# ============================================================================
# Cascading Deletion
# ============================================================================


@pytest.mark.asyncio
async def test_delete_project_cascades_role_assignments(seeded_db: AsyncSession, test_user: User) -> None:
    """Deleting a project hard-deletes all user and group role assignments."""
    svc = ProjectService(seeded_db, test_user)
    project = await svc.create_project(name="cascade-assignments")

    other = User(
        id=uuid4(),
        username="cascade-u",
        email="cascade-u@test.com",
        first_name="CU",
        password_hash="$argon2id$test",  # noqa: S106
    )
    group = Group(id=uuid4(), name="cascade-grp", description="", labels={})
    seeded_db.add(other)
    seeded_db.add(group)
    await seeded_db.commit()

    seeded_db.add(
        RoleAssignment(
            principal_id=other.id,
            role_name="project-user",
            project_id=project.id,
        )
    )
    seeded_db.add(
        RoleAssignment(
            group_id=group.id,
            role_name="project-auditor",
            project_id=project.id,
        )
    )
    await seeded_db.commit()

    await svc.delete_project(project.id)

    assigns = (await seeded_db.exec(select(RoleAssignment).where(RoleAssignment.project_id == project.id))).all()
    assert assigns == []


@pytest.mark.asyncio
async def test_delete_project_cascades_custom_roles(seeded_db: AsyncSession, test_user: User) -> None:
    """Deleting a project hard-deletes all custom roles scoped to it."""
    svc = ProjectService(seeded_db, test_user)
    project = await svc.create_project(name="cascade-roles")

    role = Role(
        name="custom-proj-role",
        is_builtin=False,
        project_id=project.id,
        scope="project",
        policy_names=["workflow:read"],
        labels={},
    )
    seeded_db.add(role)
    await seeded_db.commit()

    await svc.delete_project(project.id)

    rows = (await seeded_db.exec(select(Role).where(Role.project_id == project.id))).all()
    assert rows == []


@pytest.mark.asyncio
async def test_delete_project_cascades_custom_policies(seeded_db: AsyncSession, test_user: User) -> None:
    """Deleting a project hard-deletes all custom policies scoped to it."""
    svc = ProjectService(seeded_db, test_user)
    project = await svc.create_project(name="cascade-policies")

    policy = Policy(
        name="custom-proj-policy",
        statements=[{"effect": "allow", "actions": ["read"], "scope": "project"}],
        is_builtin=False,
        project_id=project.id,
        scope="project",
        labels={},
    )
    seeded_db.add(policy)
    await seeded_db.commit()

    await svc.delete_project(project.id)

    rows = (await seeded_db.exec(select(Policy).where(Policy.project_id == project.id))).all()
    assert rows == []


@pytest.mark.asyncio
async def test_delete_project_soft_deletes_workflows(seeded_db: AsyncSession, test_user: User) -> None:
    """Deleting a project soft-deletes all workflows within it."""
    svc = ProjectService(seeded_db, test_user)
    user_id = test_user.id
    project = await svc.create_project(name="cascade-workflows")

    workflow = Workflow(
        name="proj-workflow",
        project_id=project.id,
        created_by=user_id,
        labels={},
    )
    seeded_db.add(workflow)
    await seeded_db.commit()
    wf_id = workflow.id

    await svc.delete_project(project.id)

    seeded_db.expire_all()
    wf = (await seeded_db.exec(select(Workflow).where(Workflow.id == wf_id))).first()
    assert wf is not None
    assert wf.deleted_at is not None
    assert wf.deleted_by == user_id


@pytest.mark.asyncio
async def test_delete_project_soft_deletes_executions(seeded_db: AsyncSession, test_user: User) -> None:
    """Deleting a project soft-deletes all executions within it."""
    svc = ProjectService(seeded_db, test_user)
    user_id = test_user.id
    project = await svc.create_project(name="cascade-executions")

    workflow = Workflow(
        name="exec-workflow",
        project_id=project.id,
        created_by=user_id,
        labels={},
    )
    seeded_db.add(workflow)
    await seeded_db.flush()

    wf_version = WorkflowVersion(
        workflow_id=workflow.id,
        version=1,
        schema_version="2.0.0",
        workflow_definition=create_minimal_workflow_definition(name="test-cascade"),
        created_by=user_id,
        labels={},
    )
    seeded_db.add(wf_version)
    await seeded_db.flush()

    execution = Execution(
        workflow_id=workflow.id,
        workflow_version_id=wf_version.id,
        project_id=project.id,
        temporal_workflow_id=f"temporal-{uuid4().hex[:8]}",
        status="pending",
        created_by=user_id,
        labels={},
    )
    seeded_db.add(execution)
    await seeded_db.commit()
    exec_id = execution.id

    await svc.delete_project(project.id)

    seeded_db.expire_all()
    ex = (await seeded_db.exec(select(Execution).where(Execution.id == exec_id))).first()
    assert ex is not None
    assert ex.deleted_at is not None
    assert ex.deleted_by == user_id


@pytest.mark.asyncio
async def test_delete_project_hard_deletes_credentials_and_cleans_secrets(
    seeded_db: AsyncSession, test_user: User
) -> None:
    """Deleting a project hard-deletes credentials and removes their secrets."""
    svc = ProjectService(seeded_db, test_user)
    user_id = test_user.id
    project = await svc.create_project(name="cascade-creds")

    cred_type = CredentialType(
        name=f"test-type-{uuid4().hex[:8]}",
        description="test",
        inputs={"fields": [], "required": []},
        injectors={"extra_vars": {}, "env": {}, "file": {}},
        managed=False,
    )
    seeded_db.add(cred_type)
    await seeded_db.flush()

    secret = Secret()
    seeded_db.add(secret)
    await seeded_db.flush()

    enc_secret = EncryptedSecret(
        secret_id=secret.id,
        encrypted_data={"token": "encrypted-data"},
    )
    seeded_db.add(enc_secret)
    await seeded_db.flush()

    credential = Credential(
        name="proj-cred",
        credential_type_id=cred_type.id,
        secret_id=secret.id,
        project_id=project.id,
        created_by=user_id,
        labels={},
    )
    seeded_db.add(credential)
    await seeded_db.commit()
    cred_id = credential.id
    secret_id = secret.id
    enc_id = enc_secret.id

    await svc.delete_project(project.id)

    seeded_db.expire_all()
    cred = (await seeded_db.exec(select(Credential).where(Credential.id == cred_id))).first()
    assert cred is None

    sec = (await seeded_db.exec(select(Secret).where(Secret.id == secret_id))).first()
    assert sec is None

    enc = (await seeded_db.exec(select(EncryptedSecret).where(EncryptedSecret.id == enc_id))).first()
    assert enc is None


@pytest.mark.asyncio
async def test_delete_project_hard_deletes_approval_requests(seeded_db: AsyncSession, test_user: User) -> None:
    """Deleting a project hard-deletes all approval requests within it."""
    from syntara.approvals.models.approval_request import ApprovalRequest

    svc = ProjectService(seeded_db, test_user)
    user_id = test_user.id
    project = await svc.create_project(name="cascade-approvals")

    workflow = Workflow(
        name="approval-workflow",
        project_id=project.id,
        created_by=user_id,
        labels={},
    )
    seeded_db.add(workflow)
    await seeded_db.flush()

    wf_version = WorkflowVersion(
        workflow_id=workflow.id,
        version=1,
        schema_version="2.0.0",
        workflow_definition=create_minimal_workflow_definition(name="test-cascade"),
        created_by=user_id,
        labels={},
    )
    seeded_db.add(wf_version)
    await seeded_db.flush()

    execution = Execution(
        workflow_id=workflow.id,
        workflow_version_id=wf_version.id,
        project_id=project.id,
        temporal_workflow_id=f"temporal-{uuid4().hex[:8]}",
        status="pending",
        created_by=user_id,
        labels={},
    )
    seeded_db.add(execution)
    await seeded_db.flush()

    approval = ApprovalRequest(
        name="test-approval",
        execution_id=execution.id,
        project_id=project.id,
        approval_node_id="step-1",
        next_step_approved={"id": "next", "name": "Next Step", "type": "llm"},
        labels={},
    )
    seeded_db.add(approval)
    await seeded_db.commit()
    approval_id = approval.id

    await svc.delete_project(project.id)

    seeded_db.expire_all()
    row = (await seeded_db.exec(select(ApprovalRequest).where(ApprovalRequest.id == approval_id))).first()
    assert row is None


@pytest.mark.asyncio
async def test_delete_project_does_not_affect_other_projects(seeded_db: AsyncSession, test_user: User) -> None:
    """Deleting one project leaves another project's resources intact."""
    svc = ProjectService(seeded_db, test_user)
    user_id = test_user.id
    p1 = await svc.create_project(name="cascade-target")
    p2 = await svc.create_project(name="cascade-survivor")

    role1 = Role(name="r1", is_builtin=False, project_id=p1.id, scope="project", policy_names=[], labels={})
    role2 = Role(name="r2", is_builtin=False, project_id=p2.id, scope="project", policy_names=[], labels={})
    wf1 = Workflow(name="wf1", project_id=p1.id, created_by=user_id, labels={})
    wf2 = Workflow(name="wf2", project_id=p2.id, created_by=user_id, labels={})
    seeded_db.add_all([role1, role2, wf1, wf2])
    await seeded_db.commit()
    p1_id = p1.id
    role2_id = role2.id
    wf2_id = wf2.id

    await svc.delete_project(p1_id)

    seeded_db.expire_all()
    # p1 resources should be gone/soft-deleted
    assert (await seeded_db.exec(select(Role).where(Role.project_id == p1_id))).all() == []
    wf1_row = (await seeded_db.exec(select(Workflow).where(Workflow.project_id == p1_id))).first()
    assert wf1_row is not None
    assert wf1_row.deleted_at is not None

    # p2 resources should be untouched
    r2 = (await seeded_db.exec(select(Role).where(Role.id == role2_id))).first()
    assert r2 is not None
    wf2_row = (await seeded_db.exec(select(Workflow).where(Workflow.id == wf2_id))).first()
    assert wf2_row is not None
    assert wf2_row.deleted_at is None


@pytest.mark.asyncio
async def test_delete_project_with_no_resources(seeded_db: AsyncSession, test_user: User) -> None:
    """Deleting a project with no child resources succeeds cleanly."""
    svc = ProjectService(seeded_db, test_user)
    project = await svc.create_project(name="empty-cascade")
    await svc.delete_project(project.id)
    with pytest.raises(ProjectNotFoundError):
        await svc.get_project(project.id)


# ============================================================================
# Builtin Project Protection
# ============================================================================


@pytest.mark.asyncio
async def test_update_builtin_project_raises(seeded_db: AsyncSession, test_user: User) -> None:
    """Updating a builtin project raises BuiltinProtectionError."""
    from syntara.authz.exceptions import BuiltinProtectionError
    from syntara.authz.models.project import Project

    result = await seeded_db.exec(select(Project).where(Project.is_builtin == True))  # noqa: E712
    builtin_project = result.first()
    assert builtin_project is not None, "seed_authz_data should create a built-in project"

    svc = ProjectService(seeded_db, test_user)
    with pytest.raises(BuiltinProtectionError, match="cannot be modified"):
        await svc.update_project(builtin_project.id, name="renamed")


@pytest.mark.asyncio
async def test_delete_builtin_project_raises(seeded_db: AsyncSession, test_user: User) -> None:
    """Deleting a builtin project raises BuiltinProtectionError."""
    from syntara.authz.exceptions import BuiltinProtectionError
    from syntara.authz.models.project import Project

    result = await seeded_db.exec(select(Project).where(Project.is_builtin == True))  # noqa: E712
    builtin_project = result.first()
    assert builtin_project is not None

    svc = ProjectService(seeded_db, test_user)
    with pytest.raises(BuiltinProtectionError, match="cannot be deleted"):
        await svc.delete_project(builtin_project.id)


@pytest.mark.asyncio
async def test_update_non_builtin_project_succeeds(seeded_db: AsyncSession, test_user: User) -> None:
    """Updating a non-builtin project succeeds normally."""
    svc = ProjectService(seeded_db, test_user)
    project = await svc.create_project(name="normal-project")
    updated = await svc.update_project(project.id, name="renamed-project")
    assert updated.name == "renamed-project"


@pytest.mark.asyncio
async def test_delete_non_builtin_project_succeeds(seeded_db: AsyncSession, test_user: User) -> None:
    """Deleting a non-builtin project succeeds normally."""
    svc = ProjectService(seeded_db, test_user)
    project = await svc.create_project(name="deletable-project")
    await svc.delete_project(project.id)
    with pytest.raises(ProjectNotFoundError):
        await svc.get_project(project.id)
