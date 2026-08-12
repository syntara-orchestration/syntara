"""Unit tests for _build_workflow_with_version_response helper and publish endpoint."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from syntara.workflows.models.workflow import PublishWorkflowVersionResponse, WorkflowReadWithVersion
from syntara.workflows.models.workflow_version import PublishVersionRequest
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
    wf.project_id = uuid4()
    wf.published_version_id = None
    wf.created_at = "2026-01-01T00:00:00Z"
    wf.updated_at = "2026-01-01T00:00:00Z"
    wf.deleted_at = None
    wf.deleted_by = None
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
    v.deleted_at = None
    v.deleted_by = None
    return v


def _make_mock_service() -> AsyncMock:
    service = AsyncMock()
    service.session = AsyncMock()
    service.get_publish_context = AsyncMock(return_value=({}, {}))
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
