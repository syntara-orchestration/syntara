"""Persistence tests for backend-generated form response schemas."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest

from syntara.core.constants import JsonbLimits
from syntara.core.jsonb_limits import serialized_json_size
from syntara.workflows.models import Workflow, WorkflowCreate, WorkflowUpdate, WorkflowVersion
from syntara.workflows.services.workflow_service import WorkflowService

if TYPE_CHECKING:
    from collections.abc import Generator
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User


@pytest.fixture(autouse=True)
def _system_continue_on_failure() -> Generator[None, None, None]:
    """Provide the workflow service's runtime setting without app startup."""
    with patch(
        "syntara.workflows.services.workflow_service.get_system_continue_on_failure",
        AsyncMock(return_value=False),
    ):
        yield


def _form_definition(value_name: str = "request_title") -> dict[str, Any]:
    return {
        "fields": [
            {
                "type": "text",
                "value_name": value_name,
                "label": "Request title",
                "required": True,
            },
            {"type": "email", "value_name": "contact", "label": "Contact"},
            {"type": "number", "value_name": "count", "label": "Count"},
            {"type": "checkbox", "value_name": "confirmed", "label": "Confirmed"},
            {
                "type": "date",
                "value_name": "scheduled_at",
                "label": "Scheduled at",
                "include_date": True,
                "include_time": True,
                "include_timezone": True,
            },
            {
                "type": "dropdown",
                "value_name": "severity",
                "label": "Severity",
                "options": {
                    "source": "static",
                    "values": [{"display_label": "Low", "value": "low"}],
                },
            },
            {
                "type": "multi_select",
                "value_name": "tags",
                "label": "Tags",
                "options": {
                    "source": "static",
                    "values": [{"display_label": "One", "value": "one"}],
                },
            },
        ]
    }


def _expected_properties(text_value_name: str) -> dict[str, dict[str, Any]]:
    return {
        text_value_name: {"type": "string"},
        "contact": {"type": "string"},
        "count": {"type": ["number", "null"]},
        "confirmed": {"type": "boolean"},
        "scheduled_at": {"type": "string", "format": "date-time"},
        "severity": {"type": ["string", "null"], "enum": ["low", None]},
        "tags": {"type": "array", "items": {"type": "string", "enum": ["one"]}},
    }


def _large_static_form_definition() -> dict[str, Any]:
    option_value = "option-value-" + ("x" * 2_800)
    return {
        "fields": [
            {
                "type": "dropdown",
                "value_name": "choice",
                "label": "Choice",
                "required": True,
                "options": {
                    "source": "static",
                    "values": [{"display_label": f"Option {index}", "value": option_value} for index in range(500)],
                },
            }
        ]
    }


def _large_static_option_workflow_definition() -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "name": "large-form-schema-workflow",
        "description": "Workflow with large static option values",
        "triggers": [
            {
                "id": "form_trigger",
                "type": "form_trigger",
                "parameters": {"form_definition": _large_static_form_definition()},
            }
        ],
        "nodes": [
            {
                "id": "finish",
                "type": "script",
                "parameters": {"language": "bash", "code": "echo done"},
            }
        ],
        "edges": [{"from": "form_trigger", "to": "finish"}],
    }


def _workflow_definition() -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "name": "form-schema-workflow",
        "description": "Workflow with both form node types",
        "triggers": [
            {
                "id": "form_trigger",
                "type": "form_trigger",
                "parameters": {"form_definition": _form_definition()},
            }
        ],
        "nodes": [
            {
                "id": "form_prompt",
                "type": "form_prompt",
                "parameters": {"form_definition": _form_definition("prompt_title")},
            },
            {
                "id": "finish",
                "type": "script",
                "parameters": {"language": "bash", "code": "echo done"},
            },
        ],
        "edges": [
            {"from": "form_trigger", "to": "form_prompt"},
            {"from": "form_prompt", "to": "finish", "from_port": "submitted"},
        ],
    }


