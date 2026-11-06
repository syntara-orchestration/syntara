"""Tests for published workflow step metadata returned by the workflow detail API."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from syntara.workflows.models import Workflow, WorkflowVersion
from syntara.workflows.services.workflow_service import WorkflowService, _output_schema_for_step


@pytest.mark.asyncio
async def test_published_step_metadata_uses_the_published_version_and_output_models() -> None:
    workflow_id = uuid4()
    published_version_id = uuid4()
    now = datetime.now(UTC)
    workflow = Workflow(
        id=workflow_id,
        name="test-workflow",
        project_id=uuid4(),
        created_by=uuid4(),
        current_version=2,
        is_enabled=True,
        published_version_id=published_version_id,
        created_at=now,
        updated_at=now,
    )
    published_version = WorkflowVersion(
        id=published_version_id,
        workflow_id=workflow_id,
        version=1,
        schema_version="2.0.0",
        workflow_definition={
            "nodes": [
                {"id": "published_script", "type": "script"},
                {"id": "unknown_step", "type": "future_type"},
            ]
        },
        created_by=uuid4(),
        created_at=now,
        updated_at=now,
    )
    service = WorkflowService.__new__(WorkflowService)
    service.session = AsyncMock()
    service.session.get.return_value = published_version

    metadata = await service.get_published_step_metadata(workflow)

    assert metadata is not None
    assert metadata.version_id == published_version_id
    assert metadata.version == 1
    assert [step.id for step in metadata.steps] == ["published_script", "unknown_step"]
    script_schema = metadata.steps[0].output_schema
    assert script_schema is not None
    assert "stdout" in script_schema["properties"]
    assert "status" in script_schema["properties"]
    assert metadata.steps[1].output_schema is None
    service.session.get.assert_awaited_once_with(WorkflowVersion, published_version_id)


@pytest.mark.asyncio
async def test_published_step_metadata_is_absent_when_workflow_is_unpublished() -> None:
    now = datetime.now(UTC)
    workflow = Workflow(
        id=uuid4(),
        name="unpublished-workflow",
        project_id=uuid4(),
        created_by=uuid4(),
        current_version=1,
        is_enabled=False,
        published_version_id=None,
        created_at=now,
        updated_at=now,
    )
    service = WorkflowService.__new__(WorkflowService)
    service.session = AsyncMock()

    metadata = await service.get_published_step_metadata(workflow)

    assert metadata is None
    service.session.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_published_step_metadata_reuses_output_schema_for_large_workflows() -> None:
    workflow_id = uuid4()
    published_version_id = uuid4()
    now = datetime.now(UTC)
    workflow = Workflow(
        id=workflow_id,
        name="large-workflow",
        project_id=uuid4(),
        created_by=uuid4(),
        current_version=1,
        is_enabled=True,
        published_version_id=published_version_id,
        created_at=now,
        updated_at=now,
    )
    published_version = WorkflowVersion(
        id=published_version_id,
        workflow_id=workflow_id,
        version=1,
        schema_version="2.0.0",
        workflow_definition={"nodes": [{"id": f"step_{index}", "type": "script"} for index in range(64)]},
        created_by=uuid4(),
        created_at=now,
        updated_at=now,
    )
    service = WorkflowService.__new__(WorkflowService)
    service.session = AsyncMock()
    service.session.get.return_value = published_version
    _output_schema_for_step.cache_clear()

    metadata = await service.get_published_step_metadata(workflow)

    assert metadata is not None
    assert len(metadata.steps) == 64
    assert _output_schema_for_step.cache_info().misses == 1
    assert _output_schema_for_step.cache_info().hits == 63
    _output_schema_for_step.cache_clear()
