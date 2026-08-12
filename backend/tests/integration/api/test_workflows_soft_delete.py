"""Integration tests for workflow soft delete implementation.

Verifies soft delete implementation (deleted_at timestamps, deleted_by audit trail)
by querying the database directly. The API only returns 404 for deleted records, so
DB access is required to verify soft delete vs hard delete behavior.

Uses auth_client + test_db_session (not syntara_api) because syntara_api is session-scoped
with its own connection pool, causing race conditions with function-scoped test_db_session
in parallel test execution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlmodel import select

from syntara.workflows.models import Workflow
from tests.helpers.workflow import create_minimal_workflow_definition

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.mark.asyncio
async def test_delete_workflow_is_soft_delete_not_hard(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_project_id: str,
) -> None:
    """Test that DELETE performs soft delete, not hard delete.

    Expected: Workflow record still exists in database (with deleted_at set)
    This test directly verifies the database state to ensure soft delete behavior.
    """
    workflow_name = f"soft-not-hard-{uuid4().hex[:8]}"
    workflow_def = create_minimal_workflow_definition(
        name=workflow_name,
        description="Soft not hard delete test",
        activity_id="soft_not_hard_activity",
    )

    create_response = await auth_client.post(
        "/api/v1/workflows",
        json={
            "name": workflow_name,
            "project_id": test_project_id,
            "workflow_definition": workflow_def,
        },
    )
    assert create_response.status_code == 201
    workflow_data = create_response.json()
    workflow_id = workflow_data["id"]

    # Delete workflow
    delete_response = await auth_client.delete(f"/api/v1/workflows/{workflow_id}")
    assert delete_response.status_code == 204

    # Workflow should return 404 on normal GET (filtered by deleted_at IS NULL)
    get_response = await auth_client.get(f"/api/v1/workflows/{workflow_id}")
    assert get_response.status_code == 404

    # Verify in database: Record still exists with deleted_at set
    result = await test_db_session.exec(
        select(Workflow).filter(Workflow.id == workflow_id)
        # NOTE: No deleted_at filter - we want to see the record even if soft-deleted
    )
    db_workflow = result.one_or_none()

    # Assert record exists (not hard-deleted)
    assert db_workflow is not None, "Workflow was hard-deleted instead of soft-deleted"

    # Assert deleted_at IS NOT NULL (soft delete timestamp is set)
    assert db_workflow.deleted_at is not None, "deleted_at field is NULL - soft delete not applied"

    # Assert deleted_by is set
    assert db_workflow.deleted_by is not None, "deleted_by field is NULL - should track who deleted it"
