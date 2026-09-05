"""Integration tests for WorkflowRead created_by/updated_by UserReference fields."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest

from tests.helpers.workflow import create_minimal_workflow_definition

if TYPE_CHECKING:
    from httpx import AsyncClient

    from syntara.core.models import User


@pytest.mark.asyncio
class TestWorkflowUserReferenceFields:
    """Verify created_by/updated_by return UserReference objects on workflow APIs."""

    async def test_create_returns_user_reference(
        self, jwt_client: AsyncClient, test_user: User, test_project_id: UUID
    ) -> None:
        payload = {
            "name": f"user-ref-create-{uuid4().hex[:8]}",
            "workflow_definition": create_minimal_workflow_definition(name="user-ref-create"),
            "project_id": str(test_project_id),
        }
        resp = await jwt_client.post("/api/v1/workflows", json=payload)
        assert resp.status_code == 201
        body = resp.json()

        assert isinstance(body["created_by"], dict)
        assert body["created_by"]["id"] == str(test_user.id)
        assert body["created_by"]["name"] == test_user.username
        # updated_by is set to the creator on creation, matching the credentials pattern
        assert isinstance(body["updated_by"], dict)
        assert body["updated_by"]["id"] == str(test_user.id)
        assert body["updated_by"]["name"] == test_user.username

    async def test_get_and_list_return_user_references(
        self, jwt_client: AsyncClient, test_user: User, test_project_id: UUID
    ) -> None:
        payload = {
            "name": f"user-ref-list-{uuid4().hex[:8]}",
            "workflow_definition": create_minimal_workflow_definition(name="user-ref-list"),
            "project_id": str(test_project_id),
        }
        create_resp = await jwt_client.post("/api/v1/workflows", json=payload)
        assert create_resp.status_code == 201
        workflow_id = create_resp.json()["id"]

        get_resp = await jwt_client.get(f"/api/v1/workflows/{workflow_id}")
        assert get_resp.status_code == 200
        get_body = get_resp.json()
        assert isinstance(get_body["created_by"], dict)
        assert get_body["created_by"]["id"] == str(test_user.id)
        assert get_body["created_by"]["name"] == test_user.username

        list_resp = await jwt_client.get("/api/v1/workflows")
        assert list_resp.status_code == 200
        match = next(r for r in list_resp.json()["resources"] if r["id"] == workflow_id)
        assert isinstance(match["created_by"], dict)
        assert match["created_by"]["id"] == str(test_user.id)
        assert match["created_by"]["name"] == test_user.username

    async def test_update_sets_updated_by_user_reference(
        self, jwt_client: AsyncClient, test_user: User, test_project_id: UUID
    ) -> None:
        payload = {
            "name": f"user-ref-update-{uuid4().hex[:8]}",
            "workflow_definition": create_minimal_workflow_definition(name="user-ref-update"),
            "project_id": str(test_project_id),
        }
        create_resp = await jwt_client.post("/api/v1/workflows", json=payload)
        assert create_resp.status_code == 201
        workflow_id = create_resp.json()["id"]

        patch_resp = await jwt_client.patch(
            f"/api/v1/workflows/{workflow_id}",
            json={"description": "updated description"},
        )
        assert patch_resp.status_code == 200
        body = patch_resp.json()
        assert isinstance(body["created_by"], dict)
        assert body["created_by"]["id"] == str(test_user.id)
        assert isinstance(body["updated_by"], dict)
        assert body["updated_by"]["id"] == str(test_user.id)
        assert body["updated_by"]["name"] == test_user.username
