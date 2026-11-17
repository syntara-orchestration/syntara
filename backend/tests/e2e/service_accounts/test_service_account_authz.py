"""E2E tests for service account RBAC authorization (API-5,6,7,8,25,34).

Covers:
  API-5:  Authenticated users create/read; system admins manage
  API-6:  Project roles do not grant service-account management
  API-7:  Platform admin sees all service accounts
  API-8:  System auditors have metadata access
  API-25: Role assignment — direct only, group membership rejected
  API-34: Project grants do not grant account management
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
        UserRoleAssignmentFactory,
    )
    from syntara_api_client.api import SyntaraApiRegistry

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)

from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.auth import api_for

from tests.e2e.service_accounts import create_sa

pytestmark = [pytest.mark.e2e]


class TestProjectAdminCRUD:
    """API-5: Project admins receive the authenticated create/read grants only."""

    def test_project_admin_can_create_and_read_but_not_manage(
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
        sa = create_sa(user_api)
        sa_id = sa.id

        try:
            # Read detail
            detail = user_api.service_accounts.get(service_account_id=sa_id).assert_and_get()
            assert detail.id == sa_id

            # List
            list_resp = user_api.service_accounts.list().assert_and_get()
            assert any(r.id == sa_id for r in list_resp.resources)

            # The creator and project-admin role do not grant management rights.
            update_resp = user_api.service_accounts.update(
                service_account_id=sa_id,
                body=ServiceAccountUpdate(description="denied"),
            )
            assert update_resp.status_code == HTTPStatus.FORBIDDEN
            delete_resp = user_api.service_accounts.delete(service_account_id=sa_id)
            assert delete_resp.status_code == HTTPStatus.FORBIDDEN
        except Exception:
            admin_api.service_accounts.delete(service_account_id=sa_id)
            raise


class TestCrossProjectRead:
    """API-6: All authenticated users can read accounts, but only admins manage them."""

    def test_project_admin_can_read_other_accounts_but_not_manage_them(
        self,
        syntara_base_url: str,
        admin_api: SyntaraApiRegistry,
        create_project: ProjectFactory,
        create_user: UserFactory,
        assign_project_role_to_user: AssignProjectRoleFactory,
    ) -> None:
        alpha_id, _ = create_project(admin_api, "alpha")
        user_id, username, password = create_user(admin_api, "cross-deny")
        assign_project_role_to_user(admin_api, alpha_id, user_id, "project-admin")

        beta_sa = create_sa(admin_api)

        user_api = api_for(syntara_base_url, username, password)

        try:
            # Signed-in humans can create independent identities
            create_resp = user_api.service_accounts.create(
                body=ServiceAccountCreate(name=unique_name("cross-deny")),
            )
            assert create_resp.status_code == HTTPStatus.CREATED
            user_api.service_accounts.delete(service_account_id=create_resp.assert_and_get().id)

            # Read is system-wide for authenticated users.
            detail = user_api.service_accounts.get(service_account_id=beta_sa.id).assert_and_get()
            assert detail.id == beta_sa.id
            listing = user_api.service_accounts.list().assert_and_get()
            assert beta_sa.id in {account.id for account in listing.resources}

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
    """API-7: Platform admin sees all service accounts."""

    def test_admin_sees_all_service_accounts(
        self,
        admin_api: SyntaraApiRegistry,
    ) -> None:
        sa_a = create_sa(admin_api)
        sa_b = create_sa(admin_api)

        try:
            # List all — both should appear
            list_resp = admin_api.service_accounts.list().assert_and_get()
            listed_ids = {r.id for r in list_resp.resources}
            assert sa_a.id in listed_ids, "First service account missing from admin list"
            assert sa_b.id in listed_ids, "Second service account missing from admin list"

            # Get each individually
            admin_api.service_accounts.get(service_account_id=sa_a.id).assert_and_get()
            admin_api.service_accounts.get(service_account_id=sa_b.id).assert_and_get()
        finally:
            admin_api.service_accounts.delete(service_account_id=sa_a.id)
            admin_api.service_accounts.delete(service_account_id=sa_b.id)


class TestCRUDPolicyEnforcement:
    """API-8: System auditors have metadata access."""

    def test_auditor_can_read_but_not_write(
        self,
        syntara_base_url: str,
        admin_api: SyntaraApiRegistry,
        create_project: ProjectFactory,
        create_user: UserFactory,
        assign_project_role_to_user: AssignProjectRoleFactory,
        assign_system_role: UserRoleAssignmentFactory,
    ) -> None:
        user_id, username, password = create_user(admin_api, "auditor")
        assign_system_role(admin_api, user_id, "auditor")

        sa = create_sa(admin_api)

        auditor_api = api_for(syntara_base_url, username, password)

        try:
            # Read detail → 200
            detail = auditor_api.service_accounts.get(service_account_id=sa.id).assert_and_get()
            assert detail.id == sa.id

            # List → 200, SA appears
            list_resp = auditor_api.service_accounts.list().assert_and_get()
            assert any(r.id == sa.id for r in list_resp.resources)

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
        sa = create_sa(admin_api)

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

    def test_system_role_assignment_is_visible_and_revocable(self, admin_api: SyntaraApiRegistry) -> None:
        sa = create_sa(admin_api)

        try:
            assignment = admin_api.role_assignments.create(
                body=RoleAssignmentCreate(principal_id=sa.id, role_name="auditor")
            ).assert_and_get()
            assert assignment.project_id is None

            visible = admin_api.role_assignments.list(principal_id=sa.id).assert_and_get()
            assert any(row.id == assignment.id and row.role_name == "auditor" for row in visible.resources)

            revoked = admin_api.role_assignments.delete(assignment_id=assignment.id)
            assert revoked.status_code == HTTPStatus.NO_CONTENT
            remaining = admin_api.role_assignments.list(principal_id=sa.id).assert_and_get()
            assert all(row.id != assignment.id for row in remaining.resources)
        finally:
            admin_api.service_accounts.delete(service_account_id=sa.id)

    def test_service_account_cannot_be_group_member(
        self,
        admin_api: SyntaraApiRegistry,
        create_project: ProjectFactory,
        create_group: GroupFactory,
    ) -> None:
        """GroupMemberAdd only accepts user_id — SA UUID is rejected."""
        group_id, _ = create_group(admin_api, "sa-grp")
        sa = create_sa(admin_api)

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
    """API-34: Project grants never convey account ownership."""

    def test_project_role_grant_does_not_expose_account(
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

        alpha_sa = create_sa(admin_api)

        user_api = api_for(syntara_base_url, username, password)

        try:
            # All authenticated users can read identities before any project grant.
            list_before = user_api.service_accounts.list().assert_and_get()
            assert alpha_sa.id in {r.id for r in list_before.resources}
            assert user_api.service_accounts.get(service_account_id=alpha_sa.id).status_code == HTTPStatus.OK
            assert (
                user_api.service_accounts.update(
                    service_account_id=alpha_sa.id,
                    body=ServiceAccountUpdate(description="denied"),
                ).status_code
                == HTTPStatus.FORBIDDEN
            )

            # Grant project-admin on alpha
            assign_project_role_to_user(admin_api, alpha_id, user_id, "project-admin")

            # Re-authenticate to pick up new permissions
            user_api = api_for(syntara_base_url, username, password)

            # Project administration does not change service-account access.
            list_after = user_api.service_accounts.list().assert_and_get()
            visible_ids_after = {r.id for r in list_after.resources}
            assert alpha_sa.id in visible_ids_after
            directory = user_api.service_accounts.list_directory(name=alpha_sa.name).assert_and_get()
            assert any(entry.id == alpha_sa.id for entry in directory.resources)
            assert (
                user_api.service_accounts.update(
                    service_account_id=alpha_sa.id,
                    body=ServiceAccountUpdate(description="still denied"),
                ).status_code
                == HTTPStatus.FORBIDDEN
            )
        finally:
            admin_api.service_accounts.delete(service_account_id=alpha_sa.id)
