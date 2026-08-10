"""Unit tests for execution-time reference validation activity.

Tests validate_node_references against a real database, verifying
that workflows fail with clear non-retryable errors when referenced
resources become unavailable between save and execution.
"""

from collections.abc import Generator
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession
from temporalio.exceptions import ApplicationError

from syntara.core.models import User
from syntara.integrations.models.integration import (
    Integration,
    IntegrationProjectAssignment,
    IntegrationScope,
    IntegrationType,
)
from syntara.integrations.models.llm_model import LLMModel
from syntara.tool_manager.models.tool import Tool, ToolStatus
from syntara.workflows.workflow_engine.activities import integration_scope_activity
from syntara.workflows.workflow_engine.activities.integration_scope_activity import (
    _validate_node,
    validate_node_references,
)

# ---------------------------------------------------------------------------
# Shared helpers
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


@pytest.fixture(autouse=True)
def _use_test_session(test_db_session: AsyncSession) -> Generator[None]:
    """Route the activity's DB queries through the test session."""
    original = integration_scope_activity._session_factory

    class _TestSessionCtx:
        async def __aenter__(self) -> AsyncSession:
            return test_db_session

        async def __aexit__(self, *args: object) -> None:
            pass

    integration_scope_activity._session_factory = _TestSessionCtx  # type: ignore[assignment]
    yield
    integration_scope_activity._session_factory = original


