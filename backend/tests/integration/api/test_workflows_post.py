"""Contract tests for POST /api/v1/workflows endpoint.

These tests verify the API contract for creating workflows.
Tests MUST FAIL before implementation (TDD approach).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.helpers.workflow import create_minimal_workflow_definition
from tests.integration.helpers.error_data import assert_error_data

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.asyncio
async def test_post_workflow_valid_definition(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Test creating a workflow with valid definition.

    Expected: 201 Created with workflow object
    """
    valid_workflow = {
        "name": "test-workflow",
        "description": "A test workflow",
        "project_id": test_project_id,
        "workflow_definition": create_minimal_workflow_definition(
            name="test-workflow", description="A test workflow", activity_id="task1", activity_type="script_python"
        ),
    }

    response = await jwt_client.post("/api/v1/workflows", json=valid_workflow)

    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["name"] == "test-workflow"
    assert data["description"] == "A test workflow"
    assert "created_at" in data
    assert "current_version" in data
    assert data["current_version"] == 1
    assert data["is_enabled"] is False


@pytest.mark.asyncio
async def test_post_workflow_invalid_definition(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Test creating a workflow with invalid definition saves with validation issues.

    Expected: 201 Created with has_validation_issues=True (save always succeeds)
    """
    invalid_workflow = {
        "name": "invalid-workflow",
        "project_id": test_project_id,
        "workflow_definition": {
            "schema_version": "2.0.0",
            # Missing required 'triggers', 'nodes', and 'edges' fields
        },
    }

    response = await jwt_client.post("/api/v1/workflows", json=invalid_workflow)

    assert response.status_code == 201
    data = response.json()
    assert data["has_validation_issues"] is True


@pytest.mark.asyncio
async def test_post_workflow_missing_name(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Test creating a workflow without a name.

    Expected: 422 Unprocessable Entity (validation error)
    """
    workflow_without_name = {
        "project_id": test_project_id,
        "workflow_definition": create_minimal_workflow_definition(
            name="test",
            description="Test workflow",
        ),
    }

    response = await jwt_client.post("/api/v1/workflows", json=workflow_without_name)

    assert response.status_code == 422  # Pydantic validation errors return 422
    assert_error_data(
        response,
        error_type="https://api.example.com/errors/validation-error",
        title="Request Validation Error",
        detail="Validation failed: name: Field required",
        code="REQUEST_VALIDATION_ERROR",
        retryable=False,
    )


@pytest.mark.asyncio
async def test_post_workflow_missing_project_id(jwt_client: AsyncClient) -> None:
    """Test creating a workflow without project_id.

    Expected: 422 Unprocessable Entity (project_id is required)
    """
    workflow_without_project = {
        "name": "no-project-workflow",
        "workflow_definition": create_minimal_workflow_definition(
            name="no-project-workflow",
            description="Test workflow",
        ),
    }

    response = await jwt_client.post("/api/v1/workflows", json=workflow_without_project)

    assert response.status_code == 422
    assert_error_data(
        response,
        error_type="https://api.example.com/errors/validation-error",
        title="Request Validation Error",
        detail="Validation failed: project_id: Field required",
        code="REQUEST_VALIDATION_ERROR",
        retryable=False,
    )


@pytest.mark.asyncio
async def test_post_workflow_duplicate_name(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Test creating a workflow with a duplicate name.

    Expected: 409 Conflict with RFC 9457 format
    """
    workflow = {
        "name": "duplicate-workflow",
        "project_id": test_project_id,
        "workflow_definition": create_minimal_workflow_definition(
            name="duplicate-workflow",
            description="Test workflow",
        ),
    }

    # Create first workflow
    response1 = await jwt_client.post("/api/v1/workflows", json=workflow)
    assert response1.status_code == 201

    # Try to create duplicate
    response2 = await jwt_client.post("/api/v1/workflows", json=workflow)
    assert response2.status_code == 409
    data = response2.json()
    assert "detail" in data
    assert "title" in data
    assert data["title"] == "Workflow Name Conflict"


@pytest.mark.asyncio
async def test_post_workflow_missing_required_fields(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Test creating a workflow with definition missing required V2 fields saves with issues.

    Expected: 201 Created with has_validation_issues=True (save always succeeds)
    """
    workflow_missing_fields = {
        "name": "incomplete-workflow",
        "project_id": test_project_id,
        "workflow_definition": {
            "schema_version": "2.0.0",
            # Missing required 'triggers', 'nodes', and 'edges' fields
        },
    }

    response = await jwt_client.post("/api/v1/workflows", json=workflow_missing_fields)

    assert response.status_code == 201
    data = response.json()
    assert data["has_validation_issues"] is True


@pytest.mark.asyncio
async def test_post_workflow_response_schema(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Test that the response matches the expected schema.

    Expected: Response contains all required fields with correct types
    """
    workflow = {
        "name": "schema-test-workflow",
        "description": "Testing response schema",
        "project_id": test_project_id,
        "workflow_definition": create_minimal_workflow_definition(
            name="schema-test",
            description="Testing response schema",
            activity_id="test_activity",
            activity_type="script_python",
        ),
    }

    response = await jwt_client.post("/api/v1/workflows", json=workflow)

    assert response.status_code == 201
    data = response.json()

    # Verify response schema
    required_fields = [
        "id",
        "name",
        "description",
        "current_version",
        "is_enabled",
        "created_at",
        "updated_at",
    ]

    for field in required_fields:
        assert field in data, f"Missing required field: {field}"

    # Verify types
    assert isinstance(data["id"], str)
    assert isinstance(data["name"], str)
    assert isinstance(data["current_version"], int)
    assert isinstance(data["is_enabled"], bool)
    assert isinstance(data["created_at"], str)
    assert isinstance(data["updated_at"], str)


@pytest.mark.asyncio
async def test_post_workflow_with_labels(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Test creating a workflow with labels.

    Expected: 201 Created with labels included
    """
    workflow_with_labels = {
        "name": "labeled-workflow",
        "project_id": test_project_id,
        "workflow_definition": create_minimal_workflow_definition(
            name="labeled-workflow",
            description="Workflow with labels",
        ),
        "labels": {
            "environment": "test",
            "team": "engineering",
        },
    }

    response = await jwt_client.post("/api/v1/workflows", json=workflow_with_labels)

    assert response.status_code == 201
    data = response.json()
    assert "labels" in data
    assert data["labels"]["environment"] == "test"
    assert data["labels"]["team"] == "engineering"


@pytest.mark.asyncio
async def test_post_workflow_with_labels_not_strings(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Test creating a workflow with non-string labels.

    Expected: 422 Unprocessable
    """
    workflow_with_labels = {
        "name": "labeled-workflow",
        "project_id": test_project_id,
        "workflow_definition": create_minimal_workflow_definition(
            name="labeled-workflow",
            description="Workflow with labels",
        ),
        "labels": {
            "valid": "value1",
            "invalid": 1,
        },
    }

    response = await jwt_client.post("/api/v1/workflows", json=workflow_with_labels)

    assert response.status_code == 422
    assert_error_data(
        response,
        error_type="https://api.example.com/errors/validation-error",
        title="Request Validation Error",
        detail="Validation failed: labels: labels value for key 'invalid' must be a string, got int",
        code="REQUEST_VALIDATION_ERROR",
        retryable=False,
    )


@pytest.mark.asyncio
async def test_post_workflow_with_long_description(jwt_client: AsyncClient, test_project_id: str) -> None:
    """Test creating a workflow with a long description. The field limit is 2,000 characters.

    Expected: 422 Unprocessable
    """
    workflow_with_labels = {
        "name": "labeled-workflow",
        "description": "=" * 2001,
        "project_id": test_project_id,
        "workflow_definition": create_minimal_workflow_definition(
            name="labeled-workflow",
            description="Workflow with labels",
        ),
    }

    response = await jwt_client.post("/api/v1/workflows", json=workflow_with_labels)

    assert response.status_code == 422
    assert_error_data(
        response,
        error_type="https://api.example.com/errors/validation-error",
        title="Request Validation Error",
        detail="Validation failed: description: String should have at most 2000 characters",
        code="REQUEST_VALIDATION_ERROR",
        retryable=False,
    )
