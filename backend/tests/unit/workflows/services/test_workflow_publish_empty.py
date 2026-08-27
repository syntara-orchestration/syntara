"""Unit tests for publish_workflow_version validation and no-copy publish behavior."""

import asyncio
import time
from collections.abc import AsyncGenerator, Generator
from typing import NoReturn
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from syntara.workflows.exceptions import (
    ScheduledTriggerSyncError,
    TriggerValidationError,
    WorkflowPublishValidationError,
)
from syntara.workflows.services import scheduled_trigger_service as scheduled_trigger_service_mod
from syntara.workflows.services.scheduled_trigger_service import ScheduledTriggerService
from syntara.workflows.services.workflow_service import WorkflowService, _pending_schedule_delete_tasks


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


def _pending_delete_tasks() -> list[asyncio.Task[None]]:
    return [task for task in _pending_schedule_delete_tasks if not task.done()]


async def _finish_background_deletes(*, wait_seconds: float = 1.0) -> None:
    tasks = list(_pending_schedule_delete_tasks)
    if tasks:
        async with asyncio.timeout(wait_seconds):
            await asyncio.gather(*tasks, return_exceptions=True)


async def _cancel_background_deletes() -> None:
    tasks = list(_pending_schedule_delete_tasks)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


class TestPublishEmptyWorkflow:
    """Publish rejects workflows with no steps."""

    @pytest.mark.asyncio
    async def test_publish_rejects_empty_nodes(self, mock_service: WorkflowService) -> None:
        workflow_id = uuid4()
        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.is_builtin = False

        mock_version = MagicMock()
        mock_version.version = 1
        mock_version.workflow_definition = {
            "schema_version": "2.0.0",
            "name": "empty",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [],
            "edges": [],
        }

        with (
            patch.object(mock_service, "_get_workflow_for_update", return_value=mock_workflow),
            patch.object(mock_service, "_get_version_or_none", return_value=mock_version),
            pytest.raises(WorkflowPublishValidationError) as exc_info,
        ):
            await mock_service.publish_workflow_version(workflow_id, version=1)

        assert any("at least one step" in f.message for f in exc_info.value.validation_result.findings)

    @pytest.mark.asyncio
    async def test_publish_allows_workflow_with_nodes(self, mock_service: WorkflowService) -> None:
        workflow_id = uuid4()
        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.is_builtin = False
        mock_workflow.published_version_id = None
        mock_workflow.current_version = 1
        mock_workflow.name = "test-wf"
        mock_workflow.project_id = uuid4()

        mock_version = MagicMock()
        mock_version.id = uuid4()
        mock_version.version = 1
        mock_version.workflow_definition = {
            "schema_version": "2.0.0",
            "name": "with-nodes",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [{"id": "n1", "type": "script", "parameters": {"language": "python", "code": "pass"}}],
            "edges": [{"from": "t1", "to": "n1"}],
        }
        mock_version.created_at = None

        with (
            patch.object(mock_service, "_get_workflow_for_update", return_value=mock_workflow),
            patch.object(mock_service, "_get_version_or_none", return_value=mock_version),
            patch.object(mock_service, "_flush_with_duplicate_check", new_callable=AsyncMock),
            patch.object(mock_service, "_sync_all_trigger_types", new_callable=AsyncMock),
            patch.object(mock_service, "_sync_scheduled_triggers", new_callable=AsyncMock),
            patch.object(mock_service.session, "commit", new_callable=AsyncMock),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService"),
        ):
            workflow, _version, _warning = await mock_service.publish_workflow_version(workflow_id, version=1)

        assert workflow == mock_workflow

    @pytest.mark.asyncio
    async def test_publish_sets_name_and_creates_event(self, mock_service: WorkflowService) -> None:
        workflow_id = uuid4()
        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.is_builtin = False
        mock_workflow.published_version_id = None
        mock_workflow.current_version = 1
        mock_workflow.name = "test-wf"
        mock_workflow.project_id = uuid4()

        mock_version = MagicMock()
        mock_version.id = uuid4()
        mock_version.version = 1
        mock_version.name = None
        mock_version.change_description = None
        mock_version.workflow_definition = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [{"id": "n1", "type": "script", "parameters": {"language": "python", "code": "pass"}}],
            "edges": [{"from": "t1", "to": "n1"}],
        }

        with (
            patch.object(mock_service, "_get_workflow_for_update", return_value=mock_workflow),
            patch.object(mock_service, "_get_version_or_none", return_value=mock_version),
            patch.object(mock_service, "_flush_with_duplicate_check", new_callable=AsyncMock),
            patch.object(mock_service, "_sync_all_trigger_types", new_callable=AsyncMock),
            patch.object(mock_service, "_sync_scheduled_triggers", new_callable=AsyncMock),
            patch.object(mock_service.session, "commit", new_callable=AsyncMock),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService"),
        ):
            workflow, version, _warning = await mock_service.publish_workflow_version(
                workflow_id, version=1, name="Release v1.0", change_description="First release"
            )

        assert version.name == "Release v1.0"
        assert version.change_description == "First release"
        assert workflow.published_version_id == mock_version.id
        assert workflow.is_enabled is True
        mock_add = mock_service.session.add
        mock_add.assert_called()  # type: ignore[attr-defined]
        added_objects = [call.args[0] for call in mock_add.call_args_list]  # type: ignore[attr-defined]
        from syntara.workflows.models.workflow_publish_event import WorkflowPublishEvent

        assert any(isinstance(obj, WorkflowPublishEvent) for obj in added_objects)

    @pytest.mark.asyncio
    async def test_publish_with_workflow_definition_creates_new_version(self, mock_service: WorkflowService) -> None:
        workflow_id = uuid4()
        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.is_builtin = False
        mock_workflow.published_version_id = None
        mock_workflow.current_version = 1
        mock_workflow.name = "test-wf"
        mock_workflow.project_id = uuid4()

        mock_version = MagicMock()
        mock_version.id = uuid4()
        mock_version.version = 1
        mock_version.workflow_definition = {
            "schema_version": "2.0.0",
            "name": "old",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [{"id": "n1", "type": "script", "parameters": {"language": "python", "code": "pass"}}],
            "edges": [{"from": "t1", "to": "n1"}],
        }

        new_definition = {
            "schema_version": "2.0.0",
            "name": "new",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [{"id": "n1", "type": "script", "parameters": {"language": "python", "code": "print(1)"}}],
            "edges": [{"from": "t1", "to": "n1"}],
        }

        new_version = MagicMock()
        new_version.id = uuid4()
        new_version.version = 2
        new_version.workflow_definition = new_definition

        with (
            patch.object(mock_service, "_get_workflow_for_update", return_value=mock_workflow),
            patch.object(mock_service, "_get_version_or_none", return_value=mock_version),
            patch.object(mock_service, "_create_version_record", new_callable=AsyncMock, return_value=new_version),
            patch.object(mock_service, "_flush_with_duplicate_check", new_callable=AsyncMock),
            patch.object(mock_service, "_sync_all_trigger_types", new_callable=AsyncMock),
            patch.object(mock_service, "_sync_scheduled_triggers", new_callable=AsyncMock),
            patch.object(mock_service.session, "flush", new_callable=AsyncMock),
            patch.object(mock_service.session, "commit", new_callable=AsyncMock),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService"),
        ):
            workflow, published, _warning = await mock_service.publish_workflow_version(
                workflow_id, version=1, workflow_definition=new_definition
            )

        assert published == new_version
        assert workflow.published_version_id == new_version.id


