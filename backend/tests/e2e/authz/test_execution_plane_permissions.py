"""A custom system role grants a non-admin access through the live EP facade."""

from __future__ import annotations

import os
from http import HTTPStatus
from typing import TYPE_CHECKING

import httpx
import pytest
from orchestrator_test_sdk.e2e.auth import local_login_session
from orchestrator_test_sdk.e2e.tls import e2e_ssl_context

if TYPE_CHECKING:
    from orchestrator_test_sdk.factories import RoleFactory, UserFactory, UserRoleAssignmentFactory
    from syntara_api_client.api import SyntaraApiRegistry

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not os.environ.get("APP_BASE_URL"), reason="APP_BASE_URL not set — full stack required"),
    pytest.mark.skipif(not os.environ.get("EP_API_URL"), reason="EP_API_URL not set — live Execution Plane required"),
]


def test_non_admin_target_reader_role(
    syntara_base_url: str,
    admin_api: SyntaraApiRegistry,
    create_user: UserFactory,
    create_role: RoleFactory,
    assign_system_role: UserRoleAssignmentFactory,
) -> None:
    """Grant target read, verify actual inventory access, then revoke the grant."""
    user_id, username, password = create_user(admin_api, "ep-reader", group_names=[])
    token, _ = local_login_session(syntara_base_url, username, password)
    role_name = create_role(admin_api, "ep-reader", ["execution_target:read:any"])
    prefix = f"{syntara_base_url}/api/execution_plane/v1"

    with httpx.Client(
        headers={"Authorization": f"Bearer {token}"},
        verify=e2e_ssl_context(),
        timeout=30,
    ) as client:
        response = client.get(f"{prefix}/execution_targets")
        assert response.status_code == HTTPStatus.FORBIDDEN, response.text

        assignment_id = assign_system_role(admin_api, user_id, role_name)

        response = client.get(f"{prefix}/execution_targets", params={"limit": 1, "include_total": "true"})
        assert response.status_code == HTTPStatus.OK, response.text
        targets = response.json()["resources"]
        # The EP-enabled E2E stack provisions an installed execution target.
        assert targets, "Expected the live EP stack's installed execution target"
        target_id = targets[0]["id"]
        response = client.get(f"{prefix}/execution_targets/{target_id}")
        assert response.status_code == HTTPStatus.OK, response.text
        assert response.json()["id"] == target_id

        response = client.get(f"{prefix}/work_items")
        assert response.status_code == HTTPStatus.FORBIDDEN, response.text
        # An empty patch is harmless even if authorization regresses, but still
        # exercises the update permission on a real target.
        response = client.patch(f"{prefix}/execution_targets/{target_id}", json={})
        assert response.status_code == HTTPStatus.FORBIDDEN, response.text

        revoked = admin_api.users.delete_role_assignment(user_id=user_id, assignment_id=assignment_id)
        assert revoked.is_success
        response = client.get(f"{prefix}/execution_targets")
        assert response.status_code == HTTPStatus.FORBIDDEN, response.text
