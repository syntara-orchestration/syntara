"""Integration tests: save-time healing of SELECTED tool strategy with no tool_selections.

A Task Agent node left with tool_selection_strategy=SELECTED and no tool_selections
(e.g. because no MCP tools were available to pick) must be canonicalized to NONE
*before* schema findings are collected, on every save path: create, update (new
version), and atomic save-and-publish. The real (unmocked) workflow_validator is
used throughout so these tests fail if the JSON Schema 'tool_selections' is a
required property finding is still produced.
"""

from collections.abc import Generator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

import syntara.settings.cache.settings_cache as _settings_cache_module
from syntara.core.models import User
from syntara.settings.cache.settings_cache import SettingsCache, set_runtime_settings
from syntara.workflows.models import Workflow, WorkflowVersion
from syntara.workflows.services.workflow_service import WorkflowService

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture(autouse=True)
def _scoped_runtime_cache(test_session_factory: "Callable[[], object]") -> Generator[None, None, None]:
    """Install a SettingsCache for the test, restoring the previous one after.

    Needed because create_workflow/create_workflow_version/publish_workflow_version
    all call get_system_continue_on_failure(), which requires the process-wide
    SettingsCache singleton. Normally initialised by the app lifespan (session_app
    fixture) — this file doesn't use the API client, so it installs one directly.
    """
    previous = _settings_cache_module._runtime_settings
    set_runtime_settings(SettingsCache(session_factory=test_session_factory))
    yield
    _settings_cache_module._runtime_settings = previous


def _minimal_valid_definition(name: str) -> dict[str, Any]:
    """A schema-valid baseline definition with a single script node."""
    return {
        "schema_version": "2.0.0",
        "name": name,
        "triggers": [{"id": "trigger_1", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {"id": "n1", "type": "script", "name": "Step 1", "parameters": {"language": "python", "code": "print(1)"}}
        ],
        "edges": [{"from": "trigger_1", "to": "n1"}],
    }


def _broken_agentic_definition(name: str) -> dict[str, Any]:
    """The exact broken shape from the ticket: SELECTED with no tool_selections."""
    return {
        "schema_version": "2.0.0",
        "name": name,
        "triggers": [{"id": "trigger_1", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {
                "id": "agent_1",
                "type": "agentic",
                "name": "Task Agent",
                "parameters": {
                    "prompt": "Say hello",
                    "tool_selection_strategy": "SELECTED",
                },
            }
        ],
        "edges": [{"from": "trigger_1", "to": "agent_1"}],
    }


def _create_db_workflow(
    session: AsyncSession, user: User, project_id: UUID, *, name: str, workflow_definition: dict[str, Any]
) -> Workflow:
    now = datetime.now(UTC)
    workflow = Workflow(
        id=uuid4(),
        name=name,
        description=None,
        labels={},
        current_version=1,
        created_by=user.id,
        project_id=project_id,
        is_enabled=False,
        is_builtin=False,
        created_at=now,
        updated_at=now,
    )
    session.add(workflow)
    version = WorkflowVersion(
        id=uuid4(),
        workflow_id=workflow.id,
        version=1,
        schema_version="2.0.0",
        workflow_definition=workflow_definition,
        created_by=user.id,
        change_description="Initial version",
        created_at=now,
    )
    session.add(version)
    return workflow


@pytest.mark.asyncio
class TestCreateWorkflowHealsEmptySelectedStrategy:
    """POST /workflows with a broken agentic node saves clean instead of erroring."""

    async def test_no_findings_and_persisted_definition_is_canonical(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        service = WorkflowService(test_db_session, test_user)
        definition = _broken_agentic_definition("create-heal-test")

        workflow, version, val_result = await service.create_workflow(
            name="create-heal-test",
            description=None,
            labels={},
            workflow_definition=definition,
            project_id=test_project_id,
        )

        assert val_result.findings == []
        assert workflow.has_validation_issues is False
        params = version.workflow_definition["nodes"][0]["parameters"]
        assert params["tool_selection_strategy"] == "NONE"
        assert "tool_selections" not in params

    async def test_genuinely_invalid_definitions_still_reported(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        """Guard: the pre-pass only touches tool_selection_strategy, not unrelated errors."""
        service = WorkflowService(test_db_session, test_user)
        definition = _broken_agentic_definition("still-invalid-test")
        del definition["nodes"][0]["parameters"]["prompt"]

        _workflow, _version, val_result = await service.create_workflow(
            name="still-invalid-test",
            description=None,
            labels={},
            workflow_definition=definition,
            project_id=test_project_id,
        )

        assert val_result.error_count >= 1
        assert any("prompt" in finding.message for finding in val_result.findings)


@pytest.mark.asyncio
class TestCreateWorkflowVersionHealsEmptySelectedStrategy:
    """Saving a new version with a broken agentic node heals before validation."""

    async def test_no_findings_and_persisted_definition_is_canonical(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        service = WorkflowService(test_db_session, test_user)
        workflow = _create_db_workflow(
            test_db_session,
            test_user,
            test_project_id,
            name="version-heal-test",
            workflow_definition=_minimal_valid_definition("version-heal-test"),
        )
        await test_db_session.commit()

        new_definition = _broken_agentic_definition("version-heal-test")

        result, val_result = await service.create_workflow_version(workflow, new_definition, "Add task agent")

        assert result is not None
        assert val_result.findings == []
        assert workflow.has_validation_issues is False
        params = result.workflow_definition["nodes"][0]["parameters"]
        assert params["tool_selection_strategy"] == "NONE"
        assert "tool_selections" not in params


@pytest.mark.asyncio
class TestPublishAtomicSaveHealsEmptySelectedStrategy:
    """Atomic save-and-publish heals the definition before the publish validation gate."""

    async def test_publish_succeeds_and_persisted_definition_is_canonical(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        service = WorkflowService(test_db_session, test_user)
        workflow = _create_db_workflow(
            test_db_session,
            test_user,
            test_project_id,
            name="publish-heal-test",
            workflow_definition=_minimal_valid_definition("publish-heal-test"),
        )
        await test_db_session.commit()

        broken_definition = _broken_agentic_definition("publish-heal-test")

        mock_wh_svc = MagicMock()
        mock_wh_svc.return_value.sync_webhook_triggers = AsyncMock()
        with patch("syntara.workflows.services.workflow_service.WebhookTriggerService", mock_wh_svc):
            result_workflow, result_version, _warning = await service.publish_workflow_version(
                workflow_id=workflow.id,
                version=1,
                workflow_definition=broken_definition,
            )

        assert result_workflow.published_version_id == result_version.id
        params = result_version.workflow_definition["nodes"][0]["parameters"]
        assert params["tool_selection_strategy"] == "NONE"
        assert "tool_selections" not in params