class TestUnpublishWorkflow:
    """Tests for unpublish_workflow missing version warning."""

    @pytest.fixture(autouse=True)
    def _unpublished_background_delete(self) -> Generator[None]:
        with patch.object(WorkflowService, "_workflow_is_published", new=AsyncMock(return_value=False)):
            yield

    @pytest.mark.asyncio
    async def test_unpublish_logs_warning_when_version_missing(self, mock_service: WorkflowService) -> None:
        workflow_id = uuid4()
        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.is_builtin = False
        mock_workflow.published_version_id = uuid4()
        mock_workflow.name = "test-wf"
        mock_workflow.project_id = uuid4()

        with (
            patch.object(mock_service, "_get_workflow_for_update", new_callable=AsyncMock, return_value=mock_workflow),
            patch.object(mock_service.session, "get", new_callable=AsyncMock, return_value=None),
            patch.object(mock_service, "_sync_all_trigger_types", new_callable=AsyncMock),
            patch.object(mock_service.session, "commit", new_callable=AsyncMock),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService"),
            patch(
                "syntara.workflows.services.workflow_service.ScheduledTriggerService",
                return_value=MagicMock(
                    get_client=AsyncMock(),
                    delete_triggers_for_workflow=AsyncMock(),
                ),
            ),
            patch("syntara.workflows.services.workflow_service.logger") as mock_logger,
        ):
            await mock_service.unpublish_workflow(workflow_id)
            await _finish_background_deletes()

        mock_logger.warning.assert_called_once()
        assert "Published version record not found" in mock_logger.warning.call_args[0][0]

    @pytest.mark.asyncio
    async def test_unpublish_with_valid_published_version(self, mock_service: WorkflowService) -> None:
        """Unpublish succeeds and clears published_version_id when version exists."""
        workflow_id = uuid4()
        pub_version_id = uuid4()
        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.is_builtin = False
        mock_workflow.published_version_id = pub_version_id
        mock_workflow.name = "test-wf"
        mock_workflow.project_id = uuid4()

        mock_published = MagicMock()
        mock_published.version = 3
        mock_published.workflow_definition = {"nodes": []}

        with (
            patch.object(mock_service, "_get_workflow_for_update", new_callable=AsyncMock, return_value=mock_workflow),
            patch.object(mock_service.session, "get", new_callable=AsyncMock, return_value=mock_published),
            patch.object(mock_service, "_sync_all_trigger_types", new_callable=AsyncMock),
            patch.object(mock_service.session, "commit", new_callable=AsyncMock),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService"),
            patch(
                "syntara.workflows.services.workflow_service.ScheduledTriggerService",
                return_value=MagicMock(
                    get_client=AsyncMock(),
                    delete_triggers_for_workflow=AsyncMock(),
                ),
            ),
        ):
            result = await mock_service.unpublish_workflow(workflow_id)
            await _finish_background_deletes()

        assert result.published_version_id is None
        assert result.is_enabled is False

    @pytest.mark.asyncio
    async def test_publish_without_name_preserves_existing(self, mock_service: WorkflowService) -> None:
        """Publish without name kwarg does not overwrite existing version name."""
        workflow_id = uuid4()
        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.is_builtin = False
        mock_workflow.published_version_id = None
        mock_workflow.current_version = 1
        mock_workflow.name = "test-wf"
        mock_workflow.project_id = uuid4()

        mock_version = MagicMock()
        mock_version.id = uuid4()
        mock_version.version = 1
        mock_version.name = "Original Name"
        mock_version.change_description = "Original Desc"
        mock_version.workflow_definition = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [{"id": "n1", "type": "script", "parameters": {"language": "python", "code": "pass"}}],
            "edges": [{"from": "t1", "to": "n1"}],
        }

        with (
            patch.object(mock_service, "_get_workflow_for_update", return_value=mock_workflow),
            patch.object(mock_service, "_get_version_or_none", return_value=mock_version),
            patch.object(mock_service, "_flush_with_duplicate_check", new_callable=AsyncMock),
            patch.object(mock_service, "_sync_all_trigger_types", new_callable=AsyncMock),
            patch.object(mock_service, "_sync_scheduled_triggers", new_callable=AsyncMock),
            patch.object(mock_service.session, "commit", new_callable=AsyncMock),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService"),
        ):
            _, version, _warning = await mock_service.publish_workflow_version(workflow_id, version=1)

        assert version.name == "Original Name"
        assert version.change_description == "Original Desc"


