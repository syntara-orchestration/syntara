"""Contract tests for workflow version publish/unpublish endpoints.

Tests for POST /api/v1/workflows/{id}/versions/{version}/publish
and POST /api/v1/workflows/{id}/unpublish.
"""

from typing import Any

import pytest
from httpx import AsyncClient

from tests.helpers.workflow import create_minimal_workflow_definition


def _create_invalid_workflow_definition() -> dict[str, Any]:
    """Create a workflow definition with validation errors (orphaned node)."""
    return {
        "schema_version": "2.0.0",
        "name": "invalid-test",
        "description": "Test",
        "triggers": [{"id": "trigger_manual", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {
                "id": "task1",
                "name": "Task 1",
                "type": "script",
                "parameters": {"language": "python", "code": "print('hello')"},
            },
            {
                "id": "orphaned_task",
                "name": "Orphaned Task",
                "type": "script",
                "parameters": {"language": "python", "code": "print('orphaned')"},
            },
        ],
        "edges": [{"from": "trigger_manual", "to": "task1"}],
    }


@pytest.mark.asyncio
async def test_publish_version_returns_200(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Test publishing a workflow version.

    Expected: 200 with workflow including published_version_id
    """
    workflow = {
        "name": "publish-test",
        "project_id": test_project_id,
        "workflow_definition": create_minimal_workflow_definition(
            name="publish-test", description="Test", activity_id="task1"
        ),
    }

    create_resp = await jwt_client.post("/api/v1/workflows", json=workflow)
    assert create_resp.status_code == 201
    workflow_id = create_resp.json()["id"]
    assert create_resp.json()["is_enabled"] is False
    assert create_resp.json()["published_version_id"] is None

    response = await jwt_client.post(
        f"/api/v1/workflows/{workflow_id}/versions/1/publish",
        json={},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_enabled"] is True
    assert data["published_version_id"] is not None
    assert data["version"]["status"] == "published"
    assert data["warning"] == ""


@pytest.mark.asyncio
async def test_publish_version_with_name(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Test publishing with a name.

    Expected: 200 with name set on the version
    """
    workflow = {
        "name": "publish-named-test",
        "project_id": test_project_id,
        "workflow_definition": create_minimal_workflow_definition(
            name="publish-named", description="Test", activity_id="task1"
        ),
    }

    create_resp = await jwt_client.post("/api/v1/workflows", json=workflow)
    workflow_id = create_resp.json()["id"]

    response = await jwt_client.post(
        f"/api/v1/workflows/{workflow_id}/versions/1/publish",
        json={"name": "v1.0 Release"},
    )

    assert response.status_code == 200
    assert response.json()["published_version_id"] is not None
    assert response.json()["version"]["name"] == "v1.0 Release"
    assert response.json()["version"]["status"] == "published"


@pytest.mark.asyncio
async def test_publish_version_with_change_description(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Test publishing with a change_description.

    Expected: 200 with change_description set on the version
    """
    workflow = {
        "name": "publish-desc-test",
        "project_id": test_project_id,
        "workflow_definition": create_minimal_workflow_definition(
            name="publish-desc", description="Test", activity_id="task1"
        ),
    }

    create_resp = await jwt_client.post("/api/v1/workflows", json=workflow)
    workflow_id = create_resp.json()["id"]

    response = await jwt_client.post(
        f"/api/v1/workflows/{workflow_id}/versions/1/publish",
        json={"name": "v1.0", "change_description": "Initial release"},
    )

    assert response.status_code == 200
    assert response.json()["published_version_id"] is not None
    assert response.json()["version"]["name"] == "v1.0"
    assert response.json()["version"]["change_description"] == "Initial release"
    assert response.json()["version"]["status"] == "published"


@pytest.mark.asyncio
async def test_publish_switches_pointer(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Test that publishing a new version updates the published_version_id pointer.

    No-copy publish: pointer moves to the target version in-place.
    """
    workflow = {
        "name": "publish-demote-test",
        "project_id": test_project_id,
        "workflow_definition": create_minimal_workflow_definition(
            name="publish-demote", description="Test v1", activity_id="task1"
        ),
    }

    create_resp = await jwt_client.post("/api/v1/workflows", json=workflow)
    workflow_id = create_resp.json()["id"]

    # Publish v1 — pointer update, no copy created
    pub1_resp = await jwt_client.post(f"/api/v1/workflows/{workflow_id}/versions/1/publish", json={})
    assert pub1_resp.status_code == 200
    first_published_id = pub1_resp.json()["published_version_id"]

    # v1 should be published (in-place update)
    v1_resp = await jwt_client.get(f"/api/v1/workflows/{workflow_id}/versions/1")
    assert v1_resp.status_code == 200
    assert v1_resp.json()["status"] == "published"

    # Update creates v2 (draft)
    await jwt_client.patch(
        f"/api/v1/workflows/{workflow_id}",
        json={
            "workflow_definition": create_minimal_workflow_definition(
                name="publish-demote", description="Test v2", activity_id="task2"
            ),
        },
    )

    # Publish v2 — pointer switches to v2, v1 becomes previously_published
    response = await jwt_client.post(
        f"/api/v1/workflows/{workflow_id}/versions/2/publish",
        json={},
    )

    assert response.status_code == 200
    assert response.json()["published_version_id"] is not None
    assert response.json()["published_version_id"] != first_published_id

    # v1 should now be previously_published
    v1_after = await jwt_client.get(f"/api/v1/workflows/{workflow_id}/versions/1")
    assert v1_after.status_code == 200
    assert v1_after.json()["status"] == "previously_published"


@pytest.mark.asyncio
async def test_unpublish_workflow(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Test unpublishing a workflow.

    Expected: 200 with is_enabled=False, published_version_id=None
    """
    workflow = {
        "name": "unpublish-test",
        "project_id": test_project_id,
        "workflow_definition": create_minimal_workflow_definition(
            name="unpublish-test", description="Test", activity_id="task1"
        ),
    }

    create_resp = await jwt_client.post("/api/v1/workflows", json=workflow)
    workflow_id = create_resp.json()["id"]

    # Publish v1
    await jwt_client.post(f"/api/v1/workflows/{workflow_id}/versions/1/publish", json={})

    # Unpublish
    response = await jwt_client.post(f"/api/v1/workflows/{workflow_id}/unpublish")

    assert response.status_code == 200
    assert response.json()["is_enabled"] is False
    assert response.json()["published_version_id"] is None


@pytest.mark.asyncio
async def test_unpublish_when_not_published_returns_400(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Test unpublishing a workflow that is not published.

    Expected: 400 Bad Request
    """
    workflow = {
        "name": "unpublish-not-published",
        "project_id": test_project_id,
        "workflow_definition": create_minimal_workflow_definition(
            name="unpublish-not-published", description="Test", activity_id="task1"
        ),
    }

    create_resp = await jwt_client.post("/api/v1/workflows", json=workflow)
    workflow_id = create_resp.json()["id"]

    response = await jwt_client.post(f"/api/v1/workflows/{workflow_id}/unpublish")

    assert response.status_code == 400
    assert response.json()["code"] == "WORKFLOW_NOT_PUBLISHED"


@pytest.mark.asyncio
async def test_publish_nonexistent_version_returns_404(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Test publishing a version that does not exist.

    Expected: 404 Not Found
    """
    workflow = {
        "name": "publish-nonexistent-version",
        "project_id": test_project_id,
        "workflow_definition": create_minimal_workflow_definition(
            name="publish-nonexistent", description="Test", activity_id="task1"
        ),
    }

    create_resp = await jwt_client.post("/api/v1/workflows", json=workflow)
    workflow_id = create_resp.json()["id"]

    response = await jwt_client.post(
        f"/api/v1/workflows/{workflow_id}/versions/99/publish",
        json={},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_version_list_includes_status(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Test that version list includes status field.

    Expected: Versions include status (draft/published)
    """
    workflow = {
        "name": "version-status-list",
        "project_id": test_project_id,
        "workflow_definition": create_minimal_workflow_definition(
            name="version-status-list", description="Test", activity_id="task1"
        ),
    }

    create_resp = await jwt_client.post("/api/v1/workflows", json=workflow)
    workflow_id = create_resp.json()["id"]

    # Publish v1 (in-place, no copy)
    await jwt_client.post(f"/api/v1/workflows/{workflow_id}/versions/1/publish", json={})

    # Update creates v2 (draft)
    await jwt_client.patch(
        f"/api/v1/workflows/{workflow_id}",
        json={
            "workflow_definition": create_minimal_workflow_definition(
                name="version-status-list", description="v2", activity_id="task2"
            ),
        },
    )

    # List versions: v1 (published, in-place), v2 (draft from update)
    response = await jwt_client.get(f"/api/v1/workflows/{workflow_id}/versions")
    assert response.status_code == 200

    versions = response.json()["resources"]
    by_ver = {v["version"]: v for v in versions}

    assert by_ver[1]["status"] == "published"
    assert by_ver[2]["status"] == "draft"


@pytest.mark.asyncio
async def test_create_workflow_defaults_to_unpublished(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Test new workflows start unpublished.

    Expected: 201 with is_enabled=False, published_version_id=None
    """
    workflow = {
        "name": "default-unpublished",
        "project_id": test_project_id,
        "workflow_definition": create_minimal_workflow_definition(
            name="default-unpublished", description="Test", activity_id="task1"
        ),
    }

    response = await jwt_client.post("/api/v1/workflows", json=workflow)

    assert response.status_code == 201
    assert response.json()["is_enabled"] is False
    assert response.json()["published_version_id"] is None


@pytest.mark.asyncio
async def test_republish_previously_published_version(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Test re-publishing a version switches the pointer back.

    No-copy: publish v1 -> publish v2 (pointer switches) -> publish v1 again (pointer switches back)
    """
    workflow = {
        "name": "republish-test",
        "project_id": test_project_id,
        "workflow_definition": create_minimal_workflow_definition(
            name="republish", description="Test v1", activity_id="task1"
        ),
    }

    create_resp = await jwt_client.post("/api/v1/workflows", json=workflow)
    workflow_id = create_resp.json()["id"]

    # Publish v1 (in-place)
    await jwt_client.post(f"/api/v1/workflows/{workflow_id}/versions/1/publish", json={})

    # PATCH creates v2 (draft)
    await jwt_client.patch(
        f"/api/v1/workflows/{workflow_id}",
        json={
            "workflow_definition": create_minimal_workflow_definition(
                name="republish", description="Test v2", activity_id="task2"
            ),
        },
    )

    # Publish v2 (in-place). v1 becomes previously_published.
    await jwt_client.post(f"/api/v1/workflows/{workflow_id}/versions/2/publish", json={})

    # Re-publish v1 (in-place). v2 becomes previously_published.
    response = await jwt_client.post(
        f"/api/v1/workflows/{workflow_id}/versions/1/publish",
        json={"name": "v1-hotfix"},
    )

    assert response.status_code == 200
    assert response.json()["published_version_id"] is not None
    assert response.json()["version"]["status"] == "published"
    assert response.json()["version"]["name"] == "v1-hotfix"

    # v2 should be previously_published
    v2_resp = await jwt_client.get(f"/api/v1/workflows/{workflow_id}/versions/2")
    assert v2_resp.json()["status"] == "previously_published"


@pytest.mark.asyncio
async def test_publish_with_unsaved_step_includes_all_nodes(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Publish with unsaved canvas changes must include those changes.

    Reproduces the user flow:
    1. Create workflow with manual trigger + step1 -> save (v1)
    2. Add step2 -> save (update creates v2)
    3. Add step3 -> do NOT save -> publish with workflow_definition, title, and description
    4. Published version must contain trigger + step1 + step2 + step3
    5. Last saved draft (v2) must still only have trigger + step1 + step2
    """

    def _build_definition(node_ids: list[str]) -> dict[str, object]:
        nodes = [
            {
                "id": nid,
                "name": nid,
                "type": "script",
                "parameters": {"language": "python", "code": f'print("{nid}")'},
            }
            for nid in node_ids
        ]
        edges = [{"from": "trigger_manual", "to": node_ids[0]}]
        for i in range(len(node_ids) - 1):
            edges.append({"from": node_ids[i], "to": node_ids[i + 1]})
        return {
            "schema_version": "2.0.0",
            "name": "unsaved-step-test",
            "description": "test",
            "triggers": [{"id": "trigger_manual", "type": "manual_trigger", "parameters": {}}],
            "nodes": nodes,
            "edges": edges,
        }

    # Step 1: create with trigger + step1
    create_resp = await jwt_client.post(
        "/api/v1/workflows",
        json={
            "name": "unsaved-step-publish",
            "project_id": test_project_id,
            "workflow_definition": _build_definition(["step1"]),
        },
    )
    assert create_resp.status_code == 201
    workflow_id = create_resp.json()["id"]
    assert create_resp.json()["current_version"] == 1

    # Step 2: add step2 -> save
    update_resp = await jwt_client.patch(
        f"/api/v1/workflows/{workflow_id}",
        json={"workflow_definition": _build_definition(["step1", "step2"])},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["current_version"] == 2

    # Step 3: add step3 -> publish directly (don't save) with title and description
    unsaved_defn = _build_definition(["step1", "step2", "step3"])
    pub_resp = await jwt_client.post(
        f"/api/v1/workflows/{workflow_id}/versions/2/publish",
        json={
            "name": "Production Release v1.0",
            "change_description": "Added step3 for post-processing",
            "workflow_definition": unsaved_defn,
        },
    )
    assert pub_resp.status_code == 200
    pub_data = pub_resp.json()

    # With no-copy publish + workflow_definition, a new version (v3) is
    # created with the unsaved changes, then published in-place.
    assert pub_data["published_version_id"] is not None
    assert pub_data["version"]["status"] == "published"
    assert pub_data["version"]["name"] == "Production Release v1.0"
    assert pub_data["version"]["change_description"] == "Added step3 for post-processing"

    published_node_ids = [n["id"] for n in pub_data["version"]["workflow_definition"]["nodes"]]
    assert published_node_ids == ["step1", "step2", "step3"]

    # v2 (last saved draft) still has only step1 + step2
    v2_resp = await jwt_client.get(f"/api/v1/workflows/{workflow_id}/versions/2")
    assert v2_resp.status_code == 200
    v2_node_ids = [n["id"] for n in v2_resp.json()["workflow_definition"]["nodes"]]
    assert v2_node_ids == ["step1", "step2"]

    # v1 still has only step1
    v1_resp = await jwt_client.get(f"/api/v1/workflows/{workflow_id}/versions/1")
    assert v1_resp.status_code == 200
    v1_node_ids = [n["id"] for n in v1_resp.json()["workflow_definition"]["nodes"]]
    assert v1_node_ids == ["step1"]


@pytest.mark.asyncio
async def test_publish_blocked_for_definition_with_errors(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Test that publishing is blocked with 409 when the saved definition has validation errors.

    Expected: 409 Conflict with WORKFLOW_PUBLISH_VALIDATION_ERROR code
    """
    create_resp = await jwt_client.post(
        "/api/v1/workflows",
        json={
            "name": "publish-blocked-errors",
            "project_id": test_project_id,
            "workflow_definition": _create_invalid_workflow_definition(),
        },
    )
    assert create_resp.status_code == 201
    workflow_id = create_resp.json()["id"]
    assert create_resp.json()["has_validation_issues"] is True

    response = await jwt_client.post(
        f"/api/v1/workflows/{workflow_id}/versions/1/publish",
        json={},
    )

    assert response.status_code == 409
    data = response.json()
    assert data["code"] == "WORKFLOW_PUBLISH_VALIDATION_ERROR"
    assert "validation_result" in data
    assert data["validation_result"]["error_count"] > 0


@pytest.mark.asyncio
async def test_publish_blocked_with_inline_invalid_definition(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Test that publishing with an inline invalid definition is blocked with 409.

    Expected: 409 Conflict even when workflow_definition is provided in publish request
    """
    create_resp = await jwt_client.post(
        "/api/v1/workflows",
        json={
            "name": "publish-blocked-inline",
            "project_id": test_project_id,
            "workflow_definition": create_minimal_workflow_definition(
                name="publish-blocked-inline", description="Test", activity_id="task1"
            ),
        },
    )
    assert create_resp.status_code == 201
    workflow_id = create_resp.json()["id"]

    response = await jwt_client.post(
        f"/api/v1/workflows/{workflow_id}/versions/1/publish",
        json={"workflow_definition": _create_invalid_workflow_definition()},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "WORKFLOW_PUBLISH_VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_publish_blocked_preserves_existing_published_version(
    jwt_client: AsyncClient, test_project_id: str
) -> None:
    """Test that a blocked publish does not change the existing published_version_id.

    Expected: Previous published version remains active and unaffected
    """
    create_resp = await jwt_client.post(
        "/api/v1/workflows",
        json={
            "name": "publish-preserves-published",
            "project_id": test_project_id,
            "workflow_definition": create_minimal_workflow_definition(
                name="publish-preserves", description="Test v1", activity_id="task1"
            ),
        },
    )
    assert create_resp.status_code == 201
    workflow_id = create_resp.json()["id"]

    pub_resp = await jwt_client.post(
        f"/api/v1/workflows/{workflow_id}/versions/1/publish",
        json={},
    )
    assert pub_resp.status_code == 200
    original_published_id = pub_resp.json()["published_version_id"]
    assert original_published_id is not None

    update_resp = await jwt_client.patch(
        f"/api/v1/workflows/{workflow_id}",
        json={"workflow_definition": _create_invalid_workflow_definition()},
    )
    assert update_resp.status_code == 200
    new_version = update_resp.json()["current_version"]

    response = await jwt_client.post(
        f"/api/v1/workflows/{workflow_id}/versions/{new_version}/publish",
        json={},
    )
    assert response.status_code == 409

    get_resp = await jwt_client.get(f"/api/v1/workflows/{workflow_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["published_version_id"] == original_published_id
    assert get_resp.json()["is_enabled"] is True

    # v1 was published in-place (no copy)
    v1_resp = await jwt_client.get(f"/api/v1/workflows/{workflow_id}/versions/1")
    assert v1_resp.status_code == 200
    assert v1_resp.json()["status"] == "published"


@pytest.mark.asyncio
async def test_publish_with_script_node_denied_returns_403(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Atomic save-and-publish with script nodes returns 403 when script:edit is denied.

    Regression test for AAP-87589 finding #1 (publish bypass).
    """
    from unittest.mock import patch

    from syntara.authz.engine import AuthzResult

    script_definition = {
        "schema_version": "2.0.0",
        "triggers": [{"id": "trigger_manual", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {
                "id": "script1",
                "type": "script",
                "parameters": {"language": "python", "code": "print('hello')"},
            }
        ],
        "edges": [{"from": "trigger_manual", "to": "script1"}],
    }

    workflow = {
        "name": "script-publish-test",
        "project_id": test_project_id,
        "workflow_definition": create_minimal_workflow_definition(
            name="script-publish", description="Test", activity_id="task1"
        ),
    }
    create_resp = await jwt_client.post("/api/v1/workflows", json=workflow)
    assert create_resp.status_code == 201
    workflow_id = create_resp.json()["id"]

    async def _deny_script_edit(_db, _evaluator, request) -> AuthzResult:
        if request.resource_type == "script" and request.action == "edit":
            return AuthzResult(
                allowed=False,
                denied=True,
                matched_policy="",
                denial_reason="test deny",
                denied_by="",
                effective_policies=[],
            )
        return AuthzResult(
            allowed=True,
            denied=False,
            matched_policy="",
            denial_reason="",
            denied_by="",
            effective_policies=[],
        )

    with patch("syntara.workflows.services.workflow_service.authorize", side_effect=_deny_script_edit):
        response = await jwt_client.post(
            f"/api/v1/workflows/{workflow_id}/versions/1/publish",
            json={"workflow_definition": script_definition},
        )

    assert response.status_code == 403
