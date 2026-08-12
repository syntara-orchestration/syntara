"""Comprehensive model field coverage tests for PR 545 changes."""

from __future__ import annotations

from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Index

from syntara.workflows.models.execution import Execution, ExecutionRead
from syntara.workflows.models.query_params import WorkflowVersionListParams
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_publish_event import PublishAction, WorkflowPublishEvent
from syntara.workflows.models.workflow_version import WorkflowVersion


class TestWorkflowPublishEventFields:
    """Exercise WorkflowPublishEvent model field declarations via instantiation."""

    def test_model_construct_sets_workflow_id_in_dict(self) -> None:
        wid = uuid4()
        event = WorkflowPublishEvent.model_construct(workflow_id=wid)
        assert event.__dict__["workflow_id"] == wid

    def test_model_construct_sets_version_id_in_dict(self) -> None:
        vid = uuid4()
        event = WorkflowPublishEvent.model_construct(version_id=vid)
        assert event.__dict__["version_id"] == vid

    def test_model_construct_sets_action_in_dict(self) -> None:
        event = WorkflowPublishEvent.model_construct(action=PublishAction.PUBLISHED)
        assert event.__dict__["action"] == PublishAction.PUBLISHED

    def test_model_construct_sets_actor_id_in_dict(self) -> None:
        aid = uuid4()
        event = WorkflowPublishEvent.model_construct(actor_id=aid)
        assert event.__dict__["actor_id"] == aid

    def test_table_args_is_tuple(self) -> None:
        assert isinstance(WorkflowPublishEvent.__table_args__, tuple)

    def test_table_args_contains_three_indexes(self) -> None:
        indexes = [a for a in WorkflowPublishEvent.__table_args__ if isinstance(a, Index)]
        assert len(indexes) == 3

    def test_table_args_index_names(self) -> None:
        names = {a.name for a in WorkflowPublishEvent.__table_args__ if isinstance(a, Index)}
        assert names == {
            "ix_wf_publish_events_workflow_id",
            "ix_wf_publish_events_version_id",
            "ix_wf_publish_events_actor_id",
        }

    def test_publish_action_is_str_enum(self) -> None:
        assert issubclass(PublishAction, StrEnum)

    def test_publish_action_member_count(self) -> None:
        assert len(PublishAction) == 2


class TestWorkflowVersionFields:
    """Exercise WorkflowVersion model field declarations via instantiation."""

    def test_name_set_via_model_construct(self) -> None:
        wv = WorkflowVersion.model_construct(name="Release v1.0")
        assert wv.__dict__["name"] == "Release v1.0"

    def test_name_absent_when_not_provided(self) -> None:
        wv = WorkflowVersion.model_construct()
        assert wv.__dict__.get("name") is None

    def test_workflow_relationship_declared(self) -> None:
        assert "workflow" in WorkflowVersion.__sqlmodel_relationships__

    def test_executions_relationship_declared(self) -> None:
        assert "executions" in WorkflowVersion.__sqlmodel_relationships__

    def test_table_args_is_tuple(self) -> None:
        assert isinstance(WorkflowVersion.__table_args__, tuple)

    def test_table_args_index_names(self) -> None:
        names = {a.name for a in WorkflowVersion.__table_args__ if isinstance(a, Index)}
        assert "ix_workflow_versions_workflow_version" in names
        assert "ix_workflow_versions_workflow_created" in names


class TestWorkflowFields:
    """Exercise Workflow ORM model field declarations."""

    def test_published_version_id_in_model_fields(self) -> None:
        assert "published_version_id" in Workflow.model_fields

    def test_published_version_id_set_via_model_construct(self) -> None:
        vid = uuid4()
        wf = Workflow.model_construct(published_version_id=vid)
        assert wf.__dict__["published_version_id"] == vid

    def test_published_version_id_absent_when_not_provided(self) -> None:
        wf = Workflow.model_construct()
        assert wf.__dict__.get("published_version_id") is None

    def test_filterable_fields_contains_published_version_id(self) -> None:
        assert "published_version_id" in Workflow.__filterable_fields__


class TestExecutionFields:
    """Exercise Execution model field declarations."""

    def test_sortable_fields_include_run_history_fields(self) -> None:
        assert Execution.__sortable_fields__ == [
            "created_at",
            "updated_at",
            "deleted_at",
            "id",
            "workflow_version_id",
            "workflow_id",
            "completed_at",
            "status",
        ]

    def test_retried_from_execution_id_in_execution_model_fields(self) -> None:
        assert "retried_from_execution_id" in Execution.model_fields

    def test_retried_from_execution_id_in_execution_read_model_fields(self) -> None:
        assert "retried_from_execution_id" in ExecutionRead.model_fields

    def test_retried_from_execution_id_default_none(self) -> None:
        read = ExecutionRead.model_construct()
        assert getattr(read, "retried_from_execution_id", None) is None

    def test_retried_from_execution_id_with_value(self) -> None:
        eid = uuid4()
        read = ExecutionRead.model_construct(retried_from_execution_id=eid)
        assert read.retried_from_execution_id == eid

    def test_execution_orm_retried_from_in_dict(self) -> None:
        eid = uuid4()
        exc = Execution.model_construct(retried_from_execution_id=eid)
        assert exc.__dict__["retried_from_execution_id"] == eid


class TestWorkflowVersionListParamsFields:
    """Exercise WorkflowVersionListParams inheritance and structure."""

    def test_inherits_base_list_params_fields(self) -> None:
        from syntara.core.models.base import BaseListParams

        assert issubclass(WorkflowVersionListParams, BaseListParams)

    def test_model_fields_include_limit(self) -> None:
        assert "limit" in WorkflowVersionListParams.model_fields

    def test_model_fields_include_cursor(self) -> None:
        assert "cursor" in WorkflowVersionListParams.model_fields

    def test_model_fields_include_sort(self) -> None:
        assert "sort" in WorkflowVersionListParams.model_fields