class TestBuildWorkflowWithVersionResponse:
    """Tests for _build_workflow_with_version_response router helper."""

    @pytest.mark.asyncio
    async def test_builds_response_with_published_version_number(self) -> None:
        """published_version_number is set when current version is the published version."""
        from syntara.workflows.router import _build_workflow_with_version_response

        version_id = uuid4()
        mock_service = AsyncMock()
        mock_service.get_publish_context.return_value = ({version_id}, {})
        workflow = MagicMock()
        workflow.id = uuid4()
        workflow.name = "test"
        workflow.description = None
        workflow.labels = {}
        workflow.current_version = 1
        workflow.is_builtin = False
        workflow.is_enabled = True
        workflow.has_validation_issues = False
        workflow.published_version_id = version_id
        workflow.created_by = uuid4()
        workflow.project_id = uuid4()
        workflow.created_at = MagicMock()
        workflow.updated_at = MagicMock()
        workflow.deleted_at = None
        workflow.deleted_by = None
        workflow.updated_by = None

        version = MagicMock()
        version.id = version_id
        version.workflow_id = workflow.id
        version.version = 1
        version.schema_version = "2.0.0"
        version.workflow_definition = {"nodes": []}
        version.change_description = None
        version.name = None
        version.created_by = uuid4()
        version.created_at = MagicMock()
        version.updated_at = MagicMock()
        version.deleted_at = None
        version.deleted_by = None

        result = await _build_workflow_with_version_response(workflow, version, mock_service)

        assert result.published_version_number == 1
        assert result.version is not None

    @pytest.mark.asyncio
    async def test_builds_response_without_published_version_number(self) -> None:
        """published_version_number stays None when version is not the published one."""
        from syntara.workflows.router import _build_workflow_with_version_response

        mock_service = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_service.session.exec = AsyncMock(return_value=mock_result)
        mock_service.get_publish_context.return_value = (set(), {})
        workflow = MagicMock()
        workflow.id = uuid4()
        workflow.name = "test"
        workflow.description = None
        workflow.labels = {}
        workflow.current_version = 2
        workflow.is_builtin = False
        workflow.is_enabled = True
        workflow.has_validation_issues = False
        workflow.published_version_id = uuid4()
        workflow.published_version_number = None
        workflow.created_by = uuid4()
        workflow.project_id = uuid4()
        workflow.created_at = MagicMock()
        workflow.updated_at = MagicMock()
        workflow.deleted_at = None
        workflow.deleted_by = None
        workflow.updated_by = None

        version = MagicMock()
        version.id = uuid4()
        version.workflow_id = workflow.id
        version.version = 2
        version.schema_version = "2.0.0"
        version.workflow_definition = {"nodes": []}
        version.change_description = None
        version.name = None
        version.created_by = uuid4()
        version.created_at = MagicMock()
        version.updated_at = MagicMock()
        version.deleted_at = None
        version.deleted_by = None

        result = await _build_workflow_with_version_response(workflow, version, mock_service)

        assert result.published_version_number is None


class TestPopulatePublishedVersionNumber:
    """Tests for _populate_published_version_number helper."""

    @pytest.mark.asyncio
    async def test_queries_db_when_current_version_differs(self) -> None:
        """When current version != published version, queries DB for published version number."""
        from syntara.workflows.router import _populate_published_version_number

        pub_version_id = uuid4()
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = 5
        mock_session.exec = AsyncMock(return_value=mock_result)

        workflow = MagicMock()
        workflow.published_version_id = pub_version_id

        version = MagicMock()
        version.id = uuid4()  # Different from published_version_id

        workflow_read = MagicMock()

        await _populate_published_version_number(workflow_read, workflow, version, mock_session)

        assert workflow_read.published_version_number == 5
        mock_session.exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_no_published_version(self) -> None:
        """When workflow has no published version, returns without setting."""
        from syntara.workflows.router import _populate_published_version_number

        mock_session = AsyncMock()
        workflow = MagicMock()
        workflow.published_version_id = None

        version = MagicMock()
        version.id = uuid4()

        workflow_read = MagicMock()

        await _populate_published_version_number(workflow_read, workflow, version, mock_session)

        mock_session.exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_sets_version_directly_when_ids_match(self) -> None:
        """When the version is the published version, sets number from version object."""
        from syntara.workflows.router import _populate_published_version_number

        version_id = uuid4()
        mock_session = AsyncMock()

        workflow = MagicMock()
        workflow.published_version_id = version_id

        version = MagicMock()
        version.id = version_id
        version.version = 3

        workflow_read = MagicMock()

        await _populate_published_version_number(workflow_read, workflow, version, mock_session)

        assert workflow_read.published_version_number == 3
        mock_session.exec.assert_not_called()