# ---------------------------------------------------------------------------
# AAP integration scenarios
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAAPIntegrationAtExecutionTime:
    """AAP nodes fail execution when their integration becomes unavailable."""

    async def test_valid_global_aap_passes(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(
            test_db_session, test_user, integration_type=IntegrationType.ANSIBLE_AUTOMATION_PLATFORM
        )
        refs: dict[str, Any] = {"integration_id": str(intg.id)}
        await _validate_node(test_db_session, "aap_job_template", "node-1", refs, str(test_project_id))

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
        refs: dict[str, Any] = {"integration_id": str(intg.id)}
        await _validate_node(test_db_session, "aap_job_template", "node-1", refs, str(test_project_id))

    async def test_deleted_aap_fails_execution(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        refs: dict[str, Any] = {"integration_id": str(uuid4())}
        with pytest.raises(ApplicationError, match="no longer available") as exc_info:
            await _validate_node(test_db_session, "aap_job_template", "node-1", refs, str(test_project_id))
        assert exc_info.value.non_retryable
        assert exc_info.value.type == "IntegrationNotFoundError"

    async def test_disabled_aap_fails_execution(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(
            test_db_session,
            test_user,
            integration_type=IntegrationType.ANSIBLE_AUTOMATION_PLATFORM,
            enabled=False,
            name="disabled-aap",
        )
        refs: dict[str, Any] = {"integration_id": str(intg.id)}
        with pytest.raises(ApplicationError, match="'disabled-aap' is disabled") as exc_info:
            await _validate_node(test_db_session, "aap_job_template", "node-1", refs, str(test_project_id))
        assert exc_info.value.type == "IntegrationDisabledError"

    async def test_out_of_scope_aap_fails_execution(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        other_project = await _create_project(test_db_session, test_user)
        intg = await _create_integration(
            test_db_session,
            test_user,
            integration_type=IntegrationType.ANSIBLE_AUTOMATION_PLATFORM,
            scope=IntegrationScope.PROJECT,
        )
        await _assign_to_project(test_db_session, intg, other_project)
        refs: dict[str, Any] = {"integration_id": str(intg.id)}
        with pytest.raises(ApplicationError, match="not accessible") as exc_info:
            await _validate_node(test_db_session, "aap_job_template", "node-1", refs, str(test_project_id))
        assert exc_info.value.type == "IntegrationNotAccessibleError"

    async def test_wrong_type_mcp_in_aap_node_fails_execution(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(
            test_db_session, test_user, integration_type=IntegrationType.MCP_SERVER, name="my-mcp"
        )
        refs: dict[str, Any] = {"integration_id": str(intg.id)}
        with pytest.raises(ApplicationError, match="'my-mcp' is type 'mcp_server'") as exc_info:
            await _validate_node(test_db_session, "aap_job_template", "node-1", refs, str(test_project_id))
        assert exc_info.value.type == "IntegrationTypeMismatchError"


# ---------------------------------------------------------------------------
# MCP integration scenarios (agentic nodes)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMCPIntegrationAtExecutionTime:
    """Agentic nodes fail execution when their MCP integration becomes unavailable."""

    async def test_valid_global_mcp_passes(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(test_db_session, test_user)
        refs: dict[str, Any] = {"integration_connections": [{"integration_id": str(intg.id)}]}
        await _validate_node(test_db_session, "agentic", "node-1", refs, str(test_project_id))

    async def test_deleted_mcp_fails_execution(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        refs: dict[str, Any] = {"integration_connections": [{"integration_id": str(uuid4())}]}
        with pytest.raises(ApplicationError, match="no longer available") as exc_info:
            await _validate_node(test_db_session, "agentic", "node-1", refs, str(test_project_id))
        assert exc_info.value.type == "IntegrationNotFoundError"

    async def test_disabled_mcp_fails_execution(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(test_db_session, test_user, enabled=False, name="disabled-mcp")
        refs: dict[str, Any] = {"integration_connections": [{"integration_id": str(intg.id)}]}
        with pytest.raises(ApplicationError, match="'disabled-mcp' is disabled") as exc_info:
            await _validate_node(test_db_session, "agentic", "node-1", refs, str(test_project_id))
        assert exc_info.value.type == "IntegrationDisabledError"

    async def test_out_of_scope_mcp_fails_execution(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        other_project = await _create_project(test_db_session, test_user)
        intg = await _create_integration(test_db_session, test_user, scope=IntegrationScope.PROJECT)
        await _assign_to_project(test_db_session, intg, other_project)
        refs: dict[str, Any] = {"integration_connections": [{"integration_id": str(intg.id)}]}
        with pytest.raises(ApplicationError, match="not accessible") as exc_info:
            await _validate_node(test_db_session, "agentic", "node-1", refs, str(test_project_id))
        assert exc_info.value.type == "IntegrationNotAccessibleError"

    async def test_wrong_type_aap_in_mcp_connection_fails_execution(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(
            test_db_session, test_user, integration_type=IntegrationType.ANSIBLE_AUTOMATION_PLATFORM, name="my-aap"
        )
        refs: dict[str, Any] = {"integration_connections": [{"integration_id": str(intg.id)}]}
        with pytest.raises(ApplicationError, match="'my-aap' is type 'ansible_automation_platform'") as exc_info:
            await _validate_node(test_db_session, "agentic", "node-1", refs, str(test_project_id))
        assert exc_info.value.type == "IntegrationTypeMismatchError"


# ---------------------------------------------------------------------------
# LLM model and provider scenarios
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLLMValidationAtExecutionTime:
    """Agentic nodes fail execution when their LLM model or provider becomes unavailable."""

    async def test_valid_enabled_model_passes(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(test_db_session, test_user, integration_type=IntegrationType.LLM_PROVIDER)
        model = await _create_llm_model(test_db_session, test_user, intg)
        refs: dict[str, Any] = {"llm_model_id": str(model.id)}
        await _validate_node(test_db_session, "agentic", "node-1", refs, str(test_project_id))

    async def test_deleted_model_fails_execution(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        refs: dict[str, Any] = {"llm_model_id": str(uuid4())}
        with pytest.raises(ApplicationError, match="no longer available") as exc_info:
            await _validate_node(test_db_session, "agentic", "node-1", refs, str(test_project_id))
        assert exc_info.value.type == "LLMModelNotFoundError"

    async def test_disabled_model_fails_execution(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(test_db_session, test_user, integration_type=IntegrationType.LLM_PROVIDER)
        model = await _create_llm_model(test_db_session, test_user, intg, enabled=False, name="gpt-disabled")
        refs: dict[str, Any] = {"llm_model_id": str(model.id)}
        with pytest.raises(ApplicationError, match="'gpt-disabled' is disabled") as exc_info:
            await _validate_node(test_db_session, "agentic", "node-1", refs, str(test_project_id))
        assert exc_info.value.type == "LLMModelDisabledError"

    async def test_disabled_provider_fails_execution(
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
        refs: dict[str, Any] = {"llm_model_id": str(model.id)}
        with pytest.raises(ApplicationError, match="'disabled-llm-provider' is disabled") as exc_info:
            await _validate_node(test_db_session, "agentic", "node-1", refs, str(test_project_id))
        assert exc_info.value.type == "IntegrationDisabledError"

    async def test_out_of_scope_provider_fails_execution(
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
        refs: dict[str, Any] = {"llm_model_id": str(model.id)}
        with pytest.raises(ApplicationError, match="not accessible") as exc_info:
            await _validate_node(test_db_session, "agentic", "node-1", refs, str(test_project_id))
        assert exc_info.value.type == "IntegrationNotAccessibleError"


# ---------------------------------------------------------------------------
# Tool availability scenarios
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestToolValidationAtExecutionTime:
    """Agentic nodes fail execution when selected tools become unavailable."""

    async def test_all_tools_available_passes(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(test_db_session, test_user)
        tools = [await _create_tool(test_db_session, test_user, intg) for _ in range(3)]
        refs: dict[str, Any] = {
            "integration_connections": [{"integration_id": str(intg.id)}],
            "tool_selection_strategy": "SELECTED",
            "tool_selections": [str(t.id) for t in tools],
        }
        await _validate_node(test_db_session, "agentic", "node-1", refs, str(test_project_id))

    async def test_some_deleted_tools_fail_execution(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(test_db_session, test_user)
        tool = await _create_tool(test_db_session, test_user, intg)
        refs: dict[str, Any] = {
            "integration_connections": [{"integration_id": str(intg.id)}],
            "tool_selection_strategy": "SELECTED",
            "tool_selections": [str(tool.id), str(uuid4())],
        }
        with pytest.raises(ApplicationError, match="1 selected tool") as exc_info:
            await _validate_node(test_db_session, "agentic", "node-1", refs, str(test_project_id))
        assert exc_info.value.type == "ToolsUnavailableError"
        assert exc_info.value.non_retryable

    async def test_some_disabled_tools_fail_execution(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(test_db_session, test_user)
        tool_ok = await _create_tool(test_db_session, test_user, intg)
        tool_disabled = await _create_tool(test_db_session, test_user, intg, enabled=False)
        refs: dict[str, Any] = {
            "integration_connections": [{"integration_id": str(intg.id)}],
            "tool_selection_strategy": "SELECTED",
            "tool_selections": [str(tool_ok.id), str(tool_disabled.id)],
        }
        with pytest.raises(ApplicationError, match="1 selected tool") as exc_info:
            await _validate_node(test_db_session, "agentic", "node-1", refs, str(test_project_id))
        assert exc_info.value.type == "ToolsUnavailableError"

    async def test_all_tools_unavailable_fails_execution(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(test_db_session, test_user)
        refs: dict[str, Any] = {
            "integration_connections": [{"integration_id": str(intg.id)}],
            "tool_selection_strategy": "SELECTED",
            "tool_selections": [str(uuid4()), str(uuid4())],
        }
        with pytest.raises(ApplicationError, match="2 selected tool") as exc_info:
            await _validate_node(test_db_session, "agentic", "node-1", refs, str(test_project_id))
        assert exc_info.value.type == "ToolsUnavailableError"

    async def test_disabled_mcp_integration_caught_via_tool_parent(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(test_db_session, test_user, enabled=False, name="disabled-mcp")
        tool = await _create_tool(test_db_session, test_user, intg)
        refs: dict[str, Any] = {
            "tool_selection_strategy": "SELECTED",
            "tool_selections": [str(tool.id)],
        }
        with pytest.raises(ApplicationError, match="'disabled-mcp' is disabled") as exc_info:
            await _validate_node(test_db_session, "agentic", "node-1", refs, str(test_project_id))
        assert exc_info.value.type == "IntegrationDisabledError"

    async def test_out_of_scope_mcp_caught_via_tool_parent(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        other_project = await _create_project(test_db_session, test_user)
        intg = await _create_integration(test_db_session, test_user, scope=IntegrationScope.PROJECT)
        await _assign_to_project(test_db_session, intg, other_project)
        tool = await _create_tool(test_db_session, test_user, intg)
        refs: dict[str, Any] = {
            "tool_selection_strategy": "SELECTED",
            "tool_selections": [str(tool.id)],
        }
        with pytest.raises(ApplicationError, match="not accessible") as exc_info:
            await _validate_node(test_db_session, "agentic", "node-1", refs, str(test_project_id))
        assert exc_info.value.type == "IntegrationNotAccessibleError"

    async def test_all_strategy_skips_tool_check(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(test_db_session, test_user)
        refs: dict[str, Any] = {
            "integration_connections": [{"integration_id": str(intg.id)}],
            "tool_selection_strategy": "ALL",
        }
        await _validate_node(test_db_session, "agentic", "node-1", refs, str(test_project_id))


# ---------------------------------------------------------------------------
# Edge cases and defensive behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestExecutionTimeEdgeCases:
    """Boundary conditions: no references, empty project, templates, error properties."""

    async def test_script_node_skips_validation(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        refs: dict[str, Any] = {"language": "python", "script": "pass"}
        await _validate_node(test_db_session, "script", "node-1", refs, str(test_project_id))

    async def test_empty_project_id_skips_scope_but_checks_existence(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(
            test_db_session,
            test_user,
            integration_type=IntegrationType.ANSIBLE_AUTOMATION_PLATFORM,
            scope=IntegrationScope.PROJECT,
        )
        refs: dict[str, Any] = {"integration_id": str(intg.id)}
        await _validate_node(test_db_session, "aap_job_template", "node-1", refs, "")

    async def test_template_expression_skipped(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        refs: dict[str, Any] = {"integration_id": "{{ env.AAP_INTEGRATION }}"}
        await _validate_node(test_db_session, "aap_job_template", "node-1", refs, str(test_project_id))

    async def test_multiple_connections_first_invalid_fails(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        good_intg = await _create_integration(test_db_session, test_user)
        refs: dict[str, Any] = {
            "integration_connections": [
                {"integration_id": str(good_intg.id)},
                {"integration_id": str(uuid4())},
            ]
        }
        with pytest.raises(ApplicationError, match="no longer available"):
            await _validate_node(test_db_session, "agentic", "node-1", refs, str(test_project_id))

    async def test_all_errors_are_non_retryable(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        refs: dict[str, Any] = {"integration_id": str(uuid4())}
        with pytest.raises(ApplicationError) as exc_info:
            await _validate_node(test_db_session, "aap_job_template", "node-1", refs, str(test_project_id))
        assert exc_info.value.non_retryable is True

    async def test_error_message_includes_names_not_uuids(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        intg = await _create_integration(
            test_db_session,
            test_user,
            integration_type=IntegrationType.ANSIBLE_AUTOMATION_PLATFORM,
            enabled=False,
            name="My AAP Controller",
        )
        refs: dict[str, Any] = {"integration_id": str(intg.id)}
        with pytest.raises(ApplicationError, match="My AAP Controller"):
            await _validate_node(test_db_session, "aap_job_template", "node-1", refs, str(test_project_id))

    async def test_out_of_scope_error_does_not_leak_integration_name(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        other_project = await _create_project(test_db_session, test_user)
        intg = await _create_integration(
            test_db_session,
            test_user,
            integration_type=IntegrationType.ANSIBLE_AUTOMATION_PLATFORM,
            scope=IntegrationScope.PROJECT,
            name="Secret-Internal-Name",
        )
        await _assign_to_project(test_db_session, intg, other_project)
        refs: dict[str, Any] = {"integration_id": str(intg.id)}
        with pytest.raises(ApplicationError) as exc_info:
            await _validate_node(test_db_session, "aap_job_template", "node-1", refs, str(test_project_id))
        assert "Secret-Internal-Name" not in str(exc_info.value)
        assert exc_info.value.type == "IntegrationNotAccessibleError"

    async def test_none_project_id_skips_scope_but_checks_existence(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        intg = await _create_integration(
            test_db_session,
            test_user,
            integration_type=IntegrationType.ANSIBLE_AUTOMATION_PLATFORM,
            scope=IntegrationScope.PROJECT,
        )
        refs: dict[str, Any] = {"integration_id": str(intg.id)}
        await _validate_node(
            test_db_session,
            "aap_job_template",
            "node-1",
            refs,
            None,  # type: ignore[arg-type]
        )

    async def test_invalid_uuid_in_mcp_connection_skipped(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        refs: dict[str, Any] = {"integration_connections": [{"integration_id": "not-a-uuid"}]}
        await _validate_node(test_db_session, "agentic", "node-1", refs, str(test_project_id))


@pytest.mark.asyncio
class TestDatabaseErrorWrapping:
    """Verify that unexpected exceptions are wrapped as non-retryable ApplicationError."""

    async def test_database_error_wrapped_as_non_retryable(self) -> None:
        original = integration_scope_activity._session_factory

        class _BrokenSession:
            async def __aenter__(self) -> None:
                msg = "connection pool exhausted"
                raise RuntimeError(msg)

            async def __aexit__(self, *args: object) -> None:
                pass

        integration_scope_activity._session_factory = _BrokenSession  # type: ignore[assignment]
        try:
            refs: dict[str, Any] = {"integration_id": str(uuid4())}
            with pytest.raises(ApplicationError, match="Database error") as exc_info:
                await validate_node_references("aap_job_template", "node-1", refs, str(uuid4()))
            assert exc_info.value.non_retryable is True
        finally:
            integration_scope_activity._session_factory = original
