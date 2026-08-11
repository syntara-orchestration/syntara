"""Integration tests for GET /api/v1/executions endpoint."""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.workflows.models import Workflow
from syntara.workflows.models.execution import ExecutionStatus
from tests.integration.helpers.workflow import ExecutionsFactory

# ============================================================================
# Tests
# ============================================================================


@pytest.mark.asyncio
async def test_list_executions_success(
    auth_client: AsyncClient,
    executions_factory: ExecutionsFactory,
) -> None:
    """Test successful listing of all executions."""
    # Create multiple executions
    await executions_factory.create_executions(count=3)

    response = await auth_client.get("/api/v1/executions")

    assert response.status_code == 200
    data = response.json()
    assert "resources" in data
    assert isinstance(data["resources"], list)
    assert len(data["resources"]) == 3
    # total is always present but null when include_total=false
    assert "total" in data
    assert data["total"] is None


@pytest.mark.asyncio
async def test_list_executions_with_include_total(
    auth_client: AsyncClient,
    executions_factory: ExecutionsFactory,
) -> None:
    """Test listing executions with total count."""
    await executions_factory.create_executions(count=5)

    response = await auth_client.get("/api/v1/executions?include_total=true")

    assert response.status_code == 200
    data = response.json()
    assert "resources" in data
    assert "total" in data
    assert data["total"] == 5


@pytest.mark.asyncio
async def test_list_executions_filter_by_workflow_id(
    auth_client: AsyncClient,
    test_workflow: Workflow,
    executions_factory: ExecutionsFactory,
) -> None:
    """Test filtering executions by workflow_id."""
    await executions_factory.create_executions(count=2)

    response = await auth_client.get(f"/api/v1/executions?workflow_id={test_workflow.id}")

    assert response.status_code == 200
    data = response.json()
    assert len(data["resources"]) == 2
    for item in data["resources"]:
        assert item["workflow_id"] == str(test_workflow.id)


@pytest.mark.asyncio
async def test_list_executions_filter_by_status(
    auth_client: AsyncClient,
    executions_factory: ExecutionsFactory,
) -> None:
    """Test filtering executions by status."""
    # Create executions with different statuses
    await executions_factory.create_executions(count=2, status=ExecutionStatus.PENDING)
    await executions_factory.create_executions(count=2, status=ExecutionStatus.RUNNING)

    response = await auth_client.get("/api/v1/executions?status=pending")

    assert response.status_code == 200
    data = response.json()
    assert len(data["resources"]) == 2
    for item in data["resources"]:
        assert item["status"] == "pending"


@pytest.mark.asyncio
async def test_list_executions_filter_by_created_by(
    auth_client: AsyncClient,
    test_user: User,
    executions_factory: ExecutionsFactory,
) -> None:
    """Test filtering executions by created_by (user who created execution)."""
    await executions_factory.create_executions(count=2)

    response = await auth_client.get(f"/api/v1/executions?created_by={test_user.id}")

    assert response.status_code == 200
    data = response.json()
    assert len(data["resources"]) == 2
    for item in data["resources"]:
        assert item["created_by"] == str(test_user.id)


@pytest.mark.asyncio
async def test_list_executions_with_label_filtering(
    auth_client: AsyncClient,
    executions_factory: ExecutionsFactory,
) -> None:
    """Test filtering executions by labels using JSONB containment."""
    # Create executions with different labels
    await executions_factory.create_executions(
        count=2,
        labels={"environment": "production", "team": "backend"},
    )
    await executions_factory.create_executions(
        count=2,
        labels={"environment": "staging"},
    )

    # Filter by single label
    response = await auth_client.get("/api/v1/executions?labels[environment]=production")

    assert response.status_code == 200
    data = response.json()
    assert len(data["resources"]) == 2
    for item in data["resources"]:
        assert item["labels"].get("environment") == "production"


@pytest.mark.asyncio
async def test_list_executions_pagination_with_limit(
    auth_client: AsyncClient,
    executions_factory: ExecutionsFactory,
) -> None:
    """Test pagination with limit parameter."""
    await executions_factory.create_executions(count=10)

    response = await auth_client.get("/api/v1/executions?limit=3")

    assert response.status_code == 200
    data = response.json()
    assert len(data["resources"]) == 3


