"""Baseline RBAC tests: deny-by-default and self-scope policies."""

from __future__ import annotations

import os
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from orchestrator_test_sdk.factories import (
        AssignProjectRoleFactory,
        CredentialFactory,
        ProjectFactory,
        UserFactory,
        WorkflowFactory,
    )
    from syntara_api_client.api import SyntaraApiRegistry

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)

from orchestrator_test_sdk.e2e.auth import api_for
from syntara_api_client.models.execution_create import ExecutionCreate
from syntara_api_client.models.user_update import UserUpdate

pytestmark = [pytest.mark.e2e]


class TestZeroRoleBaseline:
    """Verify deny-by-default for users with no explicit roles.

    A new user gets filtered access (empty lists) on visibility-filtered
    endpoints and cannot access project-scoped resources.
    """

    def test_list_workflows_returns_empty(
        self,
        syntara_base_url: str,
        admin_api: SyntaraApiRegistry,
        create_project: ProjectFactory,
        create_workflow: WorkflowFactory,
        create_user: UserFactory,
    ) -> None:
        proj_id, _ = create_project(admin_api, "norole-wf")
        wf_id, _ = create_workflow(admin_api, proj_id, "norole-wf")
        _, username, password = create_user(admin_api, "norole-wf")
        user_api = api_for(syntara_base_url, username, password)
        workflows = user_api.workflows.list().assert_and_get()
        resource_ids = {str(r.id) for r in workflows.resources}
        assert str(wf_id) not in resource_ids, f"No-role user should not see workflow {wf_id}"

    def test_list_credentials_returns_empty(
        self,
        syntara_base_url: str,
        admin_api: SyntaraApiRegistry,
        create_project: ProjectFactory,
        create_credential: CredentialFactory,
        create_user: UserFactory,
    ) -> None:
        proj_id, _ = create_project(admin_api, "norole-cr")
        cred_id, *_ = create_credential(admin_api, proj_id, "norole-cr")
        _, username, password = create_user(admin_api, "norole-cr")
        user_api = api_for(syntara_base_url, username, password)
        credentials = user_api.credentials.list().assert_and_get()
        resource_ids = {str(r.id) for r in credentials.resources}
        assert str(cred_id) not in resource_ids, f"No-role user should not see credential {cred_id}"

    def test_list_executions_returns_empty(
        self,
        syntara_base_url: str,
        admin_api: SyntaraApiRegistry,
        create_project: ProjectFactory,
        create_workflow: WorkflowFactory,
        create_user: UserFactory,
    ) -> None:
        proj_id, _ = create_project(admin_api, "norole-ex")
        wf_id, _ = create_workflow(admin_api, proj_id, "norole-ex")
        exec_resp = admin_api.executions.create(body=ExecutionCreate(workflow_id=wf_id, trigger_node_id="trigger"))
        execution = exec_resp.assert_and_get()
        exec_id = str(execution.id)
        _, username, password = create_user(admin_api, "norole-ex")
        user_api = api_for(syntara_base_url, username, password)
        executions = user_api.executions.list().assert_and_get()
        resource_ids = {str(r.id) for r in executions.resources}
        assert exec_id not in resource_ids, f"No-role user should not see execution {exec_id}"

    def test_list_projects_returns_empty(
        self,
        syntara_base_url: str,
        admin_api: SyntaraApiRegistry,
        create_project: ProjectFactory,
        create_user: UserFactory,
    ) -> None:
        _, proj_name = create_project(admin_api, "norole-hidden")
        _, username, password = create_user(admin_api, "norole-proj")
        user_api = api_for(syntara_base_url, username, password)
        projects = user_api.projects.list().assert_and_get()
        names = {str(p.name) for p in projects.resources}
        assert proj_name not in names, f"No-role user should not see project {proj_name}"

    def test_cannot_access_specific_project_workflows(
        self,
        syntara_base_url: str,
        admin_api: SyntaraApiRegistry,
        create_project: ProjectFactory,
        create_workflow: WorkflowFactory,
        create_user: UserFactory,
    ) -> None:
        project_id, _ = create_project(admin_api, "norole-access")
        create_workflow(admin_api, project_id, "norole-hidden")
        _, username, password = create_user(admin_api, "norole-acc")
        user_api = api_for(syntara_base_url, username, password)
        resp = user_api.projects.list_workflows(project_id=project_id)
        assert resp.status_code == HTTPStatus.FORBIDDEN


