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

    Returns (owner_api, non_owner_api, admin_api, project_id).
    """
    project_id, _ = create_project(admin_api, "own-scope")

    owner_id, owner_name, owner_pass = create_user(admin_api, "owner")
    other_id, other_name, other_pass = create_user(admin_api, "nonowner")

    role_name = create_project_role(admin_api, project_id, "own-updater", _OWN_UPDATE_POLICIES)
    assign_project_role_to_user(admin_api, project_id, owner_id, role_name)
    assign_project_role_to_user(admin_api, project_id, other_id, role_name)

    owner_api = api_for(syntara_base_url, owner_name, owner_pass)
    other_api = api_for(syntara_base_url, other_name, other_pass)

    return owner_api, other_api, admin_api, project_id


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
        owner_api, _, admin_api, project_id = ownership_env
        type_id = get_bearer_token_type_id(owner_api)

        cred = owner_api.credentials.create(
            body=CredentialCreate(
                name=unique_name("own-scope-admin"),
                credential_type_id=type_id,
                project_id=project_id,
                inputs=CredentialCreateInputs.from_dict({"token": "secret"}),
            )
        ).assert_and_get()

        resp = admin_api.credentials.update(
            credential_id=cred.id,
            body=CredentialUpdate(description="admin override"),
        )
        assert resp.is_success
