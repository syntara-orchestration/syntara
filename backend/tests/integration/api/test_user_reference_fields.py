"""Integration tests for created_by/updated_by UserReference fields across APIs."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from tests.helpers.user_reference import assert_user_reference
from tests.integration.api.conftest import mcp_payload

if TYPE_CHECKING:
    from httpx import AsyncClient

    from syntara.core.models import User
    from syntara.tool_manager.models import Tool


@pytest.mark.asyncio
class TestIntegrationUserReferenceFields:
    """Verify created_by/updated_by return UserReference objects on integration APIs."""

    async def test_create_get_and_list_return_user_references(self, auth_client: AsyncClient, test_user: User) -> None:
        payload = mcp_payload(f"user-ref-intg-{uuid4().hex[:8]}")
        create_resp = await auth_client.post("/api/v1/integrations", json=payload)
        assert create_resp.status_code == 201
        body = create_resp.json()
        assert_user_reference(body["created_by"], test_user)
        assert_user_reference(body["updated_by"], test_user)

        integration_id = body["id"]
        get_resp = await auth_client.get(f"/api/v1/integrations/{integration_id}")
        assert get_resp.status_code == 200
        assert_user_reference(get_resp.json()["created_by"], test_user)

        list_resp = await auth_client.get("/api/v1/integrations")
        assert list_resp.status_code == 200
        match = next(r for r in list_resp.json()["resources"] if r["id"] == integration_id)
        assert_user_reference(match["created_by"], test_user)

    async def test_update_sets_updated_by_user_reference(self, auth_client: AsyncClient, test_user: User) -> None:
        create_resp = await auth_client.post("/api/v1/integrations", json=mcp_payload())
        assert create_resp.status_code == 201
        integration_id = create_resp.json()["id"]

        patch_resp = await auth_client.patch(
            f"/api/v1/integrations/{integration_id}",
            json={"description": "updated description"},
        )
        assert patch_resp.status_code == 200
        body = patch_resp.json()
        assert_user_reference(body["created_by"], test_user)
        assert_user_reference(body["updated_by"], test_user)


@pytest.mark.asyncio
class TestToolUserReferenceFields:
    """Verify created_by/updated_by return UserReference objects on tool APIs."""

    async def test_get_and_list_return_user_references(
        self, auth_client: AsyncClient, test_user: User, test_tool: Tool
    ) -> None:
        get_resp = await auth_client.get(f"/api/v1/tools/{test_tool.id}")
        assert get_resp.status_code == 200
        assert_user_reference(get_resp.json()["created_by"], test_user)

        list_resp = await auth_client.get("/api/v1/tools")
        assert list_resp.status_code == 200
        match = next(r for r in list_resp.json()["resources"] if r["id"] == str(test_tool.id))
        assert_user_reference(match["created_by"], test_user)


@pytest.mark.asyncio
class TestIdentityProviderUserReferenceFields:
    """Verify created_by/updated_by return UserReference objects on identity provider APIs."""

    async def test_create_get_and_list_return_user_references(
        self, admin_client: AsyncClient, admin_user: User
    ) -> None:
        payload = {
            "name": f"user-ref-idp-{uuid4().hex[:8]}",
            "configuration": {
                "provider_type": "oidc",
                "issuer_url": "https://idp.example.com",
                "client_id": "syntara-client",
                "client_secret": "super-secret",
                "redirect_uri": "https://app.example.com/callback",
            },
        }
        create_resp = await admin_client.post("/api/v1/identity_providers", json=payload)
        assert create_resp.status_code == 201
        body = create_resp.json()
        assert_user_reference(body["created_by"], admin_user)
        assert_user_reference(body["updated_by"], admin_user)

        provider_id = body["id"]
        get_resp = await admin_client.get(f"/api/v1/identity_providers/{provider_id}")
        assert get_resp.status_code == 200
        assert_user_reference(get_resp.json()["created_by"], admin_user)

        list_resp = await admin_client.get("/api/v1/identity_providers")
        assert list_resp.status_code == 200
        match = next(r for r in list_resp.json()["resources"] if r["id"] == provider_id)
        assert_user_reference(match["created_by"], admin_user)


@pytest.mark.asyncio
class TestServiceAccountUserReferenceFields:
    """Verify created_by/updated_by return UserReference objects on service account APIs."""

    async def test_create_get_and_list_return_user_references(
        self, auth_client: AsyncClient, test_user: User, test_project_id: str
    ) -> None:
        payload = {
            "name": f"user-ref-sa-{uuid4().hex[:8]}",
            "project_id": test_project_id,
        }
        create_resp = await auth_client.post("/api/v1/service_accounts", json=payload)
        assert create_resp.status_code == 201
        body = create_resp.json()
        assert_user_reference(body["created_by"], test_user)
        assert_user_reference(body["updated_by"], test_user)

        sa_id = body["id"]
        get_resp = await auth_client.get(f"/api/v1/service_accounts/{sa_id}")
        assert get_resp.status_code == 200
        assert_user_reference(get_resp.json()["created_by"], test_user)

        list_resp = await auth_client.get("/api/v1/service_accounts")
        assert list_resp.status_code == 200
        match = next(r for r in list_resp.json()["resources"] if r["id"] == sa_id)
        assert_user_reference(match["created_by"], test_user)

        cred_resp = await auth_client.post(
            f"/api/v1/service_accounts/{sa_id}/credentials",
            json={"credential_type": "client_credentials"},
        )
        assert cred_resp.status_code == 201
        cred_body = cred_resp.json()
        assert_user_reference(cred_body["created_by"], test_user)
