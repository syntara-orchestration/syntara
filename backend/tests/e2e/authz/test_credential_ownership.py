"""Credential ownership (own-scope) authorization tests.

Verifies that ``credential:update:own`` correctly gates updates to the
credential's owner, and that non-owners with the same policy are denied.
"""

from __future__ import annotations

import os
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from uuid import UUID

    from syntara_api_client.api import SyntaraApiRegistry

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)

from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.auth import api_for
from orchestrator_test_sdk.factories import (
    AssignProjectRoleFactory,
    ProjectFactory,
    ProjectRoleFactory,
    UserFactory,
    get_bearer_token_type_id,
)
from syntara_api_client.models.credential_create import CredentialCreate
from syntara_api_client.models.credential_create_inputs import CredentialCreateInputs
from syntara_api_client.models.credential_update import CredentialUpdate

pytestmark = [pytest.mark.e2e]

_OWN_UPDATE_POLICIES = [
    "credential:create:project",
    "credential:read:project",
    "credential:update:own",
    "project:read:project",
]


@pytest.fixture(scope="module")
def ownership_env(
    admin_api: SyntaraApiRegistry,
    create_user: UserFactory,
    create_project_role: ProjectRoleFactory,
    create_project: ProjectFactory,
    assign_project_role_to_user: AssignProjectRoleFactory,
    syntara_base_url: str,
) -> tuple[SyntaraApiRegistry, SyntaraApiRegistry, SyntaraApiRegistry, UUID]:
    """Set up two project-users (owner, non-owner) and a project-admin.

    Returns (owner_api, non_owner_api, project_admin_api, project_id).
    """
    project_id, _ = create_project(admin_api, "own-scope")

    owner_id, owner_name, owner_pass = create_user(admin_api, "owner")
    other_id, other_name, other_pass = create_user(admin_api, "nonowner")
    proj_admin_id, proj_admin_name, proj_admin_pass = create_user(admin_api, "proj-admin")

    role_name = create_project_role(admin_api, project_id, "own-updater", _OWN_UPDATE_POLICIES)
    assign_project_role_to_user(admin_api, project_id, owner_id, role_name)
    assign_project_role_to_user(admin_api, project_id, other_id, role_name)

    # Assign built-in project-admin role
    from syntara_api_client.models.role_assignment_create import RoleAssignmentCreate

    admin_api.projects.create_role_assignment(
        project_id=project_id,
        body=RoleAssignmentCreate(principal_id=proj_admin_id, role_name="project-admin"),
    ).assert_and_get()

    owner_api = api_for(syntara_base_url, owner_name, owner_pass)
    other_api = api_for(syntara_base_url, other_name, other_pass)
    proj_admin_api = api_for(syntara_base_url, proj_admin_name, proj_admin_pass)

    return owner_api, other_api, proj_admin_api, project_id


class TestOwnScopeCredentialUpdate:
    """Verify ownership-gated credential updates."""

    def test_owner_can_update_own_credential(
        self, ownership_env: tuple[SyntaraApiRegistry, SyntaraApiRegistry, SyntaraApiRegistry, UUID]
    ) -> None:
        """Project-user who created the credential can update it."""
        owner_api, _, _, project_id = ownership_env
        type_id = get_bearer_token_type_id(owner_api)

        cred = owner_api.credentials.create(
            body=CredentialCreate(
                name=unique_name("own-scope-mine"),
                credential_type_id=type_id,
                project_id=project_id,
                inputs=CredentialCreateInputs.from_dict({"token": "secret"}),
            )
        ).assert_and_get()

        resp = owner_api.credentials.update(
            credential_id=cred.id,
            body=CredentialUpdate(description="owner updated"),
        )
        assert resp.is_success

    def test_non_owner_denied_update(
        self, ownership_env: tuple[SyntaraApiRegistry, SyntaraApiRegistry, SyntaraApiRegistry, UUID]
    ) -> None:
        """Project-user who did NOT create the credential is denied."""
        owner_api, other_api, _, project_id = ownership_env
        type_id = get_bearer_token_type_id(owner_api)

        cred = owner_api.credentials.create(
            body=CredentialCreate(
                name=unique_name("own-scope-other"),
                credential_type_id=type_id,
                project_id=project_id,
                inputs=CredentialCreateInputs.from_dict({"token": "secret"}),
            )
        ).assert_and_get()

        resp = other_api.credentials.update(
            credential_id=cred.id,
            body=CredentialUpdate(description="not my credential"),
        )
        assert resp.status_code == HTTPStatus.FORBIDDEN

    def test_project_admin_can_update_any_credential(
        self, ownership_env: tuple[SyntaraApiRegistry, SyntaraApiRegistry, SyntaraApiRegistry, UUID]
    ) -> None:
        """Project-admin (with credential:update:project) can update any credential."""
        owner_api, _, proj_admin_api, project_id = ownership_env
        type_id = get_bearer_token_type_id(owner_api)

        cred = owner_api.credentials.create(
            body=CredentialCreate(
                name=unique_name("own-scope-admin"),
                credential_type_id=type_id,
                project_id=project_id,
                inputs=CredentialCreateInputs.from_dict({"token": "secret"}),
            )
        ).assert_and_get()

        resp = proj_admin_api.credentials.update(
            credential_id=cred.id,
            body=CredentialUpdate(description="admin override"),
        )
        assert resp.is_success