class TestPublishImplicitUnpublishEvent:
    """Tests for the implicit unpublish event when publishing a new version."""

    @pytest.mark.asyncio
    async def test_publish_when_another_version_published_creates_two_events(
        self, mock_service: WorkflowService
    ) -> None:
        """Publishing when another version is already published creates unpublish + publish events."""
        workflow_id = uuid4()
        old_published_id = uuid4()
        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.is_builtin = False
        mock_workflow.published_version_id = old_published_id
        mock_workflow.current_version = 2
        mock_workflow.name = "test-wf"
        mock_workflow.project_id = uuid4()

        mock_version = MagicMock()
        mock_version.id = uuid4()
        mock_version.version = 2
        mock_version.workflow_definition = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [{"id": "n1", "type": "script", "parameters": {"language": "python", "code": "pass"}}],
            "edges": [{"from": "t1", "to": "n1"}],
        }

        with (
            patch.object(mock_service, "_get_workflow_for_update", return_value=mock_workflow),
            patch.object(mock_service, "_get_version_or_none", return_value=mock_version),
            patch.object(mock_service, "_flush_with_duplicate_check", new_callable=AsyncMock),
            patch.object(mock_service, "_sync_all_trigger_types", new_callable=AsyncMock),
            patch.object(mock_service, "_sync_scheduled_triggers", new_callable=AsyncMock),
            patch.object(mock_service.session, "commit", new_callable=AsyncMock),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService"),
        ):
            await mock_service.publish_workflow_version(workflow_id, version=2)

        from syntara.workflows.models.workflow_publish_event import PublishAction, WorkflowPublishEvent

        mock_add = mock_service.session.add
        added_objects = [call.args[0] for call in mock_add.call_args_list]  # type: ignore[attr-defined]
        publish_events = [obj for obj in added_objects if isinstance(obj, WorkflowPublishEvent)]
        assert len(publish_events) == 2
        actions = {e.action for e in publish_events}
        assert actions == {PublishAction.PUBLISHED, PublishAction.UNPUBLISHED}

    @pytest.mark.asyncio
    async def test_publish_when_no_version_published_creates_one_event(self, mock_service: WorkflowService) -> None:
        """Publishing when no version is published creates only a publish event."""
        workflow_id = uuid4()
        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.is_builtin = False
        mock_workflow.published_version_id = None
        mock_workflow.current_version = 1
        mock_workflow.name = "test-wf"
        mock_workflow.project_id = uuid4()

        mock_version = MagicMock()
        mock_version.id = uuid4()
        mock_version.version = 1
        mock_version.workflow_definition = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [{"id": "n1", "type": "script", "parameters": {"language": "python", "code": "pass"}}],
            "edges": [{"from": "t1", "to": "n1"}],
        }

        with (
            patch.object(mock_service, "_get_workflow_for_update", return_value=mock_workflow),
            patch.object(mock_service, "_get_version_or_none", return_value=mock_version),
            patch.object(mock_service, "_flush_with_duplicate_check", new_callable=AsyncMock),
            patch.object(mock_service, "_sync_all_trigger_types", new_callable=AsyncMock),
            patch.object(mock_service, "_sync_scheduled_triggers", new_callable=AsyncMock),
            patch.object(mock_service.session, "commit", new_callable=AsyncMock),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService"),
        ):
            await mock_service.publish_workflow_version(workflow_id, version=1)

        from syntara.workflows.models.workflow_publish_event import PublishAction, WorkflowPublishEvent

        mock_add = mock_service.session.add
        added_objects = [call.args[0] for call in mock_add.call_args_list]  # type: ignore[attr-defined]
        publish_events = [obj for obj in added_objects if isinstance(obj, WorkflowPublishEvent)]
        assert len(publish_events) == 1
        assert publish_events[0].action == PublishAction.PUBLISHED

    @pytest.mark.asyncio
    async def test_publish_returns_warning_when_scheduled_trigger_sync_fails(
        self, mock_service: WorkflowService
    ) -> None:
        """Publish succeeds but returns a warning when Temporal is unavailable for scheduled triggers."""
        workflow_id = uuid4()
        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.is_builtin = False
        mock_workflow.published_version_id = None
        mock_workflow.current_version = 1
        mock_workflow.name = "test-wf"
        mock_workflow.project_id = uuid4()

        mock_version = MagicMock()
        mock_version.id = uuid4()
        mock_version.version = 1
        mock_version.workflow_definition = {
            "schema_version": "2.0.0",
            "name": "with-scheduled",
            "triggers": [
                {
                    "id": "t1",
                    "type": "scheduled_trigger",
                    "parameters": {"schedule_type": "cron", "cron": "0 * * * *"},
                },
            ],
            "nodes": [{"id": "n1", "type": "script", "parameters": {"language": "python", "code": "pass"}}],
            "edges": [{"from": "t1", "to": "n1"}],
        }

        with (
            patch.object(mock_service, "_get_workflow_for_update", return_value=mock_workflow),
            patch.object(mock_service, "_get_version_or_none", return_value=mock_version),
            patch.object(mock_service, "_flush_with_duplicate_check", new_callable=AsyncMock),
            patch.object(mock_service, "_sync_all_trigger_types", new_callable=AsyncMock),
            patch.object(
                mock_service,
                "_sync_scheduled_triggers",
                new_callable=AsyncMock,
                side_effect=ScheduledTriggerSyncError(str(workflow_id), 1),
            ),
            patch.object(mock_service.session, "commit", new_callable=AsyncMock),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService"),
        ):
            workflow, _version, warning = await mock_service.publish_workflow_version(workflow_id, version=1)

        assert workflow == mock_workflow
        assert warning == (
            "Scheduled triggers could not be activated because the scheduling service is "
            "temporarily unavailable. They will be activated automatically when the service recovers."
        )


def _published_workflow_mock() -> tuple[UUID, MagicMock]:
    workflow_id = uuid4()
    mock_workflow = MagicMock()
    mock_workflow.id = workflow_id
    mock_workflow.is_builtin = False
    mock_workflow.published_version_id = uuid4()
    mock_workflow.is_enabled = True
    mock_workflow.name = "test-wf"
    mock_workflow.project_id = uuid4()
    return workflow_id, mock_workflow


def _deleted_workflow_mock() -> tuple[UUID, MagicMock]:
    workflow_id = uuid4()
    mock_workflow = MagicMock()
    mock_workflow.id = workflow_id
    mock_workflow.is_builtin = False
    mock_workflow.name = "test-wf"
    mock_workflow.project_id = uuid4()
    return workflow_id, mock_workflow


def _configure_scheduled_service(mock_sched_cls: MagicMock, *, delete: object) -> None:
    mock_sched_cls.return_value.get_client = AsyncMock(return_value=MagicMock())
    mock_sched_cls.return_value.delete_triggers_for_workflow = delete


