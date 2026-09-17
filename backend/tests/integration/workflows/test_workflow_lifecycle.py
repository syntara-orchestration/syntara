"""End-to-end integration test for workflow lifecycle.

Tests the complete workflow management lifecycle:
1. Create workflow
2. Create versions (via PATCH)
3. List versions
4. Get specific version
5. Update workflow metadata
6. Soft delete workflow
7. Verify soft delete prevents access
"""

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from tests.helpers.workflow import (
    create_minimal_workflow_definition,
    create_workflow_definition_with_activities,
)


@pytest.mark.asyncio
async def test_workflow_complete_lifecycle(jwt_client: AsyncClient, test_project_id: UUID) -> None:  # noqa: PLR0915
    """Test complete workflow lifecycle from creation to deletion.

    This test verifies that all workflow operations work together correctly:
    - Creating a workflow automatically creates version 1
    - PATCH with workflow_definition creates new versions
    - Version history is maintained correctly
    - Metadata updates don't create versions
    - Soft delete prevents future access
    """
    # Step 1: Create workflow
    create_payload = {
        "name": "lifecycle-test-workflow",
        "description": "Testing complete lifecycle",
        "project_id": str(test_project_id),
        "labels": {"env": "test", "purpose": "integration"},
        "workflow_definition": create_minimal_workflow_definition(
            name="lifecycle-test",
            description="Initial version",
            activity_id="initial_activity",
        ),
    }

    create_response = await jwt_client.post(
        "/api/v1/workflows",
        json=create_payload,
    )
    assert create_response.status_code == 201
    workflow = create_response.json()
    workflow_id = workflow["id"]

    assert workflow["name"] == "lifecycle-test-workflow"
    assert workflow["current_version"] == 1
    assert workflow["is_enabled"] is False
    assert workflow["labels"] == {"env": "test", "purpose": "integration"}

    # Note: POST response does not include version data
    # Use GET to retrieve version data
    get_workflow_response = await jwt_client.get(f"/api/v1/workflows/{workflow_id}")
    assert get_workflow_response.status_code == 200
    workflow_with_version = get_workflow_response.json()

    # Verify workflow includes version data (WorkflowWithVersionResponse)
    assert "version" in workflow_with_version
    assert workflow_with_version["version"]["version"] == 1
    version_def = workflow_with_version["version"]["workflow_definition"]
    assert version_def["schema_version"] == "2.0.0"
    assert version_def["name"] == "lifecycle-test"

    # Step 2: Create version 2 via PATCH
    update_v2_payload = {
        "workflow_definition": create_minimal_workflow_definition(
            name="lifecycle-test",
            description="Version 2 with new activity",
            activity_id="activity_1",
        ),
        "change_description": "Added activity_1",
    }

    update_v2_response = await jwt_client.patch(
        f"/api/v1/workflows/{workflow_id}",
        json=update_v2_payload,
    )
    assert update_v2_response.status_code == 200
    workflow_v2 = update_v2_response.json()

    assert workflow_v2["current_version"] == 2
    assert workflow_v2["name"] == "lifecycle-test-workflow"  # Name unchanged
    assert "version" in workflow_v2
    assert workflow_v2["version"]["version"] == 2
    v2_def = workflow_v2["version"]["workflow_definition"]
    assert v2_def["nodes"][0]["id"] == "activity_1"

    # Step 3: Create version 3 via PATCH
    update_v3_payload = {
        "workflow_definition": create_workflow_definition_with_activities(
            name="lifecycle-test",
            description="Version 3 with two activities",
            activities=[
                {
                    "id": "activity_1",
                    "name": "Activity 1",
                    "type": "script",
                    "parameters": {
                        "language": "python",
                        "code": "print('activity 1')",
                    },
                },
                {
                    "id": "activity_2",
                    "name": "Activity 2",
                    "type": "script",
                    "parameters": {
                        "language": "python",
                        "code": "print('activity 2')",
                    },
                },
            ],
        ),
        "change_description": "Added activity_2",
    }

    update_v3_response = await jwt_client.patch(
        f"/api/v1/workflows/{workflow_id}",
        json=update_v3_payload,
    )
    assert update_v3_response.status_code == 200
    workflow_v3 = update_v3_response.json()

    assert workflow_v3["current_version"] == 3
    assert workflow_v3["version"]["version"] == 3
    v3_def = workflow_v3["version"]["workflow_definition"]
    assert len(v3_def["nodes"]) == 2
    assert v3_def["nodes"][1]["id"] == "activity_2"

    # Step 4: List all versions
    list_versions_response = await jwt_client.get(
        f"/api/v1/workflows/{workflow_id}/versions",
    )
    assert list_versions_response.status_code == 200
    versions_data = list_versions_response.json()

    assert "resources" in versions_data
    versions = versions_data["resources"]
    assert len(versions) == 3

    # Verify versions are ordered DESC (newest first)
    assert versions[0]["version"] == 3
    assert versions[1]["version"] == 2
    assert versions[2]["version"] == 1

    # Step 5: Get specific version (version 2)
    get_v2_response = await jwt_client.get(
        f"/api/v1/workflows/{workflow_id}/versions/2",
    )
    assert get_v2_response.status_code == 200
    v2_data = get_v2_response.json()

    assert v2_data["version"] == 2
    assert v2_data["workflow_id"] == workflow_id
    v2_retrieved_def = v2_data["workflow_definition"]
    assert v2_retrieved_def["nodes"][0]["id"] == "activity_1"
    assert len(v2_retrieved_def["nodes"]) == 1
    assert v2_data["change_description"] == "Added activity_1"

    # Step 6: Update metadata only (should NOT create new version)
    metadata_update_payload = {
        "description": "Updated description",
        "labels": {"env": "production", "purpose": "integration", "team": "platform"},
    }

    metadata_update_response = await jwt_client.patch(
        f"/api/v1/workflows/{workflow_id}",
        json=metadata_update_payload,
    )
    assert metadata_update_response.status_code == 200
    workflow_metadata = metadata_update_response.json()

    # Version should still be 3 (no workflow_definition in update)
    assert workflow_metadata["current_version"] == 3
    assert workflow_metadata["description"] == "Updated description"
    assert workflow_metadata["labels"] == {
        "env": "production",
        "purpose": "integration",
        "team": "platform",
    }
    assert workflow_metadata["is_enabled"] is False

    # Verify GET returns updated metadata
    get_workflow_response = await jwt_client.get(
        f"/api/v1/workflows/{workflow_id}",
    )
    assert get_workflow_response.status_code == 200
    workflow_updated = get_workflow_response.json()

    assert workflow_updated["is_enabled"] is False
    assert workflow_updated["description"] == "Updated description"
    assert workflow_updated["current_version"] == 3

    # Step 7: Soft delete workflow
    delete_response = await jwt_client.delete(
        f"/api/v1/workflows/{workflow_id}",
    )
    assert delete_response.status_code == 204

    # Step 8: Verify soft delete prevents access
    get_deleted_response = await jwt_client.get(
        f"/api/v1/workflows/{workflow_id}",
    )
    assert get_deleted_response.status_code == 404

    # Verify workflow not in list
    list_response = await jwt_client.get("/api/v1/workflows")
    assert list_response.status_code == 200
    workflows = list_response.json()["resources"]

    # Workflow should not appear in list (soft deleted)
    workflow_ids = [w["id"] for w in workflows]
    assert workflow_id not in workflow_ids

    # Verify versions endpoint returns 404 for deleted workflow
    versions_deleted_response = await jwt_client.get(
        f"/api/v1/workflows/{workflow_id}/versions",
    )
    assert versions_deleted_response.status_code == 404


