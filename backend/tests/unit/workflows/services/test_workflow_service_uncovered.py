"""Unit tests for uncovered lines in WorkflowService methods."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.workflows.exceptions import BuiltinWorkflowModifyError, WorkflowVersionConflictError
from syntara.workflows.services.workflow_service import WorkflowService


@pytest.fixture
def mock_service() -> WorkflowService:
    """Create a WorkflowService with mocked dependencies."""
    session = AsyncMock()
    session.add = MagicMock()
    user = MagicMock()
    user.id = uuid4()
    service = WorkflowService.__new__(WorkflowService)
    service.session = session
    service.user = user
    return service


class TestCheckExpectedVersion:
    """Tests for _check_expected_version conflict detection."""

    @pytest.mark.asyncio
    async def test_conflict_includes_version_name(self, mock_service: WorkflowService) -> None:
        """Verify error carries version_name when the version row exists."""
        workflow = MagicMock()
        workflow.id = uuid4()
        workflow.current_version = 3
        workflow.updated_at = None

        current_ver = MagicMock()
        current_ver.version = 3
        current_ver.name = "Release v2"
        current_ver.created_at = MagicMock()
        user_obj = MagicMock()
        user_obj.username = "alice"

        expected_ver = MagicMock()
        expected_ver.version = 1
        expected_ver.name = "Initial Draft"
        expected_ver.created_at = MagicMock()

        result = MagicMock()
        result.all.return_value = [(current_ver, user_obj), (expected_ver, None)]
        mock_service.session.exec.return_value = result  # type: ignore[attr-defined]

        with pytest.raises(WorkflowVersionConflictError) as exc_info:
            await mock_service._check_expected_version(workflow, expected_version=1)

        assert exc_info.value.current_version_name == "Release v2"
        assert exc_info.value.expected_version_name == "Initial Draft"
        assert exc_info.value.expected_created_at == expected_ver.created_at

    @pytest.mark.asyncio
    async def test_conflict_version_name_none_when_no_row(self, mock_service: WorkflowService) -> None:
        """Verify error has current_version_name=None when no version row found."""
        workflow = MagicMock()
        workflow.id = uuid4()
        workflow.current_version = 2
        workflow.updated_at = MagicMock()

        result = MagicMock()
        result.all.return_value = []
        mock_service.session.exec.return_value = result  # type: ignore[attr-defined]

        with pytest.raises(WorkflowVersionConflictError) as exc_info:
            await mock_service._check_expected_version(workflow, expected_version=1)

        assert exc_info.value.current_version_name is None
        assert exc_info.value.expected_version_name is None
        assert exc_info.value.expected_created_at is None


class TestGetWebhookSyncDefinition:
    """Tests for _get_webhook_sync_definition published-version lookup."""

    @pytest.mark.asyncio
    async def test_returns_published_definition_when_published(self, mock_service: WorkflowService) -> None:
        """Return published version's definition when published_version_id is set."""
        workflow = MagicMock()
        workflow.published_version_id = uuid4()
        published_ver = MagicMock()
        published_ver.workflow_definition = {"nodes": [{"id": "published"}]}

        result = MagicMock()
        result.one_or_none.return_value = published_ver
        mock_service.session.exec.return_value = result  # type: ignore[attr-defined]

        fallback = {"nodes": [{"id": "fallback"}]}
        definition = await mock_service._get_webhook_sync_definition(uuid4(), workflow, fallback)

        assert definition == {"nodes": [{"id": "published"}]}

    @pytest.mark.asyncio
    async def test_returns_fallback_when_not_published(self, mock_service: WorkflowService) -> None:
        """Return fallback definition when published_version_id is None."""
        workflow = MagicMock()
        workflow.published_version_id = None

        fallback = {"nodes": [{"id": "fallback"}]}
        definition = await mock_service._get_webhook_sync_definition(uuid4(), workflow, fallback)

        assert definition == fallback
        mock_service.session.exec.assert_not_called()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_returns_fallback_when_published_version_missing(self, mock_service: WorkflowService) -> None:
        """Return fallback and log warning when published version record is not found."""
        workflow = MagicMock()
        workflow.published_version_id = uuid4()

        result = MagicMock()
        result.one_or_none.return_value = None
        mock_service.session.exec.return_value = result  # type: ignore[attr-defined]

        fallback = {"nodes": [{"id": "fallback"}]}
        with patch("syntara.workflows.services.workflow_service.logger") as mock_logger:
            definition = await mock_service._get_webhook_sync_definition(uuid4(), workflow, fallback)

        assert definition == fallback
        mock_logger.warning.assert_called_once()