class TestScheduledTriggerSyncGracefulDegradation:
    """Unpublish and delete succeed even when scheduled trigger cleanup fails.

    Temporal cleanup is detached after the DB commit so a hung or failing
    delete cannot 504 the HTTP request (AAP-87692). The work must not be
    cancelled, and connect must not hold ``_client_lock``.
    """

    @pytest.fixture(autouse=True)
    async def _cleanup_detached_schedule_deletes(self) -> AsyncGenerator[None, None]:
        with patch.object(WorkflowService, "_workflow_is_published", new=AsyncMock(return_value=False)):
            yield
            await _cancel_background_deletes()

    @pytest.mark.asyncio
    async def test_unpublish_succeeds_when_trigger_delete_fails(self, mock_service: WorkflowService) -> None:
        workflow_id, mock_workflow = _published_workflow_mock()

        with (
            patch.object(mock_service, "_get_workflow_for_update", return_value=mock_workflow),
            patch.object(mock_service.session, "get", new_callable=AsyncMock, return_value=MagicMock()),
            patch.object(mock_service.session, "commit", new_callable=AsyncMock),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService") as mock_wh_cls,
            patch("syntara.workflows.services.workflow_service.ScheduledTriggerService") as mock_sched_cls,
            patch("syntara.workflows.services.workflow_service.logger") as mock_logger,
        ):
            mock_wh_cls.return_value.sync_webhook_triggers = AsyncMock()
            _configure_scheduled_service(
                mock_sched_cls,
                delete=AsyncMock(side_effect=ScheduledTriggerSyncError(str(workflow_id), 0)),
            )
            result = await mock_service.unpublish_workflow(workflow_id)
            await _finish_background_deletes()

        assert result == mock_workflow
        warning_messages = [call.args[0] for call in mock_logger.warning.call_args_list]
        assert any("Best-effort scheduled trigger deletion failed" in msg for msg in warning_messages)

    @pytest.mark.asyncio
    async def test_delete_succeeds_when_trigger_delete_fails(self, mock_service: WorkflowService) -> None:
        workflow_id, mock_workflow = _deleted_workflow_mock()

        with (
            patch.object(mock_service, "get_workflow_by_id", new_callable=AsyncMock, return_value=mock_workflow),
            patch.object(mock_service.session, "commit", new_callable=AsyncMock),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService") as mock_wh_cls,
            patch("syntara.workflows.services.workflow_service.ScheduledTriggerService") as mock_sched_cls,
        ):
            mock_wh_cls.return_value.delete_triggers_for_workflow = AsyncMock()
            _configure_scheduled_service(
                mock_sched_cls,
                delete=AsyncMock(side_effect=ScheduledTriggerSyncError(str(workflow_id), 0)),
            )
            await mock_service.delete_workflow(workflow_id)
            await _finish_background_deletes()

    @pytest.mark.asyncio
    async def test_unpublish_logs_unexpected_delete_error(self, mock_service: WorkflowService) -> None:
        workflow_id, mock_workflow = _published_workflow_mock()

        with (
            patch.object(mock_service, "_get_workflow_for_update", return_value=mock_workflow),
            patch.object(mock_service.session, "get", new_callable=AsyncMock, return_value=MagicMock()),
            patch.object(mock_service.session, "commit", new_callable=AsyncMock),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService") as mock_wh_cls,
            patch("syntara.workflows.services.workflow_service.ScheduledTriggerService") as mock_sched_cls,
            patch("syntara.workflows.services.workflow_service.logger") as mock_logger,
        ):
            mock_wh_cls.return_value.sync_webhook_triggers = AsyncMock()
            _configure_scheduled_service(
                mock_sched_cls,
                delete=AsyncMock(side_effect=RuntimeError("temporal exploded")),
            )
            result = await mock_service.unpublish_workflow(workflow_id)
            await _finish_background_deletes()

        assert result == mock_workflow
        warning_messages = [call.args[0] for call in mock_logger.warning.call_args_list]
        assert any("Best-effort scheduled trigger deletion failed" in msg for msg in warning_messages)

    @pytest.mark.asyncio
    async def test_unpublish_returns_when_trigger_delete_hangs(self, mock_service: WorkflowService) -> None:
        """HTTP unpublish must return after commit even if Temporal never answers.

        The delete task must keep running: cancelling it would interrupt
        in-flight Temporal cleanup.
        """
        workflow_id, mock_workflow = _published_workflow_mock()
        delete_started = asyncio.Event()

        async def _hang(*_args: object, **_kwargs: object) -> NoReturn:
            delete_started.set()
            await asyncio.Event().wait()
            raise AssertionError

        with (
            patch.object(mock_service, "_get_workflow_for_update", return_value=mock_workflow),
            patch.object(mock_service.session, "get", new_callable=AsyncMock, return_value=MagicMock()),
            patch.object(mock_service.session, "commit", new_callable=AsyncMock) as mock_commit,
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService") as mock_wh_cls,
            patch("syntara.workflows.services.workflow_service.ScheduledTriggerService") as mock_sched_cls,
        ):
            mock_wh_cls.return_value.sync_webhook_triggers = AsyncMock()
            _configure_scheduled_service(mock_sched_cls, delete=_hang)
            started = time.monotonic()
            try:
                result = await asyncio.wait_for(mock_service.unpublish_workflow(workflow_id), timeout=1.0)
                await asyncio.wait_for(delete_started.wait(), timeout=1.0)
                elapsed = time.monotonic() - started
                pending = _pending_delete_tasks()
                was_cancelled = pending[0].cancelled()
                was_done = pending[0].done()
                mock_commit.assert_awaited()
                mock_sched_cls.assert_called()
            finally:
                await _cancel_background_deletes()

        assert result == mock_workflow
        assert mock_workflow.published_version_id is None
        assert mock_workflow.is_enabled is False
        assert elapsed < 0.5
        assert len(pending) == 1
        assert not was_done
        assert not was_cancelled

    @pytest.mark.asyncio
    async def test_delete_returns_when_trigger_delete_hangs(self, mock_service: WorkflowService) -> None:
        workflow_id, mock_workflow = _deleted_workflow_mock()
        delete_started = asyncio.Event()

        async def _hang(*_args: object, **_kwargs: object) -> NoReturn:
            delete_started.set()
            await asyncio.Event().wait()
            raise AssertionError

        with (
            patch.object(mock_service, "get_workflow_by_id", new_callable=AsyncMock, return_value=mock_workflow),
            patch.object(mock_service.session, "commit", new_callable=AsyncMock) as mock_commit,
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService") as mock_wh_cls,
            patch("syntara.workflows.services.workflow_service.ScheduledTriggerService") as mock_sched_cls,
        ):
            mock_wh_cls.return_value.delete_triggers_for_workflow = AsyncMock()
            _configure_scheduled_service(mock_sched_cls, delete=_hang)
            started = time.monotonic()
            try:
                await asyncio.wait_for(mock_service.delete_workflow(workflow_id), timeout=1.0)
                await asyncio.wait_for(delete_started.wait(), timeout=1.0)
                elapsed = time.monotonic() - started
                pending = _pending_delete_tasks()
                was_cancelled = pending[0].cancelled()
                was_done = pending[0].done()
                mock_commit.assert_awaited()
            finally:
                await _cancel_background_deletes()

        assert elapsed < 0.5
        assert len(pending) == 1
        assert not was_done
        assert not was_cancelled

    @pytest.mark.asyncio
    async def test_unpublish_skips_delete_when_workflow_was_republished(self, mock_service: WorkflowService) -> None:
        workflow_id, mock_workflow = _published_workflow_mock()

        with (
            patch.object(mock_service, "_get_workflow_for_update", return_value=mock_workflow),
            patch.object(mock_service.session, "get", new_callable=AsyncMock, return_value=MagicMock()),
            patch.object(mock_service.session, "commit", new_callable=AsyncMock),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService") as mock_wh_cls,
            patch("syntara.workflows.services.workflow_service.ScheduledTriggerService") as mock_sched_cls,
            patch.object(WorkflowService, "_workflow_is_published", new=AsyncMock(return_value=True)),
        ):
            mock_wh_cls.return_value.sync_webhook_triggers = AsyncMock()
            result = await mock_service.unpublish_workflow(workflow_id)
            await _finish_background_deletes()
            mock_sched_cls.assert_not_called()

        assert result == mock_workflow

    @pytest.mark.asyncio
    async def test_unpublish_skips_delete_if_republished_after_connect(self, mock_service: WorkflowService) -> None:
        """A publish that lands while Temporal is connecting must keep new schedules."""
        workflow_id, mock_workflow = _published_workflow_mock()

        with (
            patch.object(mock_service, "_get_workflow_for_update", return_value=mock_workflow),
            patch.object(mock_service.session, "get", new_callable=AsyncMock, return_value=MagicMock()),
            patch.object(mock_service.session, "commit", new_callable=AsyncMock),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService") as mock_wh_cls,
            patch("syntara.workflows.services.workflow_service.ScheduledTriggerService") as mock_sched_cls,
            patch.object(
                WorkflowService,
                "_workflow_is_published",
                new=AsyncMock(side_effect=[False, True]),
            ),
        ):
            mock_wh_cls.return_value.sync_webhook_triggers = AsyncMock()
            _configure_scheduled_service(mock_sched_cls, delete=AsyncMock())
            result = await mock_service.unpublish_workflow(workflow_id)
            await _finish_background_deletes()
            mock_sched_cls.return_value.get_client.assert_awaited()
            mock_sched_cls.return_value.delete_triggers_for_workflow.assert_not_called()

        assert result == mock_workflow

    @pytest.mark.asyncio
    async def test_unpublish_passes_republish_abort_into_delete(self, mock_service: WorkflowService) -> None:
        """List/delete must keep re-checking publish state after connect."""
        workflow_id, mock_workflow = _published_workflow_mock()

        with (
            patch.object(mock_service, "_get_workflow_for_update", return_value=mock_workflow),
            patch.object(mock_service.session, "get", new_callable=AsyncMock, return_value=MagicMock()),
            patch.object(mock_service.session, "commit", new_callable=AsyncMock),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService") as mock_wh_cls,
            patch("syntara.workflows.services.workflow_service.ScheduledTriggerService") as mock_sched_cls,
            patch.object(
                WorkflowService,
                "_workflow_is_published",
                new=AsyncMock(return_value=False),
            ),
        ):
            mock_wh_cls.return_value.sync_webhook_triggers = AsyncMock()
            _configure_scheduled_service(mock_sched_cls, delete=AsyncMock())
            result = await mock_service.unpublish_workflow(workflow_id)
            await _finish_background_deletes()
            kwargs = mock_sched_cls.return_value.delete_triggers_for_workflow.await_args.kwargs
            assert callable(kwargs.get("should_abort"))
            assert await kwargs["should_abort"]() is False

        assert result == mock_workflow

    @pytest.mark.asyncio
    async def test_unpublish_returns_when_connect_hangs_without_holding_lock(
        self, mock_service: WorkflowService
    ) -> None:
        workflow_id, mock_workflow = _published_workflow_mock()
        connect_started = asyncio.Event()

        async def _hang_connect(*_args: object, **_kwargs: object) -> NoReturn:
            connect_started.set()
            await asyncio.Event().wait()
            raise AssertionError

        with (
            patch.object(mock_service, "_get_workflow_for_update", return_value=mock_workflow),
            patch.object(mock_service.session, "get", new_callable=AsyncMock, return_value=MagicMock()),
            patch.object(mock_service.session, "commit", new_callable=AsyncMock) as mock_commit,
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService") as mock_wh_cls,
            patch(
                "syntara.workflows.services.scheduled_trigger_service.Client.connect",
                new=_hang_connect,
            ),
        ):
            mock_wh_cls.return_value.sync_webhook_triggers = AsyncMock()
            try:
                result = await asyncio.wait_for(mock_service.unpublish_workflow(workflow_id), timeout=1.0)
                await asyncio.wait_for(connect_started.wait(), timeout=1.0)
                mock_commit.assert_awaited()
                assert not scheduled_trigger_service_mod._client_lock.locked()
                pending = _pending_delete_tasks()
                assert len(pending) == 1
                assert not pending[0].done()
            finally:
                await _cancel_background_deletes()
                connect_task = scheduled_trigger_service_mod._connect_task
                if connect_task is not None:
                    connect_task.cancel()
                    await asyncio.gather(connect_task, return_exceptions=True)
                    scheduled_trigger_service_mod._connect_task = None
                    scheduled_trigger_service_mod._connect_started_at = None

        assert result == mock_workflow
        assert mock_workflow.published_version_id is None

    @pytest.mark.asyncio
    async def test_slow_delete_still_completes_after_unpublish_returns(self, mock_service: WorkflowService) -> None:
        """A delete that would have exceeded a request-path bound must still finish."""
        workflow_id, mock_workflow = _published_workflow_mock()
        deleted: list[str] = []
        delete_started = asyncio.Event()
        release_delete = asyncio.Event()

        async def _gated(*_args: object, **kwargs: object) -> int:
            delete_started.set()
            await release_delete.wait()
            deleted.append(str(kwargs["workflow_id"]))
            return 1

        with (
            patch.object(mock_service, "_get_workflow_for_update", return_value=mock_workflow),
            patch.object(mock_service.session, "get", new_callable=AsyncMock, return_value=MagicMock()),
            patch.object(mock_service.session, "commit", new_callable=AsyncMock) as mock_commit,
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService") as mock_wh_cls,
            patch("syntara.workflows.services.workflow_service.ScheduledTriggerService") as mock_sched_cls,
        ):
            mock_wh_cls.return_value.sync_webhook_triggers = AsyncMock()
            _configure_scheduled_service(mock_sched_cls, delete=_gated)
            result = await mock_service.unpublish_workflow(workflow_id)
            await asyncio.wait_for(delete_started.wait(), timeout=1.0)
            mock_commit.assert_awaited()
            assert deleted == []
            release_delete.set()
            await _finish_background_deletes()

        assert result == mock_workflow
        assert deleted == [str(workflow_id)]

    @pytest.mark.asyncio
    async def test_unpublish_does_not_start_delete_when_commit_fails(self, mock_service: WorkflowService) -> None:
        workflow_id, mock_workflow = _published_workflow_mock()

        with (
            patch.object(mock_service, "_get_workflow_for_update", return_value=mock_workflow),
            patch.object(mock_service.session, "get", new_callable=AsyncMock, return_value=MagicMock()),
            patch.object(mock_service.session, "commit", new_callable=AsyncMock, side_effect=RuntimeError("db down")),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService") as mock_wh_cls,
            patch("syntara.workflows.services.workflow_service.ScheduledTriggerService") as mock_sched_cls,
        ):
            mock_wh_cls.return_value.sync_webhook_triggers = AsyncMock()
            with pytest.raises(RuntimeError, match="db down"):
                await mock_service.unpublish_workflow(workflow_id)
            mock_sched_cls.assert_not_called()

        assert _pending_delete_tasks() == []

    @pytest.mark.asyncio
    async def test_delete_does_not_start_schedule_cleanup_when_commit_fails(
        self, mock_service: WorkflowService
    ) -> None:
        workflow_id, mock_workflow = _deleted_workflow_mock()

        with (
            patch.object(mock_service, "get_workflow_by_id", new_callable=AsyncMock, return_value=mock_workflow),
            patch.object(mock_service.session, "commit", new_callable=AsyncMock, side_effect=RuntimeError("db down")),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService") as mock_wh_cls,
            patch("syntara.workflows.services.workflow_service.ScheduledTriggerService") as mock_sched_cls,
        ):
            mock_wh_cls.return_value.delete_triggers_for_workflow = AsyncMock()
            with pytest.raises(RuntimeError, match="db down"):
                await mock_service.delete_workflow(workflow_id)
            mock_sched_cls.assert_not_called()

        assert _pending_delete_tasks() == []


