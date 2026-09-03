"""Integration tests for workflow version list pagination and published_version_number.

Tests for:
- GET /api/v1/workflows/{id}/versions (cursor pagination, status, username)
- published_version_number in workflow list and single-workflow responses
- GET /api/v1/projects/{id}/workflows (published_version_number population)
"""

import pytest
from httpx import AsyncClient

from tests.helpers.workflow import create_minimal_workflow_definition


@pytest.mark.asyncio
async def test_list_versions_returns_paginated_response(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Version list endpoint returns pagination fields (next, prev, total)."""
    defn = create_minimal_workflow_definition(name="list-test", description="v1", activity_id="task1")
    create_resp = await jwt_client.post(
        "/api/v1/workflows",
        json={"name": "version-list-test", "workflow_definition": defn, "project_id": str(test_project_id)},
    )
    assert create_resp.status_code == 201
    workflow_id = create_resp.json()["id"]

    response = await jwt_client.get(f"/api/v1/workflows/{workflow_id}/versions")
    assert response.status_code == 200

    body = response.json()
    assert "resources" in body
    assert "next" in body
    assert "prev" in body
    assert len(body["resources"]) == 1
    assert body["resources"][0]["version"] == 1


@pytest.mark.asyncio
async def test_list_versions_with_limit(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Version list respects limit parameter and returns cursor for next page."""
    defn = create_minimal_workflow_definition(name="paginate-test", description="v1", activity_id="task1")
    create_resp = await jwt_client.post(
        "/api/v1/workflows",
        json={"name": "version-paginate-test", "workflow_definition": defn, "project_id": str(test_project_id)},
    )
    assert create_resp.status_code == 201
    workflow_id = create_resp.json()["id"]

    for i in range(2, 5):
        defn_next = create_minimal_workflow_definition(
            name="paginate-test", description=f"v{i}", activity_id=f"task{i}"
        )
        resp = await jwt_client.patch(
            f"/api/v1/workflows/{workflow_id}",
            json={"workflow_definition": defn_next, "change_description": f"Version {i}"},
        )
        assert resp.status_code == 200

    response = await jwt_client.get(f"/api/v1/workflows/{workflow_id}/versions?limit=2")
    assert response.status_code == 200

    body = response.json()
    assert len(body["resources"]) == 2
    assert body["next"] is not None

    next_response = await jwt_client.get(f"/api/v1/workflows/{workflow_id}/versions?limit=2&cursor={body['next']}")
    assert next_response.status_code == 200

    next_body = next_response.json()
    assert len(next_body["resources"]) == 2
    assert next_body["prev"] is not None


@pytest.mark.asyncio
async def test_list_versions_includes_status_and_creator(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Version list includes the computed status field and a resolved created_by."""
    defn = create_minimal_workflow_definition(name="status-test", description="v1", activity_id="task1")
    create_resp = await jwt_client.post(
        "/api/v1/workflows",
        json={"name": "version-status-test", "workflow_definition": defn, "project_id": str(test_project_id)},
    )
    assert create_resp.status_code == 201
    workflow_id = create_resp.json()["id"]

    response = await jwt_client.get(f"/api/v1/workflows/{workflow_id}/versions")
    assert response.status_code == 200

    version = response.json()["resources"][0]
    assert version["status"] == "draft"
    assert isinstance(version["created_by"], dict)
    assert version["created_by"]["id"]
    assert version["created_by"]["name"]


@pytest.mark.asyncio
async def test_list_versions_with_include_total(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Version list returns total count when include_total=true."""
    defn = create_minimal_workflow_definition(name="total-test", description="v1", activity_id="task1")
    create_resp = await jwt_client.post(
        "/api/v1/workflows",
        json={"name": "version-total-test", "workflow_definition": defn, "project_id": str(test_project_id)},
    )
    assert create_resp.status_code == 201
    workflow_id = create_resp.json()["id"]

    response = await jwt_client.get(f"/api/v1/workflows/{workflow_id}/versions?include_total=true")
    assert response.status_code == 200

    body = response.json()
    assert body["total"] == 1


@pytest.mark.asyncio
async def test_list_versions_default_sort_is_created_at_desc(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Default sort is -created_at (newest first)."""
    defn = create_minimal_workflow_definition(name="sort-test", description="v1", activity_id="task1")
    create_resp = await jwt_client.post(
        "/api/v1/workflows",
        json={"name": "version-sort-test", "workflow_definition": defn, "project_id": str(test_project_id)},
    )
    assert create_resp.status_code == 201
    workflow_id = create_resp.json()["id"]

    defn_v2 = create_minimal_workflow_definition(name="sort-test", description="v2", activity_id="task2")
    await jwt_client.patch(
        f"/api/v1/workflows/{workflow_id}",
        json={"workflow_definition": defn_v2, "change_description": "Version 2"},
    )

    response = await jwt_client.get(f"/api/v1/workflows/{workflow_id}/versions")
    assert response.status_code == 200

    versions = response.json()["resources"]
    assert versions[0]["version"] > versions[1]["version"]


@pytest.mark.asyncio
async def test_published_version_number_in_workflow_response(jwt_client: AsyncClient, test_project_id: str) -> None:
    """published_version_number is populated in single-workflow responses after publish."""
    defn = create_minimal_workflow_definition(name="pub-num-test", description="v1", activity_id="task1")
    create_resp = await jwt_client.post(
        "/api/v1/workflows",
        json={"name": "pub-version-num-test", "workflow_definition": defn, "project_id": str(test_project_id)},
    )
    assert create_resp.status_code == 201
    workflow_id = create_resp.json()["id"]

    publish_resp = await jwt_client.post(
        f"/api/v1/workflows/{workflow_id}/versions/1/publish",
        json={"name": "v1-published"},
    )
    assert publish_resp.status_code == 200
    pub_data = publish_resp.json()
    assert pub_data["published_version_number"] is not None

    get_resp = await jwt_client.get(f"/api/v1/workflows/{workflow_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["published_version_number"] is not None


@pytest.mark.asyncio
async def test_published_version_number_in_workflow_list(jwt_client: AsyncClient, test_project_id: str) -> None:
    """published_version_number is populated in workflow list responses."""
    defn = create_minimal_workflow_definition(name="list-pub-num", description="v1", activity_id="task1")
    create_resp = await jwt_client.post(
        "/api/v1/workflows",
        json={"name": "list-pub-num-test", "workflow_definition": defn, "project_id": str(test_project_id)},
    )
    assert create_resp.status_code == 201
    workflow_id = create_resp.json()["id"]

    await jwt_client.post(
        f"/api/v1/workflows/{workflow_id}/versions/1/publish",
        json={"name": "v1-pub"},
    )

    list_resp = await jwt_client.get("/api/v1/workflows")
    assert list_resp.status_code == 200

    workflow = next(w for w in list_resp.json()["resources"] if w["id"] == workflow_id)
    assert workflow["published_version_number"] is not None


@pytest.mark.asyncio
async def test_published_version_number_in_project_workflow_list(jwt_client: AsyncClient, test_project_id: str) -> None:
    """published_version_number is populated in project-scoped workflow list."""
    defn = create_minimal_workflow_definition(name="proj-pub-num", description="v1", activity_id="task1")
    create_resp = await jwt_client.post(
        "/api/v1/workflows",
        json={"name": "proj-pub-num-test", "workflow_definition": defn, "project_id": str(test_project_id)},
    )
    assert create_resp.status_code == 201
    workflow_id = create_resp.json()["id"]

    await jwt_client.post(
        f"/api/v1/workflows/{workflow_id}/versions/1/publish",
        json={"name": "v1-pub"},
    )

    list_resp = await jwt_client.get(f"/api/v1/projects/{test_project_id}/workflows")
    assert list_resp.status_code == 200

    workflow = next(w for w in list_resp.json()["resources"] if w["id"] == workflow_id)
    assert workflow["published_version_number"] is not None


@pytest.mark.asyncio
async def test_workflow_version_name_in_execution(jwt_client: AsyncClient, test_project_id: str) -> None:
    """workflow_version_name field exists in WorkflowRead model."""
    defn = create_minimal_workflow_definition(name="exec-name-test", description="v1", activity_id="task1")
    create_resp = await jwt_client.post(
        "/api/v1/workflows",
        json={"name": "exec-name-test", "workflow_definition": defn, "project_id": str(test_project_id)},
    )
    assert create_resp.status_code == 201
    workflow_id = create_resp.json()["id"]

    get_resp = await jwt_client.get(f"/api/v1/workflows/{workflow_id}")
    assert get_resp.status_code == 200
    version = get_resp.json()["version"]
    assert "name" in version