@pytest.mark.asyncio
async def test_workflow_version_immutability(jwt_client: AsyncClient, test_project_id: UUID) -> None:
    """Test that workflow versions are read-only and immutable."""
    # Create workflow
    create_payload = {
        "name": "immutable-test",
        "project_id": str(test_project_id),
        "workflow_definition": create_minimal_workflow_definition(
            name="immutable-test",
            description="Immutability test",
            activity_id="immutable_activity",
        ),
    }

    create_response = await jwt_client.post(
        "/api/v1/workflows",
        json=create_payload,
    )
    assert create_response.status_code == 201
    workflow = create_response.json()
    workflow_id = workflow["id"]

    # Create version 2
    update_payload = {
        "workflow_definition": create_minimal_workflow_definition(
            name="immutable-test",
            description="Immutability test version 2",
            activity_id="activity_1",
        ),
    }

    await jwt_client.patch(f"/api/v1/workflows/{workflow_id}", json=update_payload)

    # Get version 1
    v1_response = await jwt_client.get(
        f"/api/v1/workflows/{workflow_id}/versions/1",
    )
    assert v1_response.status_code == 200
    v1_original = v1_response.json()

    # Get version 1 again to verify it hasn't changed
    v1_again_response = await jwt_client.get(
        f"/api/v1/workflows/{workflow_id}/versions/1",
    )
    assert v1_again_response.status_code == 200
    v1_again = v1_again_response.json()

    # Verify version 1 is unchanged
    assert v1_original["workflow_definition"] == v1_again["workflow_definition"]
    assert v1_original["created_at"] == v1_again["created_at"]
    assert v1_original["version"] == 1

    # Verify current version is 2 but version 1 still accessible
    workflow_response = await jwt_client.get(f"/api/v1/workflows/{workflow_id}")
    assert workflow_response.status_code == 200
    current_workflow = workflow_response.json()

    assert current_workflow["current_version"] == 2
    current_def = current_workflow["version"]["workflow_definition"]
    assert current_def["nodes"][0]["id"] == "activity_1"

    # But version 1 still has original definition
    v1_def = v1_again["workflow_definition"]
    assert v1_def["nodes"][0]["id"] == "immutable_activity"