class TestUpdateVersionMetadata:
    """Tests for update_version_metadata field-set logic."""

    @pytest.mark.asyncio
    async def test_updates_name_field(self, mock_service: WorkflowService) -> None:
        """Verify name is set when included in default fields_set."""
        workflow_id = uuid4()
        version_record = MagicMock()
        mock_workflow = MagicMock(is_builtin=False)
        mock_service.get_workflow_by_id = AsyncMock(return_value=mock_workflow)  # type: ignore[method-assign]
        mock_service._get_version_or_none = AsyncMock(return_value=version_record)  # type: ignore[method-assign]

        result = await mock_service.update_version_metadata(workflow_id, 1, name="New Name")

        assert version_record.name == "New Name"
        assert result is version_record

    @pytest.mark.asyncio
    async def test_updates_change_description(self, mock_service: WorkflowService) -> None:
        """Verify change_description is set when included in default fields_set."""
        workflow_id = uuid4()
        version_record = MagicMock()
        mock_workflow = MagicMock(is_builtin=False)
        mock_service.get_workflow_by_id = AsyncMock(return_value=mock_workflow)  # type: ignore[method-assign]
        mock_service._get_version_or_none = AsyncMock(return_value=version_record)  # type: ignore[method-assign]

        await mock_service.update_version_metadata(workflow_id, 1, change_description="Updated")

        assert version_record.change_description == "Updated"

    @pytest.mark.asyncio
    async def test_uses_fields_set_when_provided(self, mock_service: WorkflowService) -> None:
        """Only update fields present in fields_set, leaving others untouched."""
        workflow_id = uuid4()
        version_record = MagicMock()
        version_record.change_description = "Original"
        mock_workflow = MagicMock(is_builtin=False)
        mock_service.get_workflow_by_id = AsyncMock(return_value=mock_workflow)  # type: ignore[method-assign]
        mock_service._get_version_or_none = AsyncMock(return_value=version_record)  # type: ignore[method-assign]

        await mock_service.update_version_metadata(workflow_id, 1, name="Only Name", fields_set={"name"})

        assert version_record.name == "Only Name"
        assert version_record.change_description == "Original"

    @pytest.mark.asyncio
    async def test_no_changes_returns_record_without_commit(self, mock_service: WorkflowService) -> None:
        """Empty fields_set means no mutations and no commit."""
        workflow_id = uuid4()
        version_record = MagicMock()
        mock_workflow = MagicMock(is_builtin=False)
        mock_service.get_workflow_by_id = AsyncMock(return_value=mock_workflow)  # type: ignore[method-assign]
        mock_service._get_version_or_none = AsyncMock(return_value=version_record)  # type: ignore[method-assign]

        result = await mock_service.update_version_metadata(workflow_id, 1, fields_set=set())

        assert result is version_record
        mock_service.session.commit.assert_not_called()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_builtin_workflow_raises(self, mock_service: WorkflowService) -> None:
        """Built-in workflows must not allow version metadata updates."""
        workflow_id = uuid4()
        mock_workflow = MagicMock(is_builtin=True, name="Builtin WF")
        mock_service.get_workflow_by_id = AsyncMock(return_value=mock_workflow)  # type: ignore[method-assign]

        with pytest.raises(BuiltinWorkflowModifyError, match="Builtin WF"):
            await mock_service.update_version_metadata(workflow_id, 1, change_description="sneaky edit")