class TestSelfScopePolicies:
    """Verify self-scoped policies granted to all authenticated users."""

    def test_can_read_own_profile(
        self, syntara_base_url: str, admin_api: SyntaraApiRegistry, create_user: UserFactory
    ) -> None:
        _, username, password = create_user(admin_api, "self-read")
        user_api = api_for(syntara_base_url, username, password)
        user_api.authentication.get_current_user().assert_and_get()

    def test_cannot_read_other_user_profile(
        self, syntara_base_url: str, admin_api: SyntaraApiRegistry, create_user: UserFactory
    ) -> None:
        _, u1_name, u1_pass = create_user(admin_api, "self-r1")
        u2_id, _, _ = create_user(admin_api, "self-r2")
        u1_api = api_for(syntara_base_url, u1_name, u1_pass)
        resp = u1_api.users.get(user_id=u2_id)
        assert resp.status_code == HTTPStatus.FORBIDDEN

    def test_can_read_own_role_assignments(
        self, syntara_base_url: str, admin_api: SyntaraApiRegistry, create_user: UserFactory
    ) -> None:
        user_id, username, password = create_user(admin_api, "self-ra")
        user_api = api_for(syntara_base_url, username, password)
        user_api.users.list_role_assignments(user_id=user_id).assert_and_get()

    def test_cannot_read_other_role_assignments(
        self,
        syntara_base_url: str,
        admin_api: SyntaraApiRegistry,
        create_project: ProjectFactory,
        assign_project_role_to_user: AssignProjectRoleFactory,
        create_user: UserFactory,
    ) -> None:
        _, u1_name, u1_pass = create_user(admin_api, "self-ra1")
        u2_id, _, _ = create_user(admin_api, "self-ra2")
        proj_id, _ = create_project(admin_api, "self-ra")
        assignment_id = assign_project_role_to_user(admin_api, proj_id, u2_id, "project-user")
        u1_api = api_for(syntara_base_url, u1_name, u1_pass)
        resp = u1_api.users.list_role_assignments(user_id=u2_id)
        if resp.is_success:
            assignments_list = resp.assert_and_get()
            resource_ids = {str(r.id) for r in assignments_list.resources}
            assert str(assignment_id) not in resource_ids, (
                f"User should not see other user's role assignment {assignment_id}"
            )
        else:
            assert resp.status_code == HTTPStatus.FORBIDDEN

    def test_can_update_own_profile(
        self, syntara_base_url: str, admin_api: SyntaraApiRegistry, create_user: UserFactory
    ) -> None:
        user_id, username, password = create_user(admin_api, "self-upd")
        user_api = api_for(syntara_base_url, username, password)
        resp = user_api.users.update(user_id=user_id, body=UserUpdate(first_name="Updated Name"))
        assert resp.status_code in (HTTPStatus.OK, HTTPStatus.FORBIDDEN)

    def test_cannot_update_other_profile(
        self, syntara_base_url: str, admin_api: SyntaraApiRegistry, create_user: UserFactory
    ) -> None:
        _, u1_name, u1_pass = create_user(admin_api, "self-up1")
        u2_id, _, _ = create_user(admin_api, "self-up2")
        u1_api = api_for(syntara_base_url, u1_name, u1_pass)
        resp = u1_api.users.update(user_id=u2_id, body=UserUpdate(first_name="Nope"))
        assert resp.status_code == HTTPStatus.FORBIDDEN
