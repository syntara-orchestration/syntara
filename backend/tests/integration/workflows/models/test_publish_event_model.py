"""Integration tests for publish-event, version, workflow, and execution model fields.

Exercises class-level declarations (Field(), __tablename__, __table_args__, StrEnum,
schema fields) through the real database to ensure coverage on model files:
- workflow_publish_event.py
- workflow_version.py (name field, filterable/sortable, WorkflowVersionRead)
- workflow.py (published_version_id, published_version_number)
- execution.py (use_published)
- query_params.py (WorkflowVersionListParams)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from syntara.workflows.models import Workflow, WorkflowVersion, WorkflowVersionRead
from syntara.workflows.models.execution import ExecutionCreate
from syntara.workflows.models.query_params import WorkflowVersionListParams
from syntara.workflows.models.workflow_publish_event import PublishAction, WorkflowPublishEvent
from tests.helpers.workflow import create_minimal_workflow_definition

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User


# ---------------------------------------------------------------------------
# TestWorkflowPublishEventModel
# ---------------------------------------------------------------------------


class TestWorkflowPublishEventModel:
    """Tests for WorkflowPublishEvent table model and PublishAction enum."""

    @pytest.mark.asyncio
    async def test_create_publish_event(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
    ) -> None:
        """Persist a PUBLISHED event and verify all fields round-trip."""
        workflow = Workflow(
            id=uuid4(),
            name="pub-event-wf",
            created_by=test_user.id,
            project_id=test_project_id,
        )
        test_db_session.add(workflow)
        await test_db_session.flush()

        version = WorkflowVersion(
            id=uuid4(),
            workflow_id=workflow.id,
            version=1,
            schema_version="2.0.0",
            workflow_definition=create_minimal_workflow_definition(name="pub-event"),
            created_by=test_user.id,
        )
        test_db_session.add(version)
        await test_db_session.flush()

        event = WorkflowPublishEvent(
            id=uuid4(),
            workflow_id=workflow.id,
            version_id=version.id,
            action=PublishAction.PUBLISHED,
            actor_id=test_user.id,
        )
        test_db_session.add(event)
        await test_db_session.flush()
        await test_db_session.refresh(event)

        assert event.workflow_id == workflow.id
        assert event.version_id == version.id
        assert event.action == PublishAction.PUBLISHED
        assert event.actor_id == test_user.id
        assert event.id is not None
        assert event.created_at is not None

    @pytest.mark.asyncio
    async def test_create_unpublish_event(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
    ) -> None:
        """Persist an UNPUBLISHED event and verify the action value."""
        workflow = Workflow(
            id=uuid4(),
            name="unpub-event-wf",
            created_by=test_user.id,
            project_id=test_project_id,
        )
        test_db_session.add(workflow)
        await test_db_session.flush()

        version = WorkflowVersion(
            id=uuid4(),
            workflow_id=workflow.id,
            version=1,
            schema_version="2.0.0",
            workflow_definition=create_minimal_workflow_definition(name="unpub-event"),
            created_by=test_user.id,
        )
        test_db_session.add(version)
        await test_db_session.flush()

        event = WorkflowPublishEvent(
            id=uuid4(),
            workflow_id=workflow.id,
            version_id=version.id,
            action=PublishAction.UNPUBLISHED,
            actor_id=test_user.id,
        )
        test_db_session.add(event)
        await test_db_session.flush()
        await test_db_session.refresh(event)

        assert event.action == PublishAction.UNPUBLISHED

    def test_publish_action_enum_values(self) -> None:
        """Verify PublishAction StrEnum member values."""
        assert PublishAction.PUBLISHED.value == "published"
        assert PublishAction.UNPUBLISHED.value == "unpublished"


# ---------------------------------------------------------------------------
# TestWorkflowVersionModelFields
# ---------------------------------------------------------------------------


class TestWorkflowVersionModelFields:
    """Tests for WorkflowVersion name field, filterable, and sortable declarations."""

    @pytest.mark.asyncio
    async def test_version_name_field_persists(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
    ) -> None:
        """Create a version with name='Release v1' and verify it persists."""
        workflow = Workflow(
            id=uuid4(),
            name="name-field-wf",
            created_by=test_user.id,
            project_id=test_project_id,
        )
        test_db_session.add(workflow)
        await test_db_session.flush()

        version = WorkflowVersion(
            id=uuid4(),
            workflow_id=workflow.id,
            version=1,
            schema_version="2.0.0",
            workflow_definition=create_minimal_workflow_definition(name="name-field"),
            created_by=test_user.id,
            name="Release v1",
        )
        test_db_session.add(version)
        await test_db_session.flush()
        await test_db_session.refresh(version)

        assert version.name == "Release v1"

    def test_filterable_fields_include_workflow_id_and_version(self) -> None:
        """Verify __filterable_fields__ contains workflow_id and version."""
        fields = WorkflowVersion.__filterable_fields__
        assert "workflow_id" in fields
        assert "version" in fields

    def test_sortable_fields_include_created_at(self) -> None:
        """Verify __sortable_fields__ contains created_at."""
        assert "created_at" in WorkflowVersion.__sortable_fields__


# ---------------------------------------------------------------------------
# TestWorkflowVersionReadSchema
# ---------------------------------------------------------------------------


class TestWorkflowVersionReadSchema:
    """Tests for WorkflowVersionRead response schema fields."""

    def test_version_read_status_field(self) -> None:
        """Instantiate WorkflowVersionRead with status='published'."""
        now = datetime.now(UTC)
        schema = WorkflowVersionRead(
            id=uuid4(),
            workflow_id=uuid4(),
            version=1,
            schema_version="2.0.0",
            workflow_definition={"nodes": []},
            created_by=uuid4(),
            created_at=now,
            updated_at=now,
            status="published",
        )
        assert schema.status == "published"

    def test_version_read_timestamp_fields(self) -> None:
        """Instantiate with last_published_at and last_unpublished_at set."""
        now = datetime.now(UTC)
        schema = WorkflowVersionRead(
            id=uuid4(),
            workflow_id=uuid4(),
            version=2,
            schema_version="2.0.0",
            workflow_definition={"nodes": []},
            created_by=uuid4(),
            created_at=now,
            updated_at=now,
            last_published_at=now,
            last_unpublished_at=now,
        )
        assert schema.last_published_at == now
        assert schema.last_unpublished_at == now


# ---------------------------------------------------------------------------
# TestWorkflowModelFields
# ---------------------------------------------------------------------------


class TestWorkflowModelFields:
    """Tests for Workflow published_version_id field."""

    @pytest.mark.asyncio
    async def test_published_version_id_persists(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
    ) -> None:
        """Set published_version_id on a Workflow, flush, refresh, and verify."""
        workflow = Workflow(
            id=uuid4(),
            name="pub-version-wf",
            created_by=test_user.id,
            project_id=test_project_id,
        )
        test_db_session.add(workflow)
        await test_db_session.flush()

        version = WorkflowVersion(
            id=uuid4(),
            workflow_id=workflow.id,
            version=1,
            schema_version="2.0.0",
            workflow_definition=create_minimal_workflow_definition(name="pub-version"),
            created_by=test_user.id,
        )
        test_db_session.add(version)
        await test_db_session.flush()

        workflow.published_version_id = version.id
        workflow.is_enabled = True
        await test_db_session.flush()
        await test_db_session.refresh(workflow)

        assert workflow.published_version_id == version.id
        assert workflow.is_enabled is True


# ---------------------------------------------------------------------------
# TestExecutionCreateUsePublished
# ---------------------------------------------------------------------------


class TestExecutionCreateUsePublished:
    """Tests for ExecutionCreate.use_published field."""

    def test_use_published_field(self) -> None:
        """Instantiate ExecutionCreate with use_published=True."""
        create = ExecutionCreate(workflow_id=uuid4(), trigger_node_id="trigger_1", use_published=True)
        assert create.use_published is True


# ---------------------------------------------------------------------------
# TestWorkflowVersionListParams
# ---------------------------------------------------------------------------


class TestWorkflowVersionListParams:
    """Tests for WorkflowVersionListParams instantiation."""

    def test_instantiation(self) -> None:
        """Instantiate with defaults and verify inherited BaseListParams fields."""
        params = WorkflowVersionListParams()
        assert params.limit == 20
        assert params.cursor is None
        assert params.sort is None
        assert params.include_total is False