class TestRestoreWorkflowVersionSourceLabel:
    """Tests for source_label logic in restore_workflow_version."""

    @pytest.mark.asyncio
    async def test_source_label_uses_version_name_when_set(self, mock_service: WorkflowService) -> None:
        """Verify change_description contains the version name when set."""
        workflow_id = uuid4()
        mock_workflow = MagicMock()
        mock_workflow.is_builtin = False
        mock_workflow.id = workflow_id
        mock_workflow.current_version = 1

        mock_target = MagicMock()
        mock_target.name = "Release v1"
        mock_target.created_at = MagicMock()
        mock_target.workflow_definition = {"nodes": []}

        mock_current = MagicMock()
        mock_current.workflow_definition = {"nodes": []}

        new_version = MagicMock()

        with (
            patch.object(mock_service, "_get_workflow_for_update", new_callable=AsyncMock, return_value=mock_workflow),
            patch.object(
                mock_service, "_get_version_or_none", new_callable=AsyncMock, side_effect=[mock_target, mock_current]
            ),
            patch.object(
                mock_service, "_create_version_record", new_callable=AsyncMock, return_value=new_version
            ) as mock_create,
            patch.object(mock_service.session, "commit", new_callable=AsyncMock),
            patch.object(mock_service.session, "refresh", new_callable=AsyncMock),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
        ):
            await mock_service.restore_workflow_version(workflow_id, version=3)

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args
        assert "Release v1" in call_kwargs.kwargs["change_description"]

    @pytest.mark.asyncio
    async def test_source_label_uses_date_when_no_name(self, mock_service: WorkflowService) -> None:
        """Verify change_description contains ISO date when name is None."""
        workflow_id = uuid4()
        mock_workflow = MagicMock()
        mock_workflow.is_builtin = False
        mock_workflow.id = workflow_id
        mock_workflow.current_version = 1

        mock_target = MagicMock()
        mock_target.name = None
        mock_created_at = MagicMock()
        mock_created_at.isoformat.return_value = "2025-01-15T10:30:00+00:00"
        mock_target.created_at = mock_created_at
        mock_target.workflow_definition = {"nodes": []}

        mock_current = MagicMock()
        mock_current.workflow_definition = {"nodes": []}

        new_version = MagicMock()

        with (
            patch.object(mock_service, "_get_workflow_for_update", new_callable=AsyncMock, return_value=mock_workflow),
            patch.object(
                mock_service, "_get_version_or_none", new_callable=AsyncMock, side_effect=[mock_target, mock_current]
            ),
            patch.object(
                mock_service, "_create_version_record", new_callable=AsyncMock, return_value=new_version
            ) as mock_create,
            patch.object(mock_service.session, "commit", new_callable=AsyncMock),
            patch.object(mock_service.session, "refresh", new_callable=AsyncMock),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
        ):
            await mock_service.restore_workflow_version(workflow_id, version=3)

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args
        assert "2025-01-15T10:30:00+00:00" in call_kwargs.kwargs["change_description"]

    @pytest.mark.asyncio
    async def test_source_label_uses_version_number_when_no_name_or_date(self, mock_service: WorkflowService) -> None:
        """Verify change_description contains version number as fallback."""
        workflow_id = uuid4()
        mock_workflow = MagicMock()
        mock_workflow.is_builtin = False
        mock_workflow.id = workflow_id
        mock_workflow.current_version = 1

        mock_target = MagicMock()
        mock_target.name = None
        mock_target.created_at = None
        mock_target.workflow_definition = {"nodes": []}

        mock_current = MagicMock()
        mock_current.workflow_definition = {"nodes": []}

        new_version = MagicMock()

        with (
            patch.object(mock_service, "_get_workflow_for_update", new_callable=AsyncMock, return_value=mock_workflow),
            patch.object(
                mock_service, "_get_version_or_none", new_callable=AsyncMock, side_effect=[mock_target, mock_current]
            ),
            patch.object(
                mock_service, "_create_version_record", new_callable=AsyncMock, return_value=new_version
            ) as mock_create,
            patch.object(mock_service.session, "commit", new_callable=AsyncMock),
            patch.object(mock_service.session, "refresh", new_callable=AsyncMock),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
        ):
            await mock_service.restore_workflow_version(workflow_id, version=3)

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args
        assert "version 3" in call_kwargs.kwargs["change_description"]
