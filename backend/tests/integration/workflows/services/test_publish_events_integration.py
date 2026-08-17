"""Integration tests for the WorkflowPublishEvent lifecycle.

Verifies that publish and unpublish actions create correct event records
in the database, and that the version listing service correctly derives
status and timestamps from those events.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.workflows.models import Workflow, WorkflowVersion
from syntara.workflows.models.validation_finding import ValidationResult
from syntara.workflows.models.workflow_publish_event import PublishAction, WorkflowPublishEvent
from syntara.workflows.services.workflow_service import WorkflowService


def _mock_validator_valid() -> MagicMock:
    """Return a MagicMock for workflow_validator with collect_findings returning valid."""
    mock = MagicMock()
    mock.collect_findings.return_value = ValidationResult(is_valid=True, error_count=0, warning_count=0, findings=[])
    return mock


def _mock_webhook_service() -> MagicMock:
    """Create a mock WebhookTriggerService with async sync method."""
    svc = MagicMock()
    svc.return_value.sync_webhook_triggers = AsyncMock(return_value=[])
    return svc


_PATCH_VALIDATOR = "syntara.workflows.services.workflow_service.workflow_validator"
_PATCH_WEBHOOK_SVC = "syntara.workflows.services.workflow_service.WebhookTriggerService"


class _PublishEventsTestBase:
    """Shared helpers for publish-event integration tests."""

    _test_project_id: UUID

    @pytest.fixture(autouse=True)
    def _inject_project_id(self, test_project_id: UUID) -> None:
        self._test_project_id = test_project_id

    def _create_workflow_definition(self, **overrides: dict[str, Any]) -> dict[str, Any]:
        """Create a minimal valid V2 workflow definition."""
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "test-workflow",
            "description": "Test workflow",
            "triggers": [
                {
                    "id": "trigger_manual",
                    "type": "manual_trigger",
                    "parameters": {},
                }
            ],
            "nodes": [
                {
                    "id": "task1",
                    "name": "Task 1",
                    "type": "script",
                    "parameters": {
                        "language": "python",
                        "code": "print('hello')",
                    },
                }
            ],
            "edges": [
                {"from": "trigger_manual", "to": "task1"},
            ],
        }
        definition.update(overrides)
        return definition

    async def _create_and_publish(
        self,
        service: WorkflowService,
        session: AsyncSession,
        *,
        name: str = "test-workflow",
        version: int = 1,
    ) -> tuple[Workflow, WorkflowVersion]:
        """Create a workflow and publish the specified version.

        Returns the workflow and the published version.
        """
        workflow_def = self._create_workflow_definition()

        with patch(_PATCH_VALIDATOR, _mock_validator_valid()):
            workflow, _, _ = await service.create_workflow(
                name=name,
                description=None,
                labels={},
                workflow_definition=workflow_def,
                project_id=self._test_project_id,
            )

        with patch(_PATCH_WEBHOOK_SVC, _mock_webhook_service()):
            result_workflow, result_version, _warning = await service.publish_workflow_version(
                workflow_id=workflow.id,
                version=version,
            )

        return result_workflow, result_version

    async def _query_events(self, session: AsyncSession, workflow_id: UUID) -> list[WorkflowPublishEvent]:
        """Query all publish events for a workflow, ordered by creation time."""
        result = await session.exec(
            select(WorkflowPublishEvent)
            .where(WorkflowPublishEvent.workflow_id == workflow_id)
            .order_by(WorkflowPublishEvent.created_at)  # type: ignore[arg-type]
        )
        return list(result.all())


class TestPublishEventsCreation(_PublishEventsTestBase):
    """Test that publish/unpublish actions create the correct event records."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_publish_creates_published_event(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Publishing a version creates a single PUBLISHED event."""
        service = WorkflowService(test_db_session, test_user)
        workflow, published_version = await self._create_and_publish(
            service, test_db_session, name="publish-event-test"
        )

        events = await self._query_events(test_db_session, workflow.id)

        assert len(events) == 1
        assert events[0].action == PublishAction.PUBLISHED
        assert events[0].version_id == published_version.id
        assert events[0].workflow_id == workflow.id
        assert events[0].actor_id == test_user.id

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_publish_creates_implicit_unpublish_event(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Publishing v2 while v1 is published creates an implicit UNPUBLISHED event for v1."""
        service = WorkflowService(test_db_session, test_user)
        workflow, v1_published = await self._create_and_publish(
            service, test_db_session, name="implicit-unpublish-test"
        )

        # Create a second version with a different definition
        v2_def = self._create_workflow_definition(description="v2 definition")  # type: ignore[arg-type]
        with patch(_PATCH_VALIDATOR, _mock_validator_valid()):
            v2, _ = await service.create_workflow_version(workflow, v2_def, "v2 changes")
        assert v2 is not None

        # Publish v2
        with patch(_PATCH_WEBHOOK_SVC, _mock_webhook_service()):
            _, v2_published, _warning = await service.publish_workflow_version(
                workflow_id=workflow.id,
                version=v2.version,
            )

        events = await self._query_events(test_db_session, workflow.id)

        # Expect 3 events: PUBLISHED(v1), UNPUBLISHED(v1), PUBLISHED(v2)
        assert len(events) == 3

        assert events[0].action == PublishAction.PUBLISHED
        assert events[0].version_id == v1_published.id

        assert events[1].action == PublishAction.UNPUBLISHED
        assert events[1].version_id == v1_published.id

        assert events[2].action == PublishAction.PUBLISHED
        assert events[2].version_id == v2_published.id

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_unpublish_creates_unpublish_event(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Explicitly unpublishing creates an UNPUBLISHED event."""
        service = WorkflowService(test_db_session, test_user)
        workflow, published_version = await self._create_and_publish(
            service, test_db_session, name="unpublish-event-test"
        )

        with patch(_PATCH_WEBHOOK_SVC, _mock_webhook_service()):
            await service.unpublish_workflow(workflow_id=workflow.id)

        events = await self._query_events(test_db_session, workflow.id)

        # Expect 2 events: PUBLISHED(v1), UNPUBLISHED(v1)
        assert len(events) == 2

        assert events[0].action == PublishAction.PUBLISHED
        assert events[0].version_id == published_version.id

        assert events[1].action == PublishAction.UNPUBLISHED
        assert events[1].version_id == published_version.id
        assert events[1].actor_id == test_user.id

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_republish_creates_new_published_event(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Publish, unpublish, then republish creates two PUBLISHED events."""
        service = WorkflowService(test_db_session, test_user)
        workflow, published_version = await self._create_and_publish(
            service, test_db_session, name="republish-event-test"
        )

        # Unpublish
        with patch(_PATCH_WEBHOOK_SVC, _mock_webhook_service()):
            await service.unpublish_workflow(workflow_id=workflow.id)

        # Republish v1
        with patch(_PATCH_WEBHOOK_SVC, _mock_webhook_service()):
            await service.publish_workflow_version(
                workflow_id=workflow.id,
                version=1,
            )

        events = await self._query_events(test_db_session, workflow.id)

        # Expect 3 events: PUBLISHED(v1), UNPUBLISHED(v1), PUBLISHED(v1 again)
        published_events = [e for e in events if e.action == PublishAction.PUBLISHED]
        unpublished_events = [e for e in events if e.action == PublishAction.UNPUBLISHED]

        assert len(published_events) == 2
        assert len(unpublished_events) == 1

        # Both PUBLISHED events should reference the same version
        assert published_events[0].version_id == published_version.id
        assert published_events[1].version_id == published_version.id


class TestPublishEventsQuery(_PublishEventsTestBase):
    """Test that version listing correctly derives status from publish events."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_list_versions_returns_correct_status(self, test_db_session: AsyncSession, test_user: User) -> None:
        """After publishing v1, listing shows v1 as published and v2 as draft."""
        service = WorkflowService(test_db_session, test_user)
        workflow, _ = await self._create_and_publish(service, test_db_session, name="status-listing-test")

        # Create v2 as a draft (different definition so it actually creates a new version)
        v2_def = self._create_workflow_definition(description="draft v2")  # type: ignore[arg-type]
        with patch(_PATCH_VALIDATOR, _mock_validator_valid()):
            v2 = await service.create_workflow_version(workflow, v2_def, "v2 draft")
        assert v2 is not None
        await test_db_session.flush()

        # List versions
        response = await service.list_workflow_versions_cursor(
            workflow_id=workflow.id,
            sort="created_at",
        )

        statuses = {r.version: r.status for r in response.resources}

        assert statuses[1] == "published"
        assert statuses[2] == "draft"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_list_versions_previously_published_status(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """After publishing v1 then v2, v1 becomes previously_published."""
        service = WorkflowService(test_db_session, test_user)
        workflow, _ = await self._create_and_publish(service, test_db_session, name="prev-published-test")

        # Create and publish v2
        v2_def = self._create_workflow_definition(description="v2 update")  # type: ignore[arg-type]
        with patch(_PATCH_VALIDATOR, _mock_validator_valid()):
            v2, _ = await service.create_workflow_version(workflow, v2_def, "v2 changes")
        assert v2 is not None

        with patch(_PATCH_WEBHOOK_SVC, _mock_webhook_service()):
            await service.publish_workflow_version(
                workflow_id=workflow.id,
                version=v2.version,
            )

        # List versions
        response = await service.list_workflow_versions_cursor(
            workflow_id=workflow.id,
            sort="created_at",
        )

        statuses = {r.version: r.status for r in response.resources}

        assert statuses[1] == "previously_published"
        assert statuses[2] == "published"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_populate_published_version_numbers(self, test_db_session: AsyncSession, test_user: User) -> None:
        """populate_published_version_numbers sets version number on WorkflowRead objects."""
        service = WorkflowService(test_db_session, test_user)

        # Create and publish two workflows
        _workflow_a, _ = await self._create_and_publish(service, test_db_session, name="pvn-test-a")
        workflow_b, _ = await self._create_and_publish(service, test_db_session, name="pvn-test-b")

        # Create a v2 for workflow_b and publish it
        v2_def = self._create_workflow_definition(description="b-v2")  # type: ignore[arg-type]
        with patch(_PATCH_VALIDATOR, _mock_validator_valid()):
            v2, _ = await service.create_workflow_version(workflow_b, v2_def, "v2")
        assert v2 is not None

        with patch(_PATCH_WEBHOOK_SVC, _mock_webhook_service()):
            await service.publish_workflow_version(
                workflow_id=workflow_b.id,
                version=v2.version,
            )

        # List workflows and populate version numbers
        result = await service.list_workflows_cursor(sort="name")
        await service.populate_published_version_numbers(result.resources)

        version_numbers = {w.name: w.published_version_number for w in result.resources}

        assert version_numbers["pvn-test-a"] == 1
        assert version_numbers["pvn-test-b"] == 2


class TestPublishTimestamps(_PublishEventsTestBase):
    """Test that publish/unpublish timestamps are correctly returned in version listings."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_publish_timestamps_returned_in_version_list(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """After publishing v1, last_published_at is set in version list response."""
        service = WorkflowService(test_db_session, test_user)
        workflow, _ = await self._create_and_publish(service, test_db_session, name="timestamps-test")

        response = await service.list_workflow_versions_cursor(
            workflow_id=workflow.id,
            sort="created_at",
        )

        assert len(response.resources) == 1
        version_read = response.resources[0]
        assert version_read.status == "published"
        assert version_read.last_published_at is not None
        # Since it is currently published, last_unpublished_at should be None
        assert version_read.last_unpublished_at is None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_unpublish_timestamp_suppressed_on_republish(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """After publish -> unpublish -> republish, last_unpublished_at is None.

        The serialization logic suppresses last_unpublished_at when the most recent
        publish timestamp is later than the most recent unpublish timestamp.
        """
        service = WorkflowService(test_db_session, test_user)
        workflow, _ = await self._create_and_publish(service, test_db_session, name="suppress-unpublish-ts-test")

        # Unpublish
        with patch(_PATCH_WEBHOOK_SVC, _mock_webhook_service()):
            await service.unpublish_workflow(workflow_id=workflow.id)

        # Verify that after unpublish, the unpublished_at timestamp exists
        response_after_unpublish = await service.list_workflow_versions_cursor(
            workflow_id=workflow.id,
            sort="created_at",
        )
        version_after_unpublish = response_after_unpublish.resources[0]
        assert version_after_unpublish.status == "previously_published"
        assert version_after_unpublish.last_unpublished_at is not None

        # Republish
        with patch(_PATCH_WEBHOOK_SVC, _mock_webhook_service()):
            await service.publish_workflow_version(
                workflow_id=workflow.id,
                version=1,
            )

        # After republish, last_unpublished_at should be suppressed
        response_after_republish = await service.list_workflow_versions_cursor(
            workflow_id=workflow.id,
            sort="created_at",
        )
        version_after_republish = response_after_republish.resources[0]
        assert version_after_republish.status == "published"
        assert version_after_republish.last_published_at is not None
        assert version_after_republish.last_unpublished_at is None
