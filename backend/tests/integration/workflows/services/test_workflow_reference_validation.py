"""Integration tests for save-time workflow reference validation.

Tests validate_workflow_references against a real database, covering
every combination of integration type, resource type, and failure mode.
"""

from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.exceptions import SafeValueError
from syntara.core.models import User
from syntara.integrations.models.integration import (
    Integration,
    IntegrationProjectAssignment,
    IntegrationScope,
    IntegrationType,
)
from syntara.integrations.models.llm_model import LLMModel
from syntara.tool_manager.models.tool import Tool, ToolStatus
from syntara.workflows.validators.workflow_integrations import (
    validate_workflow_references,
)

# ---------------------------------------------------------------------------
# Shared helpers — build workflow definitions for each node type
# ---------------------------------------------------------------------------


def _aap_definition(integration_id: str) -> dict[str, Any]:
    """Workflow definition with a single AAP Job Template node."""
    return {
        "schema_version": "2.0.0",
        "triggers": [{"id": "trigger-0", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {
                "id": "node-1",
                "type": "aap_job_template",
                "parameters": {"integration_id": integration_id, "credential_id": "", "job_template_id": 1},
            }
        ],
        "edges": [{"from": "trigger-0", "to": "node-1"}],
    }


def _agentic_definition(
    *,
    integration_ids: list[str] | None = None,
    llm_model_id: str | None = None,
    tool_ids: list[str] | None = None,
    tool_strategy: str | None = None,
) -> dict[str, Any]:
    """Workflow definition with a single Task Agent (agentic) node."""
    params: dict[str, Any] = {"prompt": "test"}
    if integration_ids is not None:
        params["integration_connections"] = [{"integration_id": iid, "credential_id": ""} for iid in integration_ids]
    if llm_model_id is not None:
        params["llm_model_id"] = llm_model_id
    if tool_strategy is not None:
        params["tool_selection_strategy"] = tool_strategy
    if tool_ids is not None:
        params["tool_selections"] = tool_ids
    return {
        "schema_version": "2.0.0",
        "triggers": [{"id": "trigger-0", "type": "manual_trigger", "parameters": {}}],
        "nodes": [{"id": "node-1", "type": "agentic", "parameters": params}],
        "edges": [{"from": "trigger-0", "to": "node-1"}],
    }


# ---------------------------------------------------------------------------
# Shared helpers — create DB records
# ---------------------------------------------------------------------------


async def _create_integration(
    session: AsyncSession,
    user: User,
    *,
    integration_type: str = IntegrationType.MCP_SERVER,
    scope: str = IntegrationScope.GLOBAL,
    enabled: bool = True,
    name: str | None = None,
) -> Integration:
    integration = Integration(
        name=name or f"intg-{uuid4().hex[:8]}",
        integration_type=integration_type,
        scope=scope,
        enabled=enabled,
        created_by=user.id,
        updated_by=user.id,
    )
    session.add(integration)
    await session.flush()
    return integration


async def _assign_to_project(session: AsyncSession, integration: Integration, project_id: UUID) -> None:
    session.add(IntegrationProjectAssignment(integration_id=integration.id, project_id=project_id))
    await session.flush()


async def _create_llm_model(
    session: AsyncSession,
    user: User,
    integration: Integration,
    *,
    enabled: bool = True,
    name: str | None = None,
) -> LLMModel:
    model = LLMModel(
        integration_id=integration.id,
        model_id=f"model-{uuid4().hex[:8]}",
        name=name or f"model-{uuid4().hex[:8]}",
        enabled=enabled,
        created_by=user.id,
    )
    session.add(model)
    await session.flush()
    return model


async def _create_tool(
    session: AsyncSession,
    user: User,
    integration: Integration,
    *,
    enabled: bool = True,
    name: str | None = None,
) -> Tool:
    tool_name = name or f"tool-{uuid4().hex[:8]}"
    tool = Tool(
        name=tool_name,
        namespaced_name=f"{integration.name}/{tool_name}",
        integration_id=integration.id,
        enabled=enabled,
        status=ToolStatus.AVAILABLE,
        created_by=user.id,
        updated_by=user.id,
    )
    session.add(tool)
    await session.flush()
    return tool


async def _create_project(session: AsyncSession, user: User) -> UUID:
    from syntara.authz.models import Project

    project = Project(name=f"project-{uuid4().hex[:8]}", created_by=user.id)
    session.add(project)
    await session.flush()
    return project.id


# ---------------------------------------------------------------------------
# Integration validation (AAP, MCP, LLM Provider)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestIntegrationValidation:
    """Existence, enabled, scope, and type checks for all integration types (AAP, MCP, LLM Provider)."""

    # --- AAP (via integration_id on aap_job_template nodes) ---

    async def test_valid_global_aap_passes(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(
            test_db_session, test_user, integration_type=IntegrationType.ANSIBLE_AUTOMATION_PLATFORM
        )
        definition = _aap_definition(str(intg.id))
        await validate_workflow_references(test_db_session, definition, test_project_id)

    async def test_valid_in_scope_aap_passes(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(
            test_db_session,
            test_user,
            integration_type=IntegrationType.ANSIBLE_AUTOMATION_PLATFORM,
            scope=IntegrationScope.PROJECT,
        )
        await _assign_to_project(test_db_session, intg, test_project_id)
        definition = _aap_definition(str(intg.id))
        await validate_workflow_references(test_db_session, definition, test_project_id)

    async def test_deleted_aap_rejects(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        definition = _aap_definition(str(uuid4()))
        with pytest.raises(SafeValueError, match="no longer available"):
            await validate_workflow_references(test_db_session, definition, test_project_id)

    async def test_disabled_aap_rejects(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(
            test_db_session,
            test_user,
            integration_type=IntegrationType.ANSIBLE_AUTOMATION_PLATFORM,
            enabled=False,
            name="disabled-aap",
        )
        definition = _aap_definition(str(intg.id))
        with pytest.raises(SafeValueError, match="'disabled-aap' is disabled"):
            await validate_workflow_references(test_db_session, definition, test_project_id)

    async def test_out_of_scope_aap_rejects(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        other_project = await _create_project(test_db_session, test_user)
        intg = await _create_integration(
            test_db_session,
            test_user,
            integration_type=IntegrationType.ANSIBLE_AUTOMATION_PLATFORM,
            scope=IntegrationScope.PROJECT,
            name="scoped-aap",
        )
        await _assign_to_project(test_db_session, intg, other_project)
        definition = _aap_definition(str(intg.id))
        with pytest.raises(SafeValueError, match="not accessible"):
            await validate_workflow_references(test_db_session, definition, test_project_id)

    async def test_wrong_type_mcp_in_aap_node_rejects(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(
            test_db_session, test_user, integration_type=IntegrationType.MCP_SERVER, name="my-mcp"
        )
        definition = _aap_definition(str(intg.id))
        with pytest.raises(SafeValueError, match="'my-mcp' is type 'mcp_server'"):
            await validate_workflow_references(test_db_session, definition, test_project_id)

    # --- MCP (via integration_connections on agentic nodes) ---

    async def test_valid_global_mcp_passes(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(test_db_session, test_user, integration_type=IntegrationType.MCP_SERVER)
        definition = _agentic_definition(integration_ids=[str(intg.id)])
        await validate_workflow_references(test_db_session, definition, test_project_id)

    async def test_valid_in_scope_mcp_passes(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(
            test_db_session,
            test_user,
            integration_type=IntegrationType.MCP_SERVER,
            scope=IntegrationScope.PROJECT,
        )
        await _assign_to_project(test_db_session, intg, test_project_id)
        definition = _agentic_definition(integration_ids=[str(intg.id)])
        await validate_workflow_references(test_db_session, definition, test_project_id)

    async def test_deleted_mcp_rejects(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        definition = _agentic_definition(integration_ids=[str(uuid4())])
        with pytest.raises(SafeValueError, match="no longer available"):
            await validate_workflow_references(test_db_session, definition, test_project_id)

    async def test_disabled_mcp_rejects(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(
            test_db_session,
            test_user,
            integration_type=IntegrationType.MCP_SERVER,
            enabled=False,
            name="disabled-mcp",
        )
        definition = _agentic_definition(integration_ids=[str(intg.id)])
        with pytest.raises(SafeValueError, match="'disabled-mcp' is disabled"):
            await validate_workflow_references(test_db_session, definition, test_project_id)

    async def test_out_of_scope_mcp_rejects(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        other_project = await _create_project(test_db_session, test_user)
        intg = await _create_integration(
            test_db_session,
            test_user,
            integration_type=IntegrationType.MCP_SERVER,
            scope=IntegrationScope.PROJECT,
            name="scoped-mcp",
        )
        await _assign_to_project(test_db_session, intg, other_project)
        definition = _agentic_definition(integration_ids=[str(intg.id)])
        with pytest.raises(SafeValueError, match="not accessible"):
            await validate_workflow_references(test_db_session, definition, test_project_id)

    async def test_wrong_type_aap_in_mcp_connection_rejects(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(
            test_db_session,
            test_user,
            integration_type=IntegrationType.ANSIBLE_AUTOMATION_PLATFORM,
            name="my-aap",
        )
        definition = _agentic_definition(integration_ids=[str(intg.id)])
        with pytest.raises(SafeValueError, match="'my-aap' is type 'ansible_automation_platform'"):
            await validate_workflow_references(test_db_session, definition, test_project_id)

    # --- LLM Provider (checked via llm_model_id → parent integration) ---

    async def test_disabled_llm_provider_rejects(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(
            test_db_session,
            test_user,
            integration_type=IntegrationType.LLM_PROVIDER,
            enabled=False,
            name="disabled-llm-provider",
        )
        model = await _create_llm_model(test_db_session, test_user, intg)
        definition = _agentic_definition(llm_model_id=str(model.id))
        with pytest.raises(SafeValueError, match="'disabled-llm-provider' is disabled"):
            await validate_workflow_references(test_db_session, definition, test_project_id)

    async def test_out_of_scope_llm_provider_rejects(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        other_project = await _create_project(test_db_session, test_user)
        intg = await _create_integration(
            test_db_session,
            test_user,
            integration_type=IntegrationType.LLM_PROVIDER,
            scope=IntegrationScope.PROJECT,
        )
        await _assign_to_project(test_db_session, intg, other_project)
        model = await _create_llm_model(test_db_session, test_user, intg)
        definition = _agentic_definition(llm_model_id=str(model.id))
        with pytest.raises(SafeValueError, match="not accessible"):
            await validate_workflow_references(test_db_session, definition, test_project_id)

    async def test_wrong_type_model_on_mcp_provider_rejects(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(
            test_db_session,
            test_user,
            integration_type=IntegrationType.MCP_SERVER,
            name="not-an-llm",
        )
        model = await _create_llm_model(test_db_session, test_user, intg)
        definition = _agentic_definition(llm_model_id=str(model.id))
        with pytest.raises(SafeValueError, match="'not-an-llm' is type 'mcp_server'"):
            await validate_workflow_references(test_db_session, definition, test_project_id)


# ---------------------------------------------------------------------------
# LLM Model validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLLMModelValidation:
    """Existence and enabled checks for LLM model references (llm_model_id on agentic nodes)."""

    async def test_valid_enabled_model_passes(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(test_db_session, test_user, integration_type=IntegrationType.LLM_PROVIDER)
        model = await _create_llm_model(test_db_session, test_user, intg)
        definition = _agentic_definition(llm_model_id=str(model.id))
        await validate_workflow_references(test_db_session, definition, test_project_id)

    async def test_deleted_model_rejects(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        definition = _agentic_definition(llm_model_id=str(uuid4()))
        with pytest.raises(SafeValueError, match="no longer available"):
            await validate_workflow_references(test_db_session, definition, test_project_id)

    async def test_disabled_model_rejects(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(test_db_session, test_user, integration_type=IntegrationType.LLM_PROVIDER)
        model = await _create_llm_model(test_db_session, test_user, intg, enabled=False, name="gpt-disabled")
        definition = _agentic_definition(llm_model_id=str(model.id))
        with pytest.raises(SafeValueError, match="'gpt-disabled' is disabled"):
            await validate_workflow_references(test_db_session, definition, test_project_id)


# ---------------------------------------------------------------------------
# Tool validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestToolValidation:
    """Auto-clear and warning findings for unavailable tools (tool_selections on agentic nodes)."""

    async def test_all_tools_available_no_findings(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(test_db_session, test_user)
        tools = [await _create_tool(test_db_session, test_user, intg) for _ in range(3)]
        definition = _agentic_definition(
            integration_ids=[str(intg.id)],
            tool_strategy="SELECTED",
            tool_ids=[str(t.id) for t in tools],
        )
        findings = await validate_workflow_references(test_db_session, definition, test_project_id)
        assert findings == []
        assert len(definition["nodes"][0]["parameters"]["tool_selections"]) == 3

    async def test_some_deleted_tools_auto_cleared(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(test_db_session, test_user)
        tool_a = await _create_tool(test_db_session, test_user, intg)
        tool_b = await _create_tool(test_db_session, test_user, intg)
        deleted_id = str(uuid4())
        definition = _agentic_definition(
            integration_ids=[str(intg.id)],
            tool_strategy="SELECTED",
            tool_ids=[str(tool_a.id), deleted_id, str(tool_b.id)],
        )
        findings = await validate_workflow_references(test_db_session, definition, test_project_id)
        assert len(findings) == 1
        assert findings[0].severity == "warning"
        assert "1 previously selected tool(s)" in findings[0].message
        assert definition["nodes"][0]["parameters"]["tool_selections"] == [str(tool_a.id), str(tool_b.id)]

    async def test_some_disabled_tools_auto_cleared(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(test_db_session, test_user)
        tool_ok = await _create_tool(test_db_session, test_user, intg)
        tool_disabled = await _create_tool(test_db_session, test_user, intg, enabled=False)
        definition = _agentic_definition(
            integration_ids=[str(intg.id)],
            tool_strategy="SELECTED",
            tool_ids=[str(tool_ok.id), str(tool_disabled.id)],
        )
        findings = await validate_workflow_references(test_db_session, definition, test_project_id)
        assert len(findings) == 1
        assert definition["nodes"][0]["parameters"]["tool_selections"] == [str(tool_ok.id)]

    async def test_all_tools_unavailable_switches_to_none(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(test_db_session, test_user)
        definition = _agentic_definition(
            integration_ids=[str(intg.id)],
            tool_strategy="SELECTED",
            tool_ids=[str(uuid4()), str(uuid4())],
        )
        findings = await validate_workflow_references(test_db_session, definition, test_project_id)
        assert len(findings) == 1
        assert "2 previously selected tool(s)" in findings[0].message
        params = definition["nodes"][0]["parameters"]
        assert params["tool_selection_strategy"] == "NONE"
        assert "tool_selections" not in params

    async def test_all_strategy_skips_tool_validation(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(test_db_session, test_user)
        definition = _agentic_definition(integration_ids=[str(intg.id)], tool_strategy="ALL")
        findings = await validate_workflow_references(test_db_session, definition, test_project_id)
        assert findings == []

    async def test_finding_includes_node_id(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(test_db_session, test_user)
        definition = _agentic_definition(
            integration_ids=[str(intg.id)],
            tool_strategy="SELECTED",
            tool_ids=[str(uuid4())],
        )
        findings = await validate_workflow_references(test_db_session, definition, test_project_id)
        assert len(findings) == 1
        assert findings[0].node_id == "node-1"


# ---------------------------------------------------------------------------
# Edge cases and validation ordering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestValidationEdgeCases:
    """Boundary conditions: no references, template expressions, multi-node, and validation ordering."""

    async def test_no_references_passes(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        definition = {
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger-0", "type": "manual_trigger", "parameters": {}}],
            "nodes": [{"id": "node-1", "type": "script", "parameters": {"language": "python", "script": "pass"}}],
            "edges": [{"from": "trigger-0", "to": "node-1"}],
        }
        findings = await validate_workflow_references(test_db_session, definition, test_project_id)
        assert findings == []

    async def test_template_expressions_skipped(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        definition = _aap_definition("{{ env.INTEGRATION_ID }}")
        findings = await validate_workflow_references(test_db_session, definition, test_project_id)
        assert findings == []

    async def test_multiple_nodes_first_bad_integration_blocks(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        good_intg = await _create_integration(test_db_session, test_user)
        definition = _agentic_definition(integration_ids=[str(good_intg.id), str(uuid4())])
        with pytest.raises(SafeValueError, match="no longer available"):
            await validate_workflow_references(test_db_session, definition, test_project_id)

    async def test_existence_checked_before_type(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        definition = _aap_definition(str(uuid4()))
        with pytest.raises(SafeValueError, match="no longer available"):
            await validate_workflow_references(test_db_session, definition, test_project_id)
