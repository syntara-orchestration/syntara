"""Unit tests for _build_workflow_with_version_response helper and publish endpoint."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from syntara.core.models.user_reference import UserReference
from syntara.workflows.models.workflow import (
    PublishWorkflowVersionResponse,
    WorkflowRead,
    WorkflowReadWithVersion,
)
from syntara.workflows.models.workflow_version import PublishVersionRequest, WorkflowVersionRead
from syntara.workflows.router import _build_workflow_with_version_response, publish_workflow_version


def _make_mock_workflow() -> MagicMock:
    wf = MagicMock(spec=[])
    wf.id = uuid4()
    wf.name = "test-wf"
    wf.description = None
    wf.labels = {}
    wf.current_version = 1
    wf.is_builtin = False
    wf.is_enabled = True
    wf.has_validation_issues = False
    wf.created_by = uuid4()
    wf.updated_by = None
    wf.project_id = uuid4()
    wf.published_version_id = None
    wf.created_at = "2026-01-01T00:00:00Z"
    wf.updated_at = "2026-01-01T00:00:00Z"
    return wf


def _make_mock_version() -> MagicMock:
    v = MagicMock(spec=[])
    v.id = uuid4()
    v.workflow_id = uuid4()
    v.version = 1
    v.status = "published"
    v.schema_version = "2.0.0"
    v.workflow_definition = {"schema_version": "2.0.0", "name": "test"}
    v.name = None
    v.publish_name = None
    v.change_description = None
    v.created_by = uuid4()
    v.created_at = "2026-01-01T00:00:00Z"
    v.updated_at = "2026-01-01T00:00:00Z"
    return v


async def _to_read(workflow: MagicMock) -> WorkflowRead:
    """Stand in for WorkflowService.to_read without a database.

    The real method resolves created_by/updated_by before returning; a response
    still holding a raw id is rejected at serialization, so mirror that here.
    """
    read = WorkflowRead.model_validate(workflow, from_attributes=True)
    read.created_by = UserReference(id=workflow.created_by, name="tester")
    read.updated_by = None
    return read


async def _to_version_read(version: MagicMock, *_args: object, **_kwargs: object) -> WorkflowVersionRead:
    """Stand in for WorkflowService.to_version_read without a database.

    Like to_read, the real method resolves created_by before returning.
    """
    return WorkflowVersionRead(
        id=version.id,
        workflow_id=version.workflow_id,
        version=version.version,
        schema_version=version.schema_version,
        workflow_definition=version.workflow_definition,
        change_description=version.change_description,
        name=version.name,
        status="draft",
        created_by=UserReference(id=version.created_by, name="tester"),
        created_at=version.created_at,
        updated_at=version.updated_at,
    )


def _make_mock_service() -> AsyncMock:
    service = AsyncMock()
    service.session = AsyncMock()
    service.get_publish_context = AsyncMock(return_value=({}, {}))
    service.to_read = AsyncMock(side_effect=_to_read)
    service.to_version_read = AsyncMock(side_effect=_to_version_read)
    return service


@pytest.mark.asyncio
async def test_returns_workflow_read_with_version_by_default() -> None:
    result = await _build_workflow_with_version_response(
        _make_mock_workflow(), _make_mock_version(), _make_mock_service()
    )
    assert isinstance(result, WorkflowReadWithVersion)
    assert not isinstance(result, PublishWorkflowVersionResponse)


@pytest.mark.asyncio
async def test_publish_endpoint_returns_warning() -> None:
    mock_service = _make_mock_service()
    mock_service.publish_workflow_version.return_value = (
        _make_mock_workflow(),
        _make_mock_version(),
        "sync failed",
    )
    request = PublishVersionRequest(publish_name=None, change_description=None)

    result = await publish_workflow_version(workflow_id=uuid4(), version=1, request=request, service=mock_service)

    assert isinstance(result, PublishWorkflowVersionResponse)
    assert result.warning == "sync failed"
