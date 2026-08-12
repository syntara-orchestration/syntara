"""Unit tests for workflow export service methods."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.workflows.exceptions import WorkflowVersionNotFoundError
from syntara.workflows.services.workflow_service import WorkflowService


@pytest.fixture
def mock_service() -> WorkflowService:
    """Create a WorkflowService with mocked dependencies."""
    session = AsyncMock()
    user = MagicMock()
    user.id = uuid4()
    service = WorkflowService.__new__(WorkflowService)
    service.session = session
    service.user = user
    return service


class TestGetVersionForExport:
    """Tests for get_version_for_export."""

    @pytest.mark.asyncio
    async def test_returns_workflow_and_version(self, mock_service: WorkflowService) -> None:
        workflow_id = uuid4()
        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.name = "test-wf"

        mock_version = MagicMock()
        mock_version.version = 2
        mock_version.workflow_definition = {"nodes": [], "edges": [], "triggers": []}

        with (
            patch.object(mock_service, "get_workflow_by_id", return_value=mock_workflow),
            patch.object(mock_service, "_get_version_or_none", return_value=mock_version),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
        ):
            workflow, version = await mock_service.get_version_for_export(workflow_id, 2)

        assert workflow == mock_workflow
        assert version == mock_version

    @pytest.mark.asyncio
    async def test_raises_on_missing_version(self, mock_service: WorkflowService) -> None:
        workflow_id = uuid4()
        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id

        with (
            patch.object(mock_service, "get_workflow_by_id", return_value=mock_workflow),
            patch.object(mock_service, "_get_version_or_none", return_value=None),
            pytest.raises(WorkflowVersionNotFoundError),
        ):
            await mock_service.get_version_for_export(workflow_id, 999)

    @pytest.mark.asyncio
    async def test_dispatches_exported_audit_event(self, mock_service: WorkflowService) -> None:
        workflow_id = uuid4()
        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.name = "audit-test"

        mock_version = MagicMock()
        mock_version.version = 3

        with (
            patch.object(mock_service, "get_workflow_by_id", return_value=mock_workflow),
            patch.object(mock_service, "_get_version_or_none", return_value=mock_version),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher") as mock_dispatcher,
        ):
            await mock_service.get_version_for_export(workflow_id, 3)

        mock_dispatcher.dispatch.assert_called_once()
        event = mock_dispatcher.dispatch.call_args[0][0]
        assert event.workflow_id == workflow_id
        assert event.version == 3
