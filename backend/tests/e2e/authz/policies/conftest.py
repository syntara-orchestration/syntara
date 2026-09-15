"""Shared test-case definitions for parametrized policy coverage tests.

Each ``PolicyTestCase`` describes one built-in policy: the policy name,
prerequisite policies needed for setup, a callable that performs the
action under test, and an optional setup callable that creates the
target resource beforehand.

Setup helpers create resources directly via the admin API. Cleanup is
handled by the test's ``project_factory`` fixture — deleting the project
cascades to all resources created inside it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from orchestrator_test_sdk.e2e import (
    generate_test_password,
    unique_name,
)
from orchestrator_test_sdk.e2e.constants import MINIMAL_WORKFLOW_DEFINITION
from orchestrator_test_sdk.factories import get_bearer_token_type_id
from syntara_api_client.models.credential_create import CredentialCreate
from syntara_api_client.models.credential_create_inputs import CredentialCreateInputs
from syntara_api_client.models.credential_update import CredentialUpdate
from syntara_api_client.models.execution_create import ExecutionCreate
from syntara_api_client.models.policy_create import PolicyCreate
from syntara_api_client.models.policy_statement_schema import PolicyStatementSchema
from syntara_api_client.models.project_create import ProjectCreate
from syntara_api_client.models.project_role_create import ProjectRoleCreate
from syntara_api_client.models.project_update import ProjectUpdate
from syntara_api_client.models.role_assignment_create import RoleAssignmentCreate
from syntara_api_client.models.upload_files_body import UploadFilesBody
from syntara_api_client.models.workflow_create import WorkflowCreate
from syntara_api_client.models.workflow_update import WorkflowUpdate

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from syntara_api_client.api import SyntaraApiRegistry
    from syntara_api_client.types import Response


@dataclass
class PolicyTestCase:
    """Describes how to test a single built-in policy."""

    policy: str
    prereqs: list[str] = field(default_factory=list)
    action: Callable[..., Response[Any]] | None = None
    setup: Callable[..., None] | None = None
    description: str = ""
    skip_denied: bool = False

    def __repr__(self) -> str:  # noqa: D105
        return self.policy


# ---------------------------------------------------------------------------
# Action functions — each takes (api, project_id, ctx) and returns a Response
# ctx is a dict that setup() may populate with resource IDs
# ---------------------------------------------------------------------------


def _wf_create(api: SyntaraApiRegistry, pid: UUID, ctx: dict[str, Any]) -> Response[Any]:
    return api.workflows.create(
        body=WorkflowCreate(
            name=unique_name("pol-wf"),
            workflow_definition=MINIMAL_WORKFLOW_DEFINITION,
            project_id=pid,
        )
    )


def _wf_list(api: SyntaraApiRegistry, pid: UUID, ctx: dict[str, Any]) -> Response[Any]:
    return api.projects.list_workflows(project_id=pid)


def _wf_update(api: SyntaraApiRegistry, pid: UUID, ctx: dict[str, Any]) -> Response[Any]:
    return api.workflows.update(workflow_id=ctx["workflow_id"], body=WorkflowUpdate(name=unique_name("upd")))


def _wf_delete(api: SyntaraApiRegistry, pid: UUID, ctx: dict[str, Any]) -> Response[Any]:
    return api.workflows.delete(workflow_id=ctx["workflow_id"])


def _cred_create(api: SyntaraApiRegistry, pid: UUID, ctx: dict[str, Any]) -> Response[Any]:
    return api.credentials.create(
        body=CredentialCreate(
            name=unique_name("pol-cred"),
            credential_type_id=ctx["cred_type_id"],
            project_id=pid,
            inputs=CredentialCreateInputs.from_dict({"token": unique_name("t")}),
        )
    )


def _cred_list(api: SyntaraApiRegistry, pid: UUID, ctx: dict[str, Any]) -> Response[Any]:
    return api.credentials.list()


def _cred_update(api: SyntaraApiRegistry, pid: UUID, ctx: dict[str, Any]) -> Response[Any]:
    return api.credentials.update(credential_id=ctx["cred_id"], body=CredentialUpdate(description="updated"))


def _cred_delete(api: SyntaraApiRegistry, pid: UUID, ctx: dict[str, Any]) -> Response[Any]:
    return api.credentials.delete(credential_id=ctx["cred_id"])


def _exec_run(api: SyntaraApiRegistry, pid: UUID, ctx: dict[str, Any]) -> Response[Any]:
    return api.executions.create(body=ExecutionCreate(workflow_id=ctx["workflow_id"], trigger_node_id="trigger"))


def _exec_list(api: SyntaraApiRegistry, pid: UUID, ctx: dict[str, Any]) -> Response[Any]:
    return api.executions.list()


def _approval_list(api: SyntaraApiRegistry, pid: UUID, ctx: dict[str, Any]) -> Response[Any]:
    return api.approvals.list()


def _project_read(api: SyntaraApiRegistry, pid: UUID, ctx: dict[str, Any]) -> Response[Any]:
    return api.projects.get(project_id=pid)


def _project_update(api: SyntaraApiRegistry, pid: UUID, ctx: dict[str, Any]) -> Response[Any]:
    return api.projects.update(project_id=pid, body=ProjectUpdate(description=unique_name("upd")))


def _project_delete(api: SyntaraApiRegistry, pid: UUID, ctx: dict[str, Any]) -> Response[Any]:
    return api.projects.delete(project_id=pid)


def _role_create_proj(api: SyntaraApiRegistry, pid: UUID, ctx: dict[str, Any]) -> Response[Any]:
    return api.projects.create_role(
        project_id=pid,
        body=ProjectRoleCreate(name=unique_name("pol-role"), policies=["workflow:read:project"]),
    )


def _role_list_proj(api: SyntaraApiRegistry, pid: UUID, ctx: dict[str, Any]) -> Response[Any]:
    return api.roles.list(project_id=pid)


def _role_assignment_assign_proj(api: SyntaraApiRegistry, pid: UUID, ctx: dict[str, Any]) -> Response[Any]:
    return api.projects.create_role_assignment(
        project_id=pid,
        body=RoleAssignmentCreate(
            principal_id=ctx["target_user_id"],
            role_name="project-user",
        ),
    )


def _role_assignment_list_proj(api: SyntaraApiRegistry, pid: UUID, ctx: dict[str, Any]) -> Response[Any]:
    return api.projects.list_role_assignments(project_id=pid)


def _policy_create_proj(api: SyntaraApiRegistry, pid: UUID, ctx: dict[str, Any]) -> Response[Any]:
    return api.projects.create_policy(
        project_id=pid,
        body=PolicyCreate(
            name=unique_name("pol-policy"),
            statements=[
                PolicyStatementSchema(
                    effect="allow",
                    actions=["workflow:read"],
                    scope="project",
                )
            ],
        ),
    )


def _policy_list_proj(api: SyntaraApiRegistry, pid: UUID, ctx: dict[str, Any]) -> Response[Any]:
    return api.policies.list(project_id=pid)


# ---------------------------------------------------------------------------
# Setup helpers — create target resources via admin API before the test action.
# Cleanup is handled by project cascade deletion.
# ---------------------------------------------------------------------------


def _setup_workflow(admin_api: SyntaraApiRegistry, pid: UUID, ctx: dict[str, Any]) -> None:
    name = unique_name("pol-wf")
    resp = admin_api.workflows.create(
        body=WorkflowCreate(
            name=name,
            workflow_definition=MINIMAL_WORKFLOW_DEFINITION,
            project_id=pid,
        ),
    )
    wf = resp.assert_and_get()
    ctx["workflow_id"] = wf.id


def _setup_credential(admin_api: SyntaraApiRegistry, pid: UUID, ctx: dict[str, Any]) -> None:
    ctx["cred_type_id"] = get_bearer_token_type_id(admin_api)
    name = unique_name("pol-cred")
    resp = admin_api.credentials.create(
        body=CredentialCreate(
            name=name,
            credential_type_id=ctx["cred_type_id"],
            project_id=pid,
            inputs=CredentialCreateInputs.from_dict({"token": unique_name("t")}),
        ),
    )
    cred = resp.assert_and_get()
    ctx["cred_id"] = cred.id


def _setup_cred_type(admin_api: SyntaraApiRegistry, pid: UUID, ctx: dict[str, Any]) -> None:
    ctx["cred_type_id"] = get_bearer_token_type_id(admin_api)


def _setup_target_user(admin_api: SyntaraApiRegistry, pid: UUID, ctx: dict[str, Any]) -> None:
    from syntara_api_client.models.user_create import UserCreate as _UserCreate

    name = unique_name("pol-target")
    resp = admin_api.users.create(
        body=_UserCreate(
            username=name,
            email=f"{name}@example.com",
            first_name="Policy Test Target",
            password=generate_test_password(),
        ),
    )
    user = resp.assert_and_get()
    ctx["target_user_id"] = user.id


def _file_upload(api: SyntaraApiRegistry, pid: UUID, ctx: dict[str, Any]) -> Response[Any]:
    from io import BytesIO

    from syntara_api_client.types import File

    body = UploadFilesBody(
        files=[File(payload=BytesIO(b"test content"), file_name="policy-test.txt", mime_type="text/plain")],
        project_id=pid,
    )
    return api.files.upload(body=body)


def _file_download(api: SyntaraApiRegistry, pid: UUID, ctx: dict[str, Any]) -> Response[Any]:
    file_id = ctx["file_id"]
    return api.files.download(file_id=file_id)


def _setup_file(admin_api: SyntaraApiRegistry, pid: UUID, ctx: dict[str, Any]) -> None:
    from io import BytesIO

    from syntara_api_client.types import File

    body = UploadFilesBody(
        files=[File(payload=BytesIO(b"setup content"), file_name="setup-test.txt", mime_type="text/plain")],
        project_id=pid,
    )
    resp = admin_api.files.upload(body=body)
    data = resp.assert_and_get()
    ctx["file_id"] = data.file_ids[0]


# ---------------------------------------------------------------------------
# Project-scoped policy test cases
# ---------------------------------------------------------------------------

PROJECT_SCOPED_CASES: list[PolicyTestCase] = [
    # -- workflow --
    PolicyTestCase("workflow:create:project", ["project:read:project"], _wf_create),
    PolicyTestCase("workflow:read:project", ["project:read:project"], _wf_list, _setup_workflow),
    PolicyTestCase(
        "workflow:update:project", ["project:read:project", "workflow:read:project"], _wf_update, _setup_workflow
    ),
    PolicyTestCase(
        "workflow:delete:project", ["project:read:project", "workflow:read:project"], _wf_delete, _setup_workflow
    ),
    # -- credential --
    PolicyTestCase("credential:create:project", ["project:read:project"], _cred_create, _setup_cred_type),
    PolicyTestCase("credential:read:project", ["project:read:project"], _cred_list, _setup_credential),
    PolicyTestCase(
        "credential:update:project",
        ["project:read:project", "credential:read:project"],
        _cred_update,
        _setup_credential,
    ),
    PolicyTestCase(
        "credential:delete:project",
        ["project:read:project", "credential:read:project"],
        _cred_delete,
        _setup_credential,
    ),
    # -- execution --
    PolicyTestCase(
        "execution:run:project", ["project:read:project", "workflow:read:project"], _exec_run, _setup_workflow
    ),
    PolicyTestCase("execution:read:project", ["project:read:project"], _exec_list),
    # -- approval --
    PolicyTestCase("approval:read:project", ["project:read:project"], _approval_list),
    PolicyTestCase("approval:decide:project", ["project:read:project", "approval:read:project"], _approval_list),
    PolicyTestCase("approval:delete:project", ["project:read:project", "approval:read:project"], _approval_list),
    # -- project --
    PolicyTestCase("project:read:project", [], _project_read),
    PolicyTestCase("project:update:project", ["project:read:project"], _project_update),
    PolicyTestCase("project:delete:project", ["project:read:project"], _project_delete),
    # -- role-assignment --
    PolicyTestCase(
        "role-assignment:assign:project", ["project:read:project"], _role_assignment_assign_proj, _setup_target_user
    ),
    PolicyTestCase(
        "role-assignment:read:project", ["project:read:project"], _role_assignment_list_proj, skip_denied=True
    ),
    PolicyTestCase(
        "role-assignment:revoke:project",
        ["project:read:project", "role-assignment:read:project"],
        _role_assignment_list_proj,
        skip_denied=True,
    ),
    # -- role --
    PolicyTestCase("role:create:project", ["project:read:project"], _role_create_proj),
    PolicyTestCase("role:read:project", ["project:read:project"], _role_list_proj, skip_denied=True),
    PolicyTestCase(
        "role:update:project", ["project:read:project", "role:read:project"], _role_list_proj, skip_denied=True
    ),
    PolicyTestCase(
        "role:delete:project", ["project:read:project", "role:read:project"], _role_list_proj, skip_denied=True
    ),
    # -- policy --
    PolicyTestCase("policy:create:project", ["project:read:project"], _policy_create_proj),
    PolicyTestCase("policy:read:project", ["project:read:project"], _policy_list_proj, skip_denied=True),
    PolicyTestCase(
        "policy:update:project", ["project:read:project", "policy:read:project"], _policy_list_proj, skip_denied=True
    ),
    PolicyTestCase(
        "policy:delete:project", ["project:read:project", "policy:read:project"], _policy_list_proj, skip_denied=True
    ),
    # -- files: disabled until E2E cluster has S3 () --
]

# ---------------------------------------------------------------------------
# System-scoped (any) policy test cases — representative subset
# ---------------------------------------------------------------------------

SYSTEM_SCOPED_REPRESENTATIVE: list[PolicyTestCase] = [
    PolicyTestCase("workflow:create:any", ["project:read:any"], _wf_create),
    PolicyTestCase("workflow:read:any", ["project:read:any"], _wf_list, _setup_workflow),
    PolicyTestCase("credential:create:any", ["project:read:any"], _cred_create, _setup_cred_type),
    PolicyTestCase("credential:read:any", ["project:read:any"], _cred_list, _setup_credential),
    PolicyTestCase("execution:run:any", ["project:read:any", "workflow:read:any"], _exec_run, _setup_workflow),
    PolicyTestCase("execution:read:any", ["project:read:any"], _exec_list),
    PolicyTestCase("project:read:any", [], lambda api, _pid, _ctx: api.projects.list()),
    PolicyTestCase(
        "project:create:any",
        [],
        lambda api, _pid, _ctx: api.projects.create(body=ProjectCreate(name=unique_name("pol-proj"))),
    ),
    PolicyTestCase(
        "role:read:any",
        [],
        lambda api, _pid, _ctx: api.roles.list(),
        skip_denied=True,
    ),
    PolicyTestCase(
        "user:read:any",
        [],
        lambda api, _pid, _ctx: api.users.list(),
        skip_denied=True,
    ),
    PolicyTestCase("group:read:any", [], lambda api, _pid, _ctx: api.groups.list()),
    PolicyTestCase("setting:read:any", [], lambda api, _pid, _ctx: api.settings.list()),
]

# ---------------------------------------------------------------------------
# Self-scoped policy test cases (5)
# Tested via test_baseline.py; included here for completeness tracking.
# ---------------------------------------------------------------------------

SELF_SCOPED_CASES: list[PolicyTestCase] = [
    PolicyTestCase("user:read:self", description="Tested in test_baseline.py"),
    PolicyTestCase("user:update:self", description="Tested in test_baseline.py"),
    PolicyTestCase("role-assignment:read:self", description="Tested in test_baseline.py"),
    PolicyTestCase("user_identity:read:self", description="Tested in test_baseline.py"),
    PolicyTestCase("user_identity:detach:self", description="Tested in test_baseline.py"),
]

# ---------------------------------------------------------------------------
# Own-scoped policy test cases
# Tested via test_credential_ownership.py; included here for coverage tracking.
# ---------------------------------------------------------------------------

OWN_SCOPED_CASES: list[PolicyTestCase] = [
    PolicyTestCase("credential:update:own", description="Tested in test_credential_ownership.py"),
]

# ---------------------------------------------------------------------------
# Policies covered by unit tests only (tests/unit/authz/).
#
# System-scoped e2e tests use a representative subset — not every policy
# needs a full-stack round-trip.  Policies listed here are verified via
# Rego/Rego unit tests and are excluded from the e2e coverage check in
# test_role_conventions.py::TestRegistryIntegrity.
#
# When adding a NEW built-in policy, either:
#   1. Add a PolicyTestCase to the appropriate list above, OR
#   2. Add it to E2E_COVERAGE_EXEMPT with a reason if unit-test coverage is sufficient.
# ---------------------------------------------------------------------------

E2E_COVERAGE_EXEMPT: set[str] = {
    # System-scoped CRUD policies that follow the same pattern as the
    # representative cases already tested e2e (create/read tested, so
    # update/delete for the same resource are unit-test-only).
    "credential:update:any",
    "credential:delete:any",
    "credential:use:any",
    "credential:use:project",
    "workflow:update:any",
    "workflow:delete:any",
    "project:update:any",
    "project:delete:any",
    # Approval policies — read/decide/create/delete follow identical authz path
    "approval:read:any",
    "approval:decide:any",
    "approval:create:any",
    "approval:delete:any",
    # Role & policy management (system-level) — CRUD mirrors project-scoped
    "role:create:any",
    "role:update:any",
    "role:delete:any",
    "policy:create:any",
    "policy:read:any",
    "policy:update:any",
    "policy:delete:any",
    # Role assignments (system-level)
    "role-assignment:read:any",
    "role-assignment:assign:any",
    "role-assignment:revoke:any",
    # User management — user:read:any tested e2e, CRUD mirrors it
    "user:create:any",
    "user:update:any",
    "user:delete:any",
    # Group management — group:read:any tested e2e, CRUD mirrors it
    "group:create:any",
    "group:update:any",
    "group:delete:any",
    "group:manage-members:any",
    # Directory lookups — lightweight read-only
    "user-directory:read:any",
    "group-directory:read:any",
    # User identities (system-scoped)
    "user_identity:read:any",
    "user_identity:attach:any",
    "user_identity:detach:any",
    # Identity providers
    "identity-provider:create:any",
    "identity-provider:read:any",
    "identity-provider:update:any",
    "identity-provider:delete:any",
    "identity-provider:test:any",
    # Tool management — covered by integration authz tests (test_tools_authz.py)
    "tool:read:any",
    "tool:update:any",
    # LLM model management — follows same pattern as tool authz
    "llm_model:read:any",
    "llm_model:update:any",
    # Tool/model project-scoped read — covered by test_tools_visibility.py / test_models_visibility.py
    "tool:read:project",
    "llm_model:read:project",
    # Integration management — CRUD follows same authz path as credentials
    "integration:create:any",
    "integration:read:any",
    "integration:read-all:any",
    "integration:read:project",
    "integration:update:any",
    "integration:delete:any",
    "integration:discover:any",
    "integration:validate:any",
    "integration:refresh:any",
    # Admin revocation — admin-only endpoints
    "admin:revocation:read:any",
    "admin:revocation:execute:any",
    # Settings (write) — read tested e2e
    "setting:write:any",
    # Authz query
    "authz:query:any",
    # Invocations
    "invocation:create:any",
    "invocation:read:any",
    "invocation:cancel:any",
    # Files — E2E needs S3 (); authz path unit-tested
    "files:upload:any",
    "files:download:any",
    "files:delete:any",
    "files:upload:project",
    "files:download:project",
    "files:delete:project",
    # Service accounts (system-scoped — unit-tested via test_rego_service_account.py)
    "service_account:create:any",
    "service_account:read:any",
    "service_account:update:any",
    "service_account:delete:any",
    "service_account:rotate_secret:any",
    "service_account:disable:any",
    "service_account:enable:any",
    # Service accounts (project-scoped)
    "service_account:create:project",
    "service_account:read:project",
    "service_account:update:project",
    "service_account:delete:project",
    "service_account:rotate_secret:project",
    "service_account:disable:project",
    "service_account:enable:project",
}