def _workflow_session_ctx(workflow: MagicMock | None, *, error: Exception | None = None) -> MagicMock:
    session = AsyncMock()
    session.get = AsyncMock(side_effect=error) if error is not None else AsyncMock(return_value=workflow)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


class TestWorkflowIsPublished:
    """Detached cleanup must keep schedules if a later publish won the race."""

    @pytest.mark.asyncio
    async def test_true_when_live_and_published(self) -> None:
        workflow = MagicMock()
        workflow.deleted_at = None
        workflow.published_version_id = uuid4()
        with patch(
            "syntara.workflows.services.workflow_service.AsyncSessionLocal",
            return_value=_workflow_session_ctx(workflow),
        ):
            assert await WorkflowService._workflow_is_published(uuid4()) is True

    @pytest.mark.asyncio
    async def test_false_when_unpublished(self) -> None:
        workflow = MagicMock()
        workflow.deleted_at = None
        workflow.published_version_id = None
        with patch(
            "syntara.workflows.services.workflow_service.AsyncSessionLocal",
            return_value=_workflow_session_ctx(workflow),
        ):
            assert await WorkflowService._workflow_is_published(uuid4()) is False

    @pytest.mark.asyncio
    async def test_false_when_soft_deleted(self) -> None:
        workflow = MagicMock()
        workflow.deleted_at = MagicMock()
        workflow.published_version_id = uuid4()
        with patch(
            "syntara.workflows.services.workflow_service.AsyncSessionLocal",
            return_value=_workflow_session_ctx(workflow),
        ):
            assert await WorkflowService._workflow_is_published(uuid4()) is False

    @pytest.mark.asyncio
    async def test_false_when_missing(self) -> None:
        with patch(
            "syntara.workflows.services.workflow_service.AsyncSessionLocal",
            return_value=_workflow_session_ctx(None),
        ):
            assert await WorkflowService._workflow_is_published(uuid4()) is False

    @pytest.mark.asyncio
    async def test_true_when_db_read_fails(self) -> None:
        with patch(
            "syntara.workflows.services.workflow_service.AsyncSessionLocal",
            return_value=_workflow_session_ctx(None, error=RuntimeError("db down")),
        ):
            assert await WorkflowService._workflow_is_published(uuid4()) is True