class TestWorkflowFormResponseSchemaPersistence:
    """Workflow persistence generates and regenerates form response schemas."""

    @pytest.mark.asyncio
    async def test_create_and_update_persist_generated_schemas(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        service = WorkflowService(test_db_session, test_user)
        definition = _workflow_definition()

        workflow, version, validation_result = await service.create_workflow(
            name=f"form-schema-{test_project_id.hex[:8]}",
            description=None,
            labels={},
            workflow_definition=definition,
            project_id=test_project_id,
        )

        assert not validation_result.error_count
        trigger_parameters = version.workflow_definition["triggers"][0]["parameters"]
        prompt_parameters = version.workflow_definition["nodes"][0]["parameters"]
        trigger_schema = trigger_parameters["response_schema"]
        prompt_schema = prompt_parameters["response_schema"]
        assert trigger_schema["properties"] == _expected_properties("request_title")
        assert prompt_schema["properties"] == _expected_properties("prompt_title")

        updated_definition = _workflow_definition()
        updated_definition["triggers"][0]["parameters"]["form_definition"] = _form_definition("updated_title")
        updated_definition["nodes"][0]["parameters"]["response_schema"] = {"type": "client-supplied"}

        updated_version, updated_validation = await service.create_workflow_version(
            workflow,
            workflow_definition=updated_definition,
            change_description="Update form and attempt to supply schema",
        )

        assert not updated_validation.error_count
        assert updated_version is not None
        updated_trigger_parameters = updated_version.workflow_definition["triggers"][0]["parameters"]
        updated_prompt_parameters = updated_version.workflow_definition["nodes"][0]["parameters"]
        assert updated_trigger_parameters["response_schema"]["properties"] == _expected_properties("updated_title")
        assert updated_prompt_parameters["response_schema"] == prompt_schema

    @pytest.mark.asyncio
    async def test_legacy_definition_without_schema_is_not_retroactively_changed(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        service = WorkflowService(test_db_session, test_user)
        definition = _workflow_definition()
        definition["triggers"][0]["parameters"]["form_definition"] = {
            "fields": [
                {
                    "type": "text",
                    "value_name": "request_title",
                    "label": "Request title",
                    "required": True,
                }
            ]
        }
        definition["nodes"][0]["parameters"]["form_definition"] = {
            "fields": [
                {
                    "type": "text",
                    "value_name": "prompt_title",
                    "label": "Prompt title",
                    "required": True,
                }
            ]
        }
        workflow = Workflow(
            name=f"legacy-form-schema-{test_project_id.hex[:8]}",
            current_version=1,
            created_by=test_user.id,
            project_id=test_project_id,
            is_enabled=False,
        )
        version = WorkflowVersion(
            workflow_id=workflow.id,
            version=1,
            schema_version="2.0.0",
            workflow_definition=definition,
            created_by=test_user.id,
            change_description="Legacy initial version",
        )
        test_db_session.add(workflow)
        test_db_session.add(version)
        await test_db_session.commit()

        unchanged_version, _validation_result = await service.create_workflow_version(
            workflow,
            workflow_definition=definition,
            change_description="No form changes",
        )

        assert unchanged_version is None
        assert "response_schema" not in definition["triggers"][0]["parameters"]

    @pytest.mark.asyncio
    async def test_publish_with_inline_definition_prepares_response_schemas(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        service = WorkflowService(test_db_session, test_user)
        definition = _workflow_definition()

        workflow, initial_version, _validation_result = await service.create_workflow(
            name=f"inline-form-schema-{test_project_id.hex[:8]}",
            description=None,
            labels={},
            workflow_definition=definition,
            project_id=test_project_id,
        )

        initial_prompt_schema = initial_version.workflow_definition["nodes"][0]["parameters"]["response_schema"]
        inline_definition = _workflow_definition()
        inline_definition["triggers"][0]["parameters"]["form_definition"] = _form_definition("updated_title")
        inline_definition["triggers"][0]["parameters"]["response_schema"] = {"type": "client-supplied"}

        with (
            patch.object(WorkflowService, "_sync_all_trigger_types", AsyncMock()),
            patch.object(WorkflowService, "_sync_scheduled_triggers", AsyncMock()),
        ):
            result_workflow, published_version, _warning = await service.publish_workflow_version(
                workflow_id=workflow.id,
                version=initial_version.version,
                workflow_definition=inline_definition,
                change_description="Publish inline form changes",
            )

        assert published_version.version == 2
        assert result_workflow.published_version_id == published_version.id
        trigger_schema = published_version.workflow_definition["triggers"][0]["parameters"]["response_schema"]
        prompt_schema = published_version.workflow_definition["nodes"][0]["parameters"]["response_schema"]
        assert trigger_schema["properties"] == _expected_properties("updated_title")
        assert prompt_schema == initial_prompt_schema

    @pytest.mark.asyncio
    async def test_malformed_node_type_returns_validation_findings(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        service = WorkflowService(test_db_session, test_user)

        workflow, _initial_version, initial_validation = await service.create_workflow(
            name=f"malformed-form-node-{test_project_id.hex[:8]}",
            description=None,
            labels={},
            workflow_definition=_workflow_definition(),
            project_id=test_project_id,
        )
        malformed_definition = {
            "schema_version": "2.0.0",
            "name": "form-schema-workflow",
            "description": "Workflow with malformed node",
            "triggers": [],
            "nodes": [{}],
            "edges": [],
        }

        updated_version, updated_validation = await service.create_workflow_version(
            workflow,
            workflow_definition=malformed_definition,
            change_description="Submit malformed node",
        )

        assert not initial_validation.error_count
        assert updated_validation.error_count > 0
        assert updated_version is not None
        assert workflow.has_validation_issues is True

    @pytest.mark.asyncio
    async def test_round_trip_update_with_large_static_options(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        service = WorkflowService(test_db_session, test_user)
        definition = _large_static_option_workflow_definition()

        create_request = WorkflowCreate.model_validate(
            {
                "name": f"large-form-schema-{test_project_id.hex[:8]}",
                "description": None,
                "labels": {},
                "workflow_definition": definition,
                "project_id": test_project_id,
            }
        )
        assert create_request.workflow_definition is not None

        workflow, initial_version, validation_result = await service.create_workflow(
            name=f"large-form-schema-{test_project_id.hex[:8]}",
            description=None,
            labels={},
            workflow_definition=definition,
            project_id=test_project_id,
        )

        assert not validation_result.error_count
        assert serialized_json_size(definition) < JsonbLimits.MAX_WORKFLOW_DEFINITION_BYTES
        assert serialized_json_size(initial_version.workflow_definition) > JsonbLimits.MAX_WORKFLOW_DEFINITION_BYTES

        round_trip_definition = deepcopy(initial_version.workflow_definition)
        round_trip_definition["description"] = "Unrelated edit"
        update_request = WorkflowUpdate.model_validate(
            {
                "name": workflow.name,
                "description": workflow.description,
                "workflow_definition": round_trip_definition,
                "change_description": "Unrelated edit",
            }
        )
        assert update_request.workflow_definition is not None

        updated_version, updated_validation = await service.create_workflow_version(
            workflow,
            workflow_definition=round_trip_definition,
            change_description="Unrelated edit",
        )

        assert not updated_validation.error_count
        assert updated_version is not None
        assert "response_schema" in updated_version.workflow_definition["triggers"][0]["parameters"]