class TestBuiltinProjectUserOwnership:
    """Verify builtin project-user role enforces own-scope for credential updates.

    This test class addresses the original BOLA vulnerability: builtin project-user
    used to have credential:update:project (allowing any project member to update
    any credential). It now has credential:update:own, restricting updates to
    the credential's owner.
    """

    def test_builtin_project_user_owner_can_update(
        self,
        admin_api: SyntaraApiRegistry,
        create_user: UserFactory,
        create_project: ProjectFactory,
        syntara_base_url: str,
    ) -> None:
        """User with builtin project-user role can update their own credential."""
        project_id, _ = create_project(admin_api, "builtin-own-test")
        owner_id, owner_name, owner_pass = create_user(admin_api, "builtin-owner")

        # Assign builtin project-user role
        from syntara_api_client.models.role_assignment_create import RoleAssignmentCreate

        admin_api.projects.create_role_assignment(
            project_id=project_id,
            body=RoleAssignmentCreate(principal_id=owner_id, role_name="project-user"),
        ).assert_and_get()

        owner_api = api_for(syntara_base_url, owner_name, owner_pass)
        type_id = get_bearer_token_type_id(owner_api)

        cred = owner_api.credentials.create(
            body=CredentialCreate(
                name=unique_name("builtin-own"),
                credential_type_id=type_id,
                project_id=project_id,
                inputs=CredentialCreateInputs.from_dict({"token": "secret"}),
            )
        ).assert_and_get()

        # Owner should be able to update their own credential
        resp = owner_api.credentials.update(
            credential_id=cred.id,
            body=CredentialUpdate(description="owner updated"),
        )
        assert resp.is_success

    def test_builtin_project_user_non_owner_denied(
        self,
        admin_api: SyntaraApiRegistry,
        create_user: UserFactory,
        create_project: ProjectFactory,
        syntara_base_url: str,
    ) -> None:
        """User with builtin project-user role CANNOT update others' credentials.

        This is the BOLA regression test: before the fix, builtin project-user
        had credential:update:project, allowing any project member to update
        any credential. After the fix, it has credential:update:own, which
        should deny this update.
        """
        project_id, _ = create_project(admin_api, "builtin-bola-test")
        owner_id, owner_name, owner_pass = create_user(admin_api, "builtin-victim")
        other_id, other_name, other_pass = create_user(admin_api, "builtin-attacker")

        # Assign builtin project-user role to both users
        from syntara_api_client.models.role_assignment_create import RoleAssignmentCreate

        admin_api.projects.create_role_assignment(
            project_id=project_id,
            body=RoleAssignmentCreate(principal_id=owner_id, role_name="project-user"),
        ).assert_and_get()
        admin_api.projects.create_role_assignment(
            project_id=project_id,
            body=RoleAssignmentCreate(principal_id=other_id, role_name="project-user"),
        ).assert_and_get()

        owner_api = api_for(syntara_base_url, owner_name, owner_pass)
        other_api = api_for(syntara_base_url, other_name, other_pass)
        type_id = get_bearer_token_type_id(owner_api)

        # Owner creates credential
        cred = owner_api.credentials.create(
            body=CredentialCreate(
                name=unique_name("builtin-bola-cred"),
                credential_type_id=type_id,
                project_id=project_id,
                inputs=CredentialCreateInputs.from_dict({"token": "victim-secret"}),
            )
        ).assert_and_get()

        # Non-owner with same builtin project-user role attempts update
        resp = other_api.credentials.update(
            credential_id=cred.id,
            body=CredentialUpdate(description="BOLA attempt"),
        )
        assert resp.status_code == HTTPStatus.FORBIDDEN, (
            "Non-owner with builtin project-user role should be denied. "
            "If this passes, the BOLA vulnerability has regressed."
        )