class TestPublishRejectsInvalidScheduledTriggerConfig:
    """Publish must reject invalid scheduled trigger configs before mutation.

    Invalid IANA timezones and invalid ISO 8601 interval strings are rejected
    by ``workflow_validator.collect_findings`` (via
    ``collect_scheduled_trigger_config_findings``, which calls
    ``ScheduledTriggerConfig.model_validate``) before any publish mutation.
    ``ScheduledTriggerService.validate_trigger_configs`` is a raise-first
    wrapper over that same helper, so verify, publish, and Temporal sync
    share one semantic contract.
    """

    @pytest.mark.asyncio
    async def test_publish_rejects_invalid_timezone_before_mutation(self, mock_service: WorkflowService) -> None:
        """Publish must fail during collect_findings before mutating published_version_id."""
        workflow_id = uuid4()
        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.is_builtin = False
        mock_workflow.published_version_id = None
        mock_workflow.current_version = 1
        mock_workflow.name = "scheduled-wf"
        mock_workflow.project_id = uuid4()

        mock_version = MagicMock()
        mock_version.id = uuid4()
        mock_version.version = 1
        mock_version.workflow_definition = {
            "schema_version": "2.0.0",
            "name": "timezone-test",
            "triggers": [
                {
                    "id": "sched_1",
                    "type": "scheduled_trigger",
                    "parameters": {
                        "schedule_type": "cron",
                        "cron": "0 9 * * *",
                        "timezone": "Invalid/Not_A_Real_Zone",
                    },
                },
            ],
            "nodes": [{"id": "n1", "type": "script", "parameters": {"language": "python", "code": "pass"}}],
            "edges": [{"from": "sched_1", "to": "n1"}],
        }

        with (
            patch.object(mock_service, "_get_workflow_for_update", return_value=mock_workflow),
            patch.object(mock_service, "_get_version_or_none", return_value=mock_version),
            patch.object(mock_service.session, "commit", new_callable=AsyncMock) as mock_commit,
            pytest.raises(WorkflowPublishValidationError) as exc_info,
        ):
            await mock_service.publish_workflow_version(workflow_id, version=1)

        assert any("scheduled trigger config" in f.message for f in exc_info.value.validation_result.findings)
        assert mock_workflow.published_version_id is None
        mock_commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_publish_rejects_invalid_interval_before_mutation(self, mock_service: WorkflowService) -> None:
        """Publish must reject an invalid ISO 8601 interval before mutating published_version_id.

        Interval was previously an unconstrained string that only failed much
        later in ``config_to_temporal_schedule`` -> ``parse_iso8601_interval``
        (after ``session.commit()``), recreating the published-in-DB /
        error-to-user inconsistency this bugfix targets.
        """
        workflow_id = uuid4()
        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.is_builtin = False
        mock_workflow.published_version_id = None
        mock_workflow.current_version = 1
        mock_workflow.name = "scheduled-wf"
        mock_workflow.project_id = uuid4()

        mock_version = MagicMock()
        mock_version.id = uuid4()
        mock_version.version = 1
        mock_version.workflow_definition = {
            "schema_version": "2.0.0",
            "name": "interval-test",
            "triggers": [
                {
                    "id": "sched_1",
                    "type": "scheduled_trigger",
                    "parameters": {
                        "schedule_type": "interval",
                        "interval": "not-an-interval",
                    },
                },
            ],
            "nodes": [{"id": "n1", "type": "script", "parameters": {"language": "python", "code": "pass"}}],
            "edges": [{"from": "sched_1", "to": "n1"}],
        }

        with (
            patch.object(mock_service, "_get_workflow_for_update", return_value=mock_workflow),
            patch.object(mock_service, "_get_version_or_none", return_value=mock_version),
            patch.object(mock_service.session, "commit", new_callable=AsyncMock) as mock_commit,
            pytest.raises(WorkflowPublishValidationError) as exc_info,
        ):
            await mock_service.publish_workflow_version(workflow_id, version=1)

        assert any("scheduled trigger config" in f.message for f in exc_info.value.validation_result.findings)
        assert mock_workflow.published_version_id is None
        mock_commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_publish_succeeds_with_valid_timezone(self, mock_service: WorkflowService) -> None:
        """Publish succeeds when scheduled trigger has a valid IANA timezone."""
        workflow_id = uuid4()
        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.is_builtin = False
        mock_workflow.published_version_id = None
        mock_workflow.current_version = 1
        mock_workflow.name = "scheduled-wf"
        mock_workflow.project_id = uuid4()

        mock_version = MagicMock()
        mock_version.id = uuid4()
        mock_version.version = 1
        mock_version.workflow_definition = {
            "schema_version": "2.0.0",
            "name": "timezone-test",
            "triggers": [
                {
                    "id": "sched_1",
                    "type": "scheduled_trigger",
                    "parameters": {
                        "schedule_type": "cron",
                        "cron": "0 9 * * *",
                        "timezone": "America/New_York",
                    },
                },
            ],
            "nodes": [{"id": "n1", "type": "script", "parameters": {"language": "python", "code": "pass"}}],
            "edges": [{"from": "sched_1", "to": "n1"}],
        }

        with (
            patch.object(mock_service, "_get_workflow_for_update", return_value=mock_workflow),
            patch.object(mock_service, "_get_version_or_none", return_value=mock_version),
            patch.object(mock_service, "_flush_with_duplicate_check", new_callable=AsyncMock),
            patch.object(mock_service, "_sync_all_trigger_types", new_callable=AsyncMock),
            patch.object(mock_service, "_sync_scheduled_triggers", new_callable=AsyncMock),
            patch.object(mock_service.session, "commit", new_callable=AsyncMock),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService"),
        ):
            workflow, _version, _warning = await mock_service.publish_workflow_version(workflow_id, version=1)

        assert workflow.published_version_id == mock_version.id