@pytest.mark.asyncio
async def test_patch_workflow_metadata_bumps_updated_at(jwt_client: AsyncClient, test_project_id: UUID) -> None:
    """PATCH workflow metadata must bump updated_at via the global before_flush hook."""
    create_payload = {
        "name": "updated-at-metadata-test",
        "description": "Original description",
        "project_id": str(test_project_id),
        "workflow_definition": create_minimal_workflow_definition(
            name="updated-at-metadata-test",
            description="Original description",
            activity_id="activity_1",
        ),
    }

    create_response = await jwt_client.post("/api/v1/workflows", json=create_payload)
    assert create_response.status_code == 201
    created = create_response.json()
    original_updated_at = created["updated_at"]

    patch_response = await jwt_client.patch(
        f"/api/v1/workflows/{created['id']}",
        json={"description": "Patched description"},
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert patched["description"] == "Patched description"
    assert patched["updated_at"] > original_updated_at


@pytest.mark.asyncio
async def test_update_version_metadata_via_patch(jwt_client: AsyncClient, test_project_id: UUID) -> None:
    """Test PATCH /workflows/{id}/versions/{version} updates metadata without affecting the definition."""
    create_payload = {
        "name": "version-metadata-test",
        "project_id": str(test_project_id),
        "workflow_definition": create_minimal_workflow_definition(
            name="version-metadata-test",
            description="Metadata test",
            activity_id="activity_1",
        ),
    }

    create_response = await jwt_client.post("/api/v1/workflows", json=create_payload)
    assert create_response.status_code == 201
    workflow_id = create_response.json()["id"]

    # PATCH version metadata — both fields
    patch_response = await jwt_client.patch(
        f"/api/v1/workflows/{workflow_id}/versions/1",
        json={"name": "Release 1.0", "change_description": "First release"},
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert patched["name"] == "Release 1.0"
    assert patched["change_description"] == "First release"
    assert patched["version"] == 1

    # Verify via GET that metadata persisted
    get_response = await jwt_client.get(f"/api/v1/workflows/{workflow_id}/versions/1")
    assert get_response.status_code == 200
    version_data = get_response.json()
    assert version_data["name"] == "Release 1.0"
    assert version_data["change_description"] == "First release"

    # Verify the workflow definition is unchanged
    assert version_data["workflow_definition"]["name"] == "version-metadata-test"


@pytest.mark.asyncio
async def test_update_version_metadata_partial(jwt_client: AsyncClient, test_project_id: UUID) -> None:
    """Test PATCH with only name leaves change_description unchanged."""
    create_payload = {
        "name": "partial-metadata-test",
        "project_id": str(test_project_id),
        "workflow_definition": create_minimal_workflow_definition(
            name="partial-metadata-test",
            description="Partial metadata test",
            activity_id="activity_1",
        ),
    }

    create_response = await jwt_client.post("/api/v1/workflows", json=create_payload)
    assert create_response.status_code == 201
    workflow_id = create_response.json()["id"]

    # Get the original change_description (set by service on create)
    get_response = await jwt_client.get(f"/api/v1/workflows/{workflow_id}/versions/1")
    original_description = get_response.json()["change_description"]

    # PATCH only name
    patch_response = await jwt_client.patch(
        f"/api/v1/workflows/{workflow_id}/versions/1",
        json={"name": "Named Version"},
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert patched["name"] == "Named Version"
    assert patched["change_description"] == original_description


@pytest.mark.asyncio
async def test_update_version_metadata_empty_body(jwt_client: AsyncClient, test_project_id: UUID) -> None:
    """Test PATCH with empty body returns 200 without modifying the record."""
    create_payload = {
        "name": "empty-body-test",
        "project_id": str(test_project_id),
        "workflow_definition": create_minimal_workflow_definition(
            name="empty-body-test",
            description="Empty body test",
            activity_id="activity_1",
        ),
    }

    create_response = await jwt_client.post("/api/v1/workflows", json=create_payload)
    assert create_response.status_code == 201
    workflow_id = create_response.json()["id"]

    patch_response = await jwt_client.patch(
        f"/api/v1/workflows/{workflow_id}/versions/1",
        json={},
    )
    assert patch_response.status_code == 200


@pytest.mark.asyncio
async def test_update_version_metadata_workflow_not_found(jwt_client: AsyncClient) -> None:
    """Test PATCH returns 404 for nonexistent workflow."""
    fake_id = str(uuid4())
    patch_response = await jwt_client.patch(
        f"/api/v1/workflows/{fake_id}/versions/1",
        json={"name": "x"},
    )
    assert patch_response.status_code == 404


@pytest.mark.asyncio
async def test_update_version_metadata_version_not_found(jwt_client: AsyncClient, test_project_id: UUID) -> None:
    """Test PATCH returns 404 for nonexistent version."""
    create_payload = {
        "name": "version-not-found-test",
        "project_id": str(test_project_id),
        "workflow_definition": create_minimal_workflow_definition(
            name="version-not-found-test",
            description="Version not found test",
            activity_id="activity_1",
        ),
    }

    create_response = await jwt_client.post("/api/v1/workflows", json=create_payload)
    assert create_response.status_code == 201
    workflow_id = create_response.json()["id"]

    patch_response = await jwt_client.patch(
        f"/api/v1/workflows/{workflow_id}/versions/999",
        json={"name": "x"},
    )
    assert patch_response.status_code == 404
