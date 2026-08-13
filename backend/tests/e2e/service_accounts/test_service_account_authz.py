"""E2E tests for service account RBAC authorization (API-5,6,7,8,25,34).

Covers:
  API-5:  Project-scoped CRUD — project admin can manage own project SAs
  API-6:  Cross-project operations denied with 403
  API-7:  Platform admin sees all service accounts across projects
  API-8:  CRUD policy enforcement — project-auditor has read-only, not write
  API-25: Role assignment — direct only, group membership rejected
  API-34: Cross-project visibility — SA not visible to other project admin
          until owning project grants service_account:read
"""

from __future__ import annotations

import os
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from syntara_api_client.models.group_member_add import GroupMemberAdd
from syntara_api_client.models.role_assignment_create import RoleAssignmentCreate
from syntara_api_client.models.service_account_create import ServiceAccountCreate
from syntara_api_client.models.service_account_update import ServiceAccountUpdate

if TYPE_CHECKING:
    from orchestrator_test_sdk.factories import (
        AssignProjectRoleFactory,
        GroupFactory,
        ProjectFactory,
        UserFactory,
    )
    from syntara_api_client.api import SyntaraApiRegistry

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)

from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.auth import api_for

from tests.e2e.service_accounts import create_sa

pytestmark = [pytest.mark.e2e]


class TestProjectAdminCRUD:
    """API-5: Project admin can manage own project SAs."""

    def test_project_admin_full_crud_lifecycle(
        self,
        syntara_base_url: str,
        admin_api: SyntaraApiRegistry,
        create_project: ProjectFactory,
        create_user: UserFactory,
        assign_project_role_to_user: AssignProjectRoleFactory,
    ) -> None:
        project_id, _ = create_project(admin_api, "pa-crud")
        user_id, username, password = create_user(admin_api, "pa-crud")
        assign_project_role_to_user(admin_api, project_id, user_id, "project-admin")

        user_api = api_for(syntara_base_url, username, password)

        # Create
        sa = create_sa(user_api, project_id)
        sa_id = sa.id

        try:
            # Read detail
            detail = user_api.service_accounts.get(service_account_id=sa_id).assert_and_get()
            assert detail.id == sa_id

            # List
            list_resp = user_api.service_accounts.list().assert_and_get()
            assert any(r.id == sa_id for r in list_resp.resources)

            # Update
            new_name = unique_name("e2e-authz-sa-upd")
            updated = user_api.service_accounts.update(
                service_account_id=sa_id,
                body=ServiceAccountUpdate(name=new_name),
            ).assert_and_get()
            assert updated.name == new_name

            # Delete
            del_resp = user_api.service_accounts.delete(service_account_id=sa_id)
            assert del_resp.status_code == HTTPStatus.NO_CONTENT
        except Exception:
            admin_api.service_accounts.delete(service_account_id=sa_id)
            raise


class TestCrossProjectDenied:
    """API-6: Cross-project operations denied with 403."""

    def test_project_admin_cannot_access_other_project_sas(
        self,
        syntara_base_url: str,
        admin_api: SyntaraApiRegistry,
        create_project: ProjectFactory,
        create_user: UserFactory,
        assign_project_role_to_user: AssignProjectRoleFactory,
    ) -> None:
        alpha_id, _ = create_project(admin_api, "alpha")
        beta_id, _ = create_project(admin_api, "beta")
        user_id, username, password = create_user(admin_api, "cross-deny")
        assign_project_role_to_user(admin_api, alpha_id, user_id, "project-admin")

        beta_sa = create_sa(admin_api, beta_id)

        user_api = api_for(syntara_base_url, username, password)

        try:
            # Create in beta → 403
            create_resp = user_api.service_accounts.create(
                body=ServiceAccountCreate(name=unique_name("cross-deny"), project_id=beta_id),
            )
            assert create_resp.status_code == HTTPStatus.FORBIDDEN

            # Get beta SA → 403
            get_resp = user_api.service_accounts.get(service_account_id=beta_sa.id)
            assert get_resp.status_code == HTTPStatus.FORBIDDEN

            # Update beta SA → 403
            update_resp = user_api.service_accounts.update(
                service_account_id=beta_sa.id,
                body=ServiceAccountUpdate(description="hacked"),
            )
            assert update_resp.status_code == HTTPStatus.FORBIDDEN

            # Delete beta SA → 403
            delete_resp = user_api.service_accounts.delete(service_account_id=beta_sa.id)
            assert delete_resp.status_code == HTTPStatus.FORBIDDEN
        finally:
            admin_api.service_accounts.delete(service_account_id=beta_sa.id)


class TestPlatformAdminSeesAll:
    """API-7: Platform admin sees all service accounts across projects."""

    def test_admin_sees_sas_in_all_projects(
        self,
        admin_api: SyntaraApiRegistry,
        create_project: ProjectFactory,
    ) -> None:
        proj_a_id, _ = create_project(admin_api, "vis-a")
        proj_b_id, _ = create_project(admin_api, "vis-b")

        sa_a = create_sa(admin_api, proj_a_id)
        sa_b = create_sa(admin_api, proj_b_id)

        try:
            # List all — both should appear
            list_resp = admin_api.service_accounts.list().assert_and_get()
            listed_ids = {r.id for r in list_resp.resources}
            assert sa_a.id in listed_ids, "SA from project A not in admin list"
            assert sa_b.id in listed_ids, "SA from project B not in admin list"

            # Get each individually
            admin_api.service_accounts.get(service_account_id=sa_a.id).assert_and_get()
            admin_api.service_accounts.get(service_account_id=sa_b.id).assert_and_get()
        finally:
            admin_api.service_accounts.delete(service_account_id=sa_a.id)
            admin_api.service_accounts.delete(service_account_id=sa_b.id)


