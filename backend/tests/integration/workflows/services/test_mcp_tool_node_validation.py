"""Integration tests for mcp_tool node reference validation against a real database.

Covers the save path (``WorkflowService.create_workflow``) and the reference
validator directly, using an ``mcp_server`` integration created through
``IntegrationService`` so the Tool records come from the real discovery path.
"""

from collections.abc import Generator
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.integrations.models.integration import (
    Integration,
    IntegrationCreate,
    IntegrationRead,
    IntegrationScope,
    IntegrationType,
)
from syntara.integrations.services.integration_service import IntegrationService
from syntara.workflows.models.validation_finding import ValidationCategory, ValidationSeverity
from syntara.workflows.services.workflow_service import WorkflowService
from syntara.workflows.validators.workflow_integrations import validate_workflow_references
from tests.fixtures.settings import FakeSettingsCache

_TOOL_NAME = "echo"


@pytest.fixture(autouse=True)
def _ensure_runtime_settings() -> Generator[None, None, None]:
    """Initialise the SettingsCache singleton the save paths read defaults from."""
    import syntara.settings.cache.settings_cache as settings_module

    original = settings_module._runtime_settings
    settings_module._runtime_settings = FakeSettingsCache()  # type: ignore[assignment]
    try:
        yield
    finally:
        settings_module._runtime_settings = original


def _mcp_tool_definition(integration_id: str, tool_name: str = _TOOL_NAME) -> dict[str, Any]:
    """Workflow definition with a single mcp_tool node."""
    return {
        "schema_version": "2.0.0",
        "name": "mcp-tool-wf",
        "triggers": [{"id": "trigger_0", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {
                "id": "node_1",
                "type": "mcp_tool",
                "parameters": {
                    "integration_id": integration_id,
                    "tool_name": tool_name,
                    "arguments": {"message": "${trigger.message}"},
                },
            }
        ],
        "edges": [{"from": "trigger_0", "to": "node_1"}],
    }


async def _create_mcp_integration(
    session: AsyncSession,
    user: User,
    *,
    with_tools: bool = True,
) -> IntegrationRead:
    """Create an mcp_server integration (optionally with discovered tools) via its service."""
    service = IntegrationService(session, user)
    payload: dict[str, Any] = {
        "name": f"mcp-{uuid4().hex[:8]}",
        "integration_type": IntegrationType.MCP_SERVER,
        "configuration": {"integration_type": "mcp_server", "base_url": "http://localhost:8080/mcp"},
    }
    if with_tools:
        payload["discovered_tools"] = [
            {"name": _TOOL_NAME, "description": "Echo back the input", "enabled": True},
            {"name": "sum", "description": "Add numbers", "enabled": True},
        ]
    integration = await service.create_integration(IntegrationCreate(**payload))
    await session.commit()
    return integration


async def _create_llm_integration(session: AsyncSession, user: User) -> Integration:
    """Create an llm_provider integration row so wrong-type references can be tested.

    Inserted directly: the service requires a management credential for
    llm_provider integrations, which is irrelevant to this validation path.
    """
    integration = Integration(
        name=f"llm-{uuid4().hex[:8]}",
        integration_type=IntegrationType.LLM_PROVIDER,
        scope=IntegrationScope.GLOBAL,
        enabled=True,
        created_by=user.id,
        updated_by=user.id,
    )
    session.add(integration)
    await session.flush()
    return integration


@pytest.mark.integration
@pytest.mark.asyncio
class TestMCPToolReferenceValidation:
    """validate_workflow_references reports mcp_tool findings from real DB state."""

    async def test_valid_tool_name_produces_no_findings(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
    ) -> None:
        integration = await _create_mcp_integration(test_db_session, test_user)

        findings = await validate_workflow_references(
            test_db_session,
            _mcp_tool_definition(str(integration.id)),
            test_project_id,
        )

        assert findings == []

    async def test_unknown_tool_name_produces_error_finding(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
    ) -> None:
        integration = await _create_mcp_integration(test_db_session, test_user)

        findings = await validate_workflow_references(
            test_db_session,
            _mcp_tool_definition(str(integration.id), tool_name="not_a_real_tool"),
            test_project_id,
        )

        assert len(findings) == 1
        finding = findings[0]
        assert finding.severity == ValidationSeverity.error
        assert finding.category == ValidationCategory.invalid_reference
        assert finding.node_id == "node_1"
        assert finding.field_path == "parameters.tool_name"
        assert "not_a_real_tool" in finding.message

    async def test_integration_without_discovered_tools_produces_warning(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
    ) -> None:
        integration = await _create_mcp_integration(test_db_session, test_user, with_tools=False)

        findings = await validate_workflow_references(
            test_db_session,
            _mcp_tool_definition(str(integration.id)),
            test_project_id,
        )

        assert len(findings) == 1
        assert findings[0].severity == ValidationSeverity.warning
        assert findings[0].field_path == "parameters.tool_name"

    async def test_wrong_integration_type_produces_error_finding(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
    ) -> None:
        integration = await _create_llm_integration(test_db_session, test_user)

        findings = await validate_workflow_references(
            test_db_session,
            _mcp_tool_definition(str(integration.id)),
            test_project_id,
        )

        assert len(findings) == 1
        assert findings[0].severity == ValidationSeverity.error
        assert findings[0].field_path == "parameters.integration_id"
        assert "mcp_server" in findings[0].message


@pytest.mark.integration
@pytest.mark.asyncio
class TestMCPToolNodeSave:
    """WorkflowService.create_workflow accepts mcp_tool nodes and surfaces findings."""

    async def test_create_workflow_with_valid_mcp_tool_node_succeeds(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
    ) -> None:
        integration = await _create_mcp_integration(test_db_session, test_user)
        service = WorkflowService(test_db_session, test_user)

        workflow, version, result = await service.create_workflow(
            name=f"wf-{uuid4().hex[:8]}",
            description=None,
            labels={},
            workflow_definition=_mcp_tool_definition(str(integration.id)),
            project_id=test_project_id,
        )

        assert workflow.id is not None
        assert version.workflow_definition["nodes"][0]["type"] == "mcp_tool"
        assert result.is_valid
        assert result.findings == []

    async def test_create_workflow_with_unknown_tool_name_reports_error(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
    ) -> None:
        integration = await _create_mcp_integration(test_db_session, test_user)
        service = WorkflowService(test_db_session, test_user)

        workflow, _version, result = await service.create_workflow(
            name=f"wf-{uuid4().hex[:8]}",
            description=None,
            labels={},
            workflow_definition=_mcp_tool_definition(str(integration.id), tool_name="ghost_tool"),
            project_id=test_project_id,
        )

        assert workflow.has_validation_issues is True
        assert not result.is_valid
        assert result.error_count == 1
        finding = result.findings[0]
        assert finding.category == ValidationCategory.invalid_reference
        assert finding.field_path == "parameters.tool_name"
        assert "ghost_tool" in finding.message