class TestValidateTriggerConfigsSharedContract:
    """Unit tests for ScheduledTriggerService.validate_trigger_configs.

    Raise-first wrapper over ``collect_scheduled_trigger_config_findings``.
    """

    def test_valid_timezone_passes(self) -> None:
        definition = {
            "triggers": [
                {
                    "id": "t1",
                    "type": "scheduled_trigger",
                    "parameters": {"schedule_type": "cron", "cron": "0 * * * *", "timezone": "UTC"},
                }
            ]
        }
        ScheduledTriggerService.validate_trigger_configs(definition)

    def test_invalid_timezone_raises(self) -> None:
        definition = {
            "triggers": [
                {
                    "id": "t1",
                    "type": "scheduled_trigger",
                    "parameters": {
                        "schedule_type": "cron",
                        "cron": "0 * * * *",
                        "timezone": "Fake/Timezone",
                    },
                }
            ]
        }
        with pytest.raises(TriggerValidationError, match=r"Invalid.*scheduled trigger config"):
            ScheduledTriggerService.validate_trigger_configs(definition)

    def test_no_scheduled_triggers_passes(self) -> None:
        definition = {
            "triggers": [
                {"id": "t1", "type": "manual_trigger", "parameters": {}},
            ]
        }
        ScheduledTriggerService.validate_trigger_configs(definition)

    def test_missing_trigger_id_still_validates_config(self) -> None:
        """Missing id must not skip ScheduledTriggerConfig validation."""
        definition = {
            "triggers": [
                {
                    "type": "scheduled_trigger",
                    "parameters": {"schedule_type": "cron", "cron": "0 * * * *", "timezone": "Fake/Tz"},
                }
            ]
        }
        with pytest.raises(TriggerValidationError, match=r"Invalid.*scheduled trigger config.*<missing id>"):
            ScheduledTriggerService.validate_trigger_configs(definition)

    def test_non_string_trigger_id_uses_missing_id_placeholder(self) -> None:
        """Non-string ids share the same display policy as collect_findings."""
        definition = {
            "triggers": [
                {
                    "id": 123,
                    "type": "scheduled_trigger",
                    "parameters": {"schedule_type": "cron", "cron": "0 * * * *", "timezone": "Fake/Tz"},
                }
            ]
        }
        with pytest.raises(TriggerValidationError, match=r"<missing id>"):
            ScheduledTriggerService.validate_trigger_configs(definition)

    def test_raise_message_matches_collect_findings(self) -> None:
        """Raise-first wrapper must surface the same message as the shared helper."""
        from syntara.workflows.validators import collect_scheduled_trigger_config_findings, workflow_validator

        definition = {
            "schema_version": "2.0.0",
            "name": "shared-path-wf",
            "triggers": [
                {
                    "id": "sched_1",
                    "type": "scheduled_trigger",
                    "parameters": {
                        "schedule_type": "cron",
                        "cron": "0 * * * *",
                        "timezone": "Fake/Timezone",
                    },
                }
            ],
            "nodes": [{"id": "n1", "type": "script", "parameters": {"language": "python", "code": "pass"}}],
            "edges": [{"from": "sched_1", "to": "n1"}],
        }
        findings = collect_scheduled_trigger_config_findings(definition)
        assert findings
        with pytest.raises(TriggerValidationError) as exc_info:
            ScheduledTriggerService.validate_trigger_configs(definition)
        assert exc_info.value.message == findings[0].message
        result = workflow_validator.collect_findings(definition)
        scheduled = [f for f in result.findings if "scheduled trigger config" in f.message]
        assert scheduled
        assert scheduled[0].message == findings[0].message

    def test_null_timezone_passes(self) -> None:
        definition = {
            "triggers": [
                {
                    "id": "t1",
                    "type": "scheduled_trigger",
                    "parameters": {"schedule_type": "cron", "cron": "0 * * * *", "timezone": None},
                }
            ]
        }
        ScheduledTriggerService.validate_trigger_configs(definition)