class TestCRUDPolicyEnforcement:
    """API-8: CRUD policy enforcement — project-auditor has read-only, not write."""

    def test_auditor_can_read_but_not_write(
        self,
        syntara_base_url: str,
        admin_api: SyntaraApiRegistry,
        create_project: ProjectFactory,
        create_user: UserFactory,
        assign_project_role_to_user: AssignProjectRoleFactory,
    ) -> None:
        project_id, _ = create_project(admin_api, "auditor")
        user_id, username, password = create_user(admin_api, "auditor")
        assign_project_role_to_user(admin_api, project_id, user_id, "project-auditor")

        sa = create_sa(admin_api, project_id)

        auditor_api = api_for(syntara_base_url, username, password)

        try:
            # Read detail → 200
            detail = auditor_api.service_accounts.get(service_account_id=sa.id).assert_and_get()
            assert detail.id == sa.id

            # List → 200, SA appears
            list_resp = auditor_api.service_accounts.list().assert_and_get()
            assert any(r.id == sa.id for r in list_resp.resources)

            # Create → 403
            create_resp = auditor_api.service_accounts.create(
                body=ServiceAccountCreate(name=unique_name("auditor-deny"), project_id=project_id),
            )
            assert create_resp.status_code == HTTPStatus.FORBIDDEN

            # Update → 403
            update_resp = auditor_api.service_accounts.update(
                service_account_id=sa.id,
                body=ServiceAccountUpdate(description="denied"),
            )
            assert update_resp.status_code == HTTPStatus.FORBIDDEN

            # Delete → 403
            delete_resp = auditor_api.service_accounts.delete(service_account_id=sa.id)
            assert delete_resp.status_code == HTTPStatus.FORBIDDEN
        finally:
            admin_api.service_accounts.delete(service_account_id=sa.id)


class TestRoleAssignmentToServiceAccount:
    """API-25: Role assignment — direct only, group membership rejected."""

    def test_direct_role_assignment_to_service_account(
        self,
        admin_api: SyntaraApiRegistry,
        create_project: ProjectFactory,
    ) -> None:
        """Assign a project role directly to a service account."""
        project_id, _ = create_project(admin_api, "sa-role")
        sa = create_sa(admin_api, project_id)

        try:
            resp = admin_api.projects.create_role_assignment(
                project_id=project_id,
                body=RoleAssignmentCreate(
                    principal_id=sa.id,
                    role_name="project-admin",
                ),
            )
            assert resp.status_code == HTTPStatus.CREATED, f"Expected 201, got {resp.status_code}: {resp.content!r}"
        finally:
            admin_api.service_accounts.delete(service_account_id=sa.id)

    def test_service_account_cannot_be_group_member(
        self,
        admin_api: SyntaraApiRegistry,
        create_project: ProjectFactory,
        create_group: GroupFactory,
    ) -> None:
        """GroupMemberAdd only accepts user_id — SA UUID is rejected."""
        project_id, _ = create_project(admin_api, "sa-grp")
        group_id, _ = create_group(admin_api, "sa-grp")
        sa = create_sa(admin_api, project_id)

        try:
            resp = admin_api.groups.add_member(
                group_id=group_id,
                body=GroupMemberAdd(user_id=sa.id),
            )
            assert resp.status_code == HTTPStatus.NOT_FOUND, (
                f"Expected 404 (SA UUID is not a user), got {resp.status_code}: {resp.content!r}"
            )
        finally:
            admin_api.service_accounts.delete(service_account_id=sa.id)


class TestCrossProjectVisibility:
    """API-34: Cross-project visibility — SA not visible until project grants read."""

    def test_sa_visible_only_after_role_grant(
        self,
        syntara_base_url: str,
        admin_api: SyntaraApiRegistry,
        create_project: ProjectFactory,
        create_user: UserFactory,
        assign_project_role_to_user: AssignProjectRoleFactory,
    ) -> None:
        alpha_id, _ = create_project(admin_api, "vis-alpha")
        beta_id, _ = create_project(admin_api, "vis-beta")
        user_id, username, password = create_user(admin_api, "vis-user")

        # User is project-admin on beta only
        assign_project_role_to_user(admin_api, beta_id, user_id, "project-admin")

        alpha_sa = create_sa(admin_api, alpha_id)

        user_api = api_for(syntara_base_url, username, password)

        try:
            # Alpha SA should NOT be visible
            list_before = user_api.service_accounts.list().assert_and_get()
            visible_ids_before = {r.id for r in list_before.resources}
            assert alpha_sa.id not in visible_ids_before, "Alpha SA visible before role grant"

            # Grant project-admin on alpha
            assign_project_role_to_user(admin_api, alpha_id, user_id, "project-admin")

            # Re-authenticate to pick up new permissions
            user_api = api_for(syntara_base_url, username, password)

            # Alpha SA should now be visible
            list_after = user_api.service_accounts.list().assert_and_get()
            visible_ids_after = {r.id for r in list_after.resources}
            assert alpha_sa.id in visible_ids_after, "Alpha SA not visible after role grant"
        finally:
            admin_api.service_accounts.delete(service_account_id=alpha_sa.id)