class TestOwnScopeEdgeCases:
    """Verify edge cases and boundary conditions for own-scope."""

    def test_cross_project_isolation(
        self,
        admin_api: SyntaraApiRegistry,
        create_user: UserFactory,
        create_project: ProjectFactory,
        create_project_role: ProjectRoleFactory,
        assign_project_role_to_user: AssignProjectRoleFactory,
        syntara_base_url: str,
    ) -> None:
        """User cannot update credential from different project, even if they created it.

        This test verifies project boundary enforcement: credential:update:own
        requires BOTH ownership match AND project match. A user with the policy
        only in project B cannot update a project-A credential, even if they own it.
        """
        # Create two projects
        proj_a_id, _ = create_project(admin_api, "cross-proj-a")
        proj_b_id, _ = create_project(admin_api, "cross-proj-b")

        # Create user with credential:update:own ONLY in project B
        user_id, username, password = create_user(admin_api, "cross-user")
        role_b = create_project_role(admin_api, proj_b_id, "own-b", _OWN_UPDATE_POLICIES)
        assign_project_role_to_user(admin_api, proj_b_id, user_id, role_b)

        # Also give user project-user role in project A (so they can create credential)
        # but WITHOUT credential:update:own
        from syntara_api_client.models.role_assignment_create import RoleAssignmentCreate

        admin_api.projects.create_role_assignment(
            project_id=proj_a_id,
            body=RoleAssignmentCreate(principal_id=user_id, role_name="project-user"),
        ).assert_and_get()

        user_api = api_for(syntara_base_url, username, password)
        type_id = get_bearer_token_type_id(user_api)

        # User creates credential in project A (they have project-user role)
        cred_a = user_api.credentials.create(
            body=CredentialCreate(
                name=unique_name("cross-proj-cred-a"),
                credential_type_id=type_id,
                project_id=proj_a_id,
                inputs=CredentialCreateInputs.from_dict({"token": "secret-a"}),
            )
        ).assert_and_get()

        # Now revoke project-user from project A and verify they can't update
        # even though they have credential:update:own in project B
        assignments = admin_api.projects.list_role_assignments(project_id=proj_a_id).assert_and_get()
        user_assignment = next((a for a in assignments.resources if str(a.principal_id) == str(user_id)), None)
        if user_assignment:
            admin_api.projects.delete_role_assignment(project_id=proj_a_id, assignment_id=user_assignment.id)

        # User attempts to update the project-A credential
        # They own it, but their credential:update:own policy is in project B,
        # and the Rego check requires policy.project == resource.project
        resp = user_api.credentials.update(
            credential_id=cred_a.id,
            body=CredentialUpdate(description="trying with wrong-project policy"),
        )

        assert resp.status_code == HTTPStatus.FORBIDDEN, (
            "User should be denied: they own the credential but their "
            "credential:update:own policy is in project B, not project A"
        )

    def test_orphaned_credential_admin_can_update(
        self,
        admin_api: SyntaraApiRegistry,
        create_user: UserFactory,
        create_project: ProjectFactory,
        syntara_base_url: str,
    ) -> None:
        """Project-admin can update credential even when original owner is deleted.

        This test verifies graceful degradation: when a user is deleted, their
        credentials become "orphaned" (created_by points to deleted user). The
        project-admin should still be able to manage these credentials via
        credential:update:project scope (which doesn't check ownership).
        """
        project_id, _ = create_project(admin_api, "orphan-proj")
        user_id, username, password = create_user(admin_api, "temp-owner")

        # Assign temporary user to project so they can create credential
        from syntara_api_client.models.role_assignment_create import RoleAssignmentCreate

        admin_api.projects.create_role_assignment(
            project_id=project_id,
            body=RoleAssignmentCreate(principal_id=user_id, role_name="project-user"),
        ).assert_and_get()

        user_api = api_for(syntara_base_url, username, password)
        type_id = get_bearer_token_type_id(user_api)

        # User creates credential
        cred = user_api.credentials.create(
            body=CredentialCreate(
                name=unique_name("orphan-cred"),
                credential_type_id=type_id,
                project_id=project_id,
                inputs=CredentialCreateInputs.from_dict({"token": "orphan-secret"}),
            )
        ).assert_and_get()

        # Delete the user (simulating employee departure)
        admin_api.users.delete(user_id=user_id)

        # Admin should still be able to update the orphaned credential
        resp = admin_api.credentials.update(
            credential_id=cred.id,
            body=CredentialUpdate(description="admin managing orphaned credential"),
        )
        assert resp.is_success, "Project-admin should manage orphaned credentials"