@pytest.mark.asyncio
async def test_list_executions_pagination_with_cursor(
    auth_client: AsyncClient,
    executions_factory: ExecutionsFactory,
) -> None:
    """Test cursor-based pagination."""
    await executions_factory.create_executions(count=10)

    # Get first page
    response = await auth_client.get("/api/v1/executions?limit=3")
    assert response.status_code == 200
    data = response.json()
    assert len(data["resources"]) == 3

    # If there's a next cursor, fetch next page
    if data.get("next"):
        next_response = await auth_client.get(f"/api/v1/executions?cursor={data['next']}&limit=3")
        assert next_response.status_code == 200
        next_data = next_response.json()
        assert "resources" in next_data
        # Ensure different results (not same as first page)
        assert data["resources"][0]["id"] != next_data["resources"][0]["id"]


@pytest.mark.asyncio
async def test_list_executions_sorting(
    auth_client: AsyncClient,
    executions_factory: ExecutionsFactory,
) -> None:
    """Test sorting executions by created_at."""
    await executions_factory.create_executions(count=5)

    # Sort descending (newest first)
    response = await auth_client.get("/api/v1/executions?sort=-created_at&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert len(data["resources"]) == 5

    # Verify descending order
    for i in range(len(data["resources"]) - 1):
        assert data["resources"][i]["created_at"] >= data["resources"][i + 1]["created_at"]


@pytest.mark.asyncio
async def test_list_executions_empty(
    auth_client: AsyncClient,
) -> None:
    """Test listing executions when none exist for a workflow."""
    # Use a non-existent workflow_id to ensure empty result
    non_existent_id = uuid.uuid4()
    response = await auth_client.get(f"/api/v1/executions?workflow_id={non_existent_id}&include_total=true")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["resources"] == []


@pytest.mark.asyncio
async def test_list_executions_multiple_filters(
    auth_client: AsyncClient,
    test_workflow: Workflow,
    executions_factory: ExecutionsFactory,
) -> None:
    """Test combining multiple filters (AND logic)."""
    await executions_factory.create_executions(
        count=2,
        status=ExecutionStatus.PENDING,
        labels={"environment": "production"},
    )
    await executions_factory.create_executions(
        count=2,
        status=ExecutionStatus.RUNNING,
        labels={"environment": "production"},
    )

    # Filter by workflow_id, status, and labels
    response = await auth_client.get(
        f"/api/v1/executions?workflow_id={test_workflow.id}&status=pending&labels[environment]=production"
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["resources"]) == 2
    for item in data["resources"]:
        assert item["workflow_id"] == str(test_workflow.id)
        assert item["status"] == "pending"
        assert item["labels"].get("environment") == "production"


# ============================================================================
# workflow_name field tests
# ============================================================================


@pytest.mark.asyncio
async def test_list_executions_includes_workflow_name(
    auth_client: AsyncClient,
    test_workflow: Workflow,
    executions_factory: ExecutionsFactory,
) -> None:
    """Test that workflow_name is populated in execution list responses."""
    await executions_factory.create_executions(count=2)

    response = await auth_client.get("/api/v1/executions")

    assert response.status_code == 200
    data = response.json()
    for item in data["resources"]:
        assert item["workflow_name"] == test_workflow.name


@pytest.mark.asyncio
async def test_list_executions_workflow_name_after_soft_delete(
    auth_client: AsyncClient,
    test_workflow: Workflow,
    test_user: User,
    test_db_session: AsyncSession,
    executions_factory: ExecutionsFactory,
) -> None:
    """Test that workflow_name is still returned after the workflow is soft-deleted."""
    await executions_factory.create_executions(count=1)

    test_workflow.soft_delete(user_id=test_user.id, deletion_time=datetime.now(UTC))
    await test_db_session.commit()

    response = await auth_client.get("/api/v1/executions")

    assert response.status_code == 200
    data = response.json()
    assert len(data["resources"]) == 1
    assert data["resources"][0]["workflow_name"] == test_workflow.name
