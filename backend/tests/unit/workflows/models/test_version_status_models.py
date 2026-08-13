"""Unit tests for model changes in the version status refactor.

Covers field declarations in execution.py, query_params.py, workflow.py,
and workflow_version.py to satisfy SonarCloud coverage requirements.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from syntara.workflows.models.execution import ExecutionCreate, ExecutionRead
from syntara.workflows.models.query_params import WorkflowVersionListParams
from syntara.workflows.models.workflow import WorkflowRead
from syntara.workflows.models.workflow_publish_event import PublishAction, WorkflowPublishEvent
from syntara.workflows.models.workflow_version import (
    PublishVersionRequest,
    WorkflowVersion,
    WorkflowVersionRead,
    WorkflowVersionUpdate,
)


class TestExecutionReadFields:
    """ExecutionRead.workflow_version_name field tests."""

    def test_workflow_version_name_defaults_to_none(self) -> None:
        read = ExecutionRead.model_construct(workflow_version_name=None)
        assert read.workflow_version_name is None

    def test_workflow_version_name_can_be_set(self) -> None:
        read = ExecutionRead.model_construct(workflow_version_name="Release v1.0")
        assert read.workflow_version_name == "Release v1.0"


class TestWorkflowVersionListParams:
    """WorkflowVersionListParams instantiation tests."""

    def test_instantiates_with_defaults(self) -> None:
        params = WorkflowVersionListParams()
        assert params.limit == 20
        assert params.cursor is None
        assert params.sort is None
        assert params.include_total is False

    def test_accepts_custom_values(self) -> None:
        params = WorkflowVersionListParams(limit=5, cursor="abc", sort="-version", include_total=True)
        assert params.limit == 5
        assert params.cursor == "abc"


class TestWorkflowReadFields:
    """WorkflowRead published_version_id and published_version_number field tests."""

    def _make_workflow_read(self, **overrides: object) -> WorkflowRead:
        defaults: dict[str, object] = {
            "id": uuid4(),
            "name": "test",
            "labels": {},
            "current_version": 1,
            "is_builtin": False,
            "is_enabled": False,
            "has_validation_issues": False,
            "published_version_id": None,
            "created_by": uuid4(),
            "project_id": uuid4(),
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        defaults.update(overrides)
        return WorkflowRead.model_validate(defaults)

    def test_published_version_id_defaults_to_none(self) -> None:
        read = self._make_workflow_read()
        assert read.published_version_id is None

    def test_published_version_id_can_be_set(self) -> None:
        vid = uuid4()
        read = self._make_workflow_read(published_version_id=vid)
        assert read.published_version_id == vid

    def test_published_version_number_defaults_to_none(self) -> None:
        read = self._make_workflow_read()
        assert read.published_version_number is None

    def test_published_version_number_can_be_set(self) -> None:
        read = self._make_workflow_read(published_version_number=3)
        assert read.published_version_number == 3

    def test_published_version_id_in_model_fields(self) -> None:
        assert "published_version_id" in WorkflowRead.model_fields

    def test_published_version_number_in_model_fields(self) -> None:
        assert "published_version_number" in WorkflowRead.model_fields


class TestWorkflowVersionModel:
    """WorkflowVersion ORM model field and class attribute tests."""

    def test_filterable_fields_includes_workflow_id(self) -> None:
        assert "workflow_id" in WorkflowVersion.__filterable_fields__

    def test_filterable_fields_includes_version(self) -> None:
        assert "version" in WorkflowVersion.__filterable_fields__

    def test_sortable_fields_inherited(self) -> None:
        assert "created_at" in WorkflowVersion.__sortable_fields__

    def test_name_field_in_model_fields(self) -> None:
        assert "name" in WorkflowVersion.model_fields


class TestWorkflowVersionReadFields:
    """WorkflowVersionRead status Literal, name, and status field tests."""

    def test_status_literal_draft(self) -> None:
        read = WorkflowVersionRead(
            id=uuid4(),
            workflow_id=uuid4(),
            version=1,
            schema_version="2.0.0",
            workflow_definition={},
            created_by=uuid4(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            status="draft",
        )
        assert read.status == "draft"

    def test_status_literal_published(self) -> None:
        read = WorkflowVersionRead(
            id=uuid4(),
            workflow_id=uuid4(),
            version=1,
            schema_version="2.0.0",
            workflow_definition={},
            created_by=uuid4(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            status="published",
        )
        assert read.status == "published"

    def test_status_literal_previously_published(self) -> None:
        read = WorkflowVersionRead(
            id=uuid4(),
            workflow_id=uuid4(),
            version=1,
            schema_version="2.0.0",
            workflow_definition={},
            created_by=uuid4(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            status="previously_published",
        )
        assert read.status == "previously_published"

    def test_name_field(self) -> None:
        read = WorkflowVersionRead(
            id=uuid4(),
            workflow_id=uuid4(),
            version=1,
            schema_version="2.0.0",
            workflow_definition={},
            created_by=uuid4(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            name="Release v1",
        )
        assert read.name == "Release v1"

    def test_defaults(self) -> None:
        read = WorkflowVersionRead(
            id=uuid4(),
            workflow_id=uuid4(),
            version=1,
            schema_version="2.0.0",
            workflow_definition={},
            created_by=uuid4(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert read.status == "draft"
        assert read.name is None
        assert read.created_by_username is None


class TestWorkflowVersionUpdate:
    """WorkflowVersionUpdate name field tests."""

    def test_name_field(self) -> None:
        update = WorkflowVersionUpdate(name="new-name")
        assert update.name == "new-name"

    def test_name_defaults_none(self) -> None:
        update = WorkflowVersionUpdate()
        assert update.name is None


class TestPublishVersionRequest:
    """PublishVersionRequest field tests."""

    def test_name_field(self) -> None:
        req = PublishVersionRequest(name="Release v2.0")
        assert req.name == "Release v2.0"

    def test_defaults(self) -> None:
        req = PublishVersionRequest()
        assert req.name is None
        assert req.change_description is None
        assert req.workflow_definition is None
        assert req.expected_version is None


class TestPublishActionEnum:
    """PublishAction enum value tests."""

    def test_published_value(self) -> None:
        assert PublishAction.PUBLISHED.value == "published"

    def test_unpublished_value(self) -> None:
        assert PublishAction.UNPUBLISHED.value == "unpublished"

    def test_enum_members(self) -> None:
        assert set(PublishAction) == {PublishAction.PUBLISHED, PublishAction.UNPUBLISHED}


class TestWorkflowPublishEventModel:
    """WorkflowPublishEvent model field and class attribute tests."""

    def test_tablename(self) -> None:
        assert WorkflowPublishEvent.__tablename__ == "workflow_publish_events"

    def test_auditable_is_none(self) -> None:
        from syntara.core.models.base.base_resource import AuditLevel

        assert WorkflowPublishEvent.__auditable__ == AuditLevel.NONE

    def test_model_fields_contain_expected_keys(self) -> None:
        expected = {"workflow_id", "version_id", "action", "actor_id"}
        assert expected.issubset(set(WorkflowPublishEvent.model_fields))

    def test_workflow_id_in_model_fields(self) -> None:
        assert "workflow_id" in WorkflowPublishEvent.model_fields

    def test_version_id_in_model_fields(self) -> None:
        assert "version_id" in WorkflowPublishEvent.model_fields

    def test_action_in_model_fields(self) -> None:
        assert "action" in WorkflowPublishEvent.model_fields

    def test_actor_id_in_model_fields(self) -> None:
        assert "actor_id" in WorkflowPublishEvent.model_fields


class TestWorkflowVersionReadTimestamps:
    """WorkflowVersionRead last_published_at and last_unpublished_at field tests."""

    def test_last_published_at_defaults_to_none(self) -> None:
        read = WorkflowVersionRead(
            id=uuid4(),
            workflow_id=uuid4(),
            version=1,
            schema_version="2.0.0",
            workflow_definition={},
            created_by=uuid4(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert read.last_published_at is None

    def test_last_published_at_can_be_set(self) -> None:
        now = datetime.now(UTC)
        read = WorkflowVersionRead(
            id=uuid4(),
            workflow_id=uuid4(),
            version=1,
            schema_version="2.0.0",
            workflow_definition={},
            created_by=uuid4(),
            created_at=now,
            updated_at=now,
            last_published_at=now,
        )
        assert read.last_published_at == now

    def test_last_unpublished_at_defaults_to_none(self) -> None:
        read = WorkflowVersionRead(
            id=uuid4(),
            workflow_id=uuid4(),
            version=1,
            schema_version="2.0.0",
            workflow_definition={},
            created_by=uuid4(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert read.last_unpublished_at is None

    def test_last_unpublished_at_can_be_set(self) -> None:
        now = datetime.now(UTC)
        read = WorkflowVersionRead(
            id=uuid4(),
            workflow_id=uuid4(),
            version=1,
            schema_version="2.0.0",
            workflow_definition={},
            created_by=uuid4(),
            created_at=now,
            updated_at=now,
            last_unpublished_at=now,
        )
        assert read.last_unpublished_at == now


class TestWorkflowVersionNoPublishedAt:
    """Verify WorkflowVersion ORM model does not have a published_at field."""

    def test_published_at_not_in_model_fields(self) -> None:
        assert "published_at" not in WorkflowVersion.model_fields


class TestExecutionCreateUsePublished:
    """ExecutionCreate.use_published field tests."""

    def test_use_published_defaults_to_false(self) -> None:
        create = ExecutionCreate(workflow_id=uuid4(), trigger_node_id="trigger_1")
        assert create.use_published is False

    def test_use_published_can_be_set_to_true(self) -> None:
        create = ExecutionCreate(workflow_id=uuid4(), trigger_node_id="trigger_1", use_published=True)
        assert create.use_published is True
