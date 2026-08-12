"""Tests for periodic analytics database queries using a real database.

All queries are tested against a real PostgreSQL database via test_db_session.
"""

from datetime import UTC, datetime, timedelta

from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.telemetry.events.integration_health import (
    CredentialHealth,
    CredentialInfo,
    IdentityProviderHealth,
    IdentityProviderInfo,
)
from syntara.telemetry.events.system_analytics import (
    CredentialCounts,
    ExecutionCounts,
    ModelUsage,
    WorkflowCounts,
)
from syntara.telemetry.queries import (
    query_credential_counts,
    query_credential_health,
    query_execution_counts,
    query_identity_provider_health,
    query_integration_health,
    query_model_usage,
    query_workflow_counts,
)
from syntara.workflows.models.execution import ExecutionStatus
from tests.integration.helpers.credential import CredentialFactory
from tests.integration.helpers.execution import ExecutionFactory
from tests.integration.helpers.identity_provider import IdentityProviderCreate
from tests.integration.helpers.token_usage import TokenUsageFactory
from tests.integration.helpers.workflow import WorkflowFactory


class TestQueryWorkflowCounts:
    """Tests for query_workflow_counts."""

    async def test_returns_counts(
        self,
        test_db_session: AsyncSession,
        workflow_factory: WorkflowFactory,
    ):
        await workflow_factory.create_many(7, is_enabled=True, prefix="enabled")
        await workflow_factory.create_many(3, is_enabled=False, prefix="disabled")
        await test_db_session.commit()

        result = await query_workflow_counts(test_db_session)

        assert isinstance(result, WorkflowCounts)
        assert result.total == 10
        assert result.enabled == 7
        assert result.disabled == 3

    async def test_handles_empty_database(self, test_db_session: AsyncSession):
        result = await query_workflow_counts(test_db_session)

        assert result.total == 0
        assert result.enabled == 0
        assert result.disabled == 0


class TestQueryExecutionCounts:
    """Tests for query_execution_counts."""

    async def test_counts_by_status(
        self,
        test_db_session: AsyncSession,
        workflow_factory: WorkflowFactory,
        execution_factory: ExecutionFactory,
    ):
        wf, version = await workflow_factory.create("exec-wf")
        completed_at = datetime.now(UTC) + timedelta(seconds=125)

        await execution_factory.create_many(
            wf,
            version,
            [
                (ExecutionStatus.COMPLETED, 40),
                (ExecutionStatus.FAILED, 5),
                (ExecutionStatus.RUNNING, 3),
                (ExecutionStatus.CANCELLED, 2),
                (ExecutionStatus.PENDING, 1),
                (ExecutionStatus.PAUSED, 1),
            ],
            completed_at=completed_at,
        )
        await test_db_session.commit()

        result = await query_execution_counts(test_db_session)

        assert isinstance(result, ExecutionCounts)
        assert result.total == 52
        assert result.completed == 40
        assert result.failed == 5
        assert result.running == 3
        assert result.cancelled == 2
        assert result.pending == 1
        assert result.paused == 1
        assert result.avg_duration_seconds > 0

    async def test_only_running(
        self,
        test_db_session: AsyncSession,
        workflow_factory: WorkflowFactory,
        execution_factory: ExecutionFactory,
    ):
        wf, version = await workflow_factory.create("running-wf")
        await execution_factory.create_many(wf, version, [(ExecutionStatus.RUNNING, 5)])
        await test_db_session.commit()

        result = await query_execution_counts(test_db_session)

        assert result.running == 5
        assert result.completed == 0
        assert result.total == 5


class TestQueryModelUsage:
    """Tests for query_model_usage."""

    async def test_returns_model_usage_list(
        self,
        test_db_session: AsyncSession,
        token_usage_factory: TokenUsageFactory,
    ):
        await token_usage_factory.create_many("gpt-4", 500, 200, 10)
        await token_usage_factory.create_many("claude-3", 600, 300, 5)
        await test_db_session.commit()

        result = await query_model_usage(test_db_session)

        assert len(result) == 2
        usage_by_model = {m.model: m for m in result}
        assert isinstance(result[0], ModelUsage)
        assert usage_by_model["gpt-4"].total_prompt_tokens == 5000
        assert usage_by_model["gpt-4"].total_completion_tokens == 2000
        assert usage_by_model["gpt-4"].total_tokens == 7000
        assert usage_by_model["gpt-4"].invocation_count == 10
        assert usage_by_model["claude-3"].total_prompt_tokens == 3000
        assert usage_by_model["claude-3"].total_completion_tokens == 1500
        assert usage_by_model["claude-3"].total_tokens == 4500
        assert usage_by_model["claude-3"].invocation_count == 5

    async def test_returns_empty_list_when_no_usage(self, test_db_session: AsyncSession):
        result = await query_model_usage(test_db_session)

        assert result == []


class TestQueryCredentialCounts:
    """Tests for query_credential_counts."""

    async def test_returns_counts_by_type(
        self,
        test_db_session: AsyncSession,
        credential_factory: CredentialFactory,
    ):
        bearer_type = await credential_factory.create_type("HTTP Bearer Token")
        llm_type = await credential_factory.create_type("LLM Provider")
        ssh_type = await credential_factory.create_type("SSH Key")
        project = await credential_factory.create_project()

        await credential_factory.create_many(bearer_type, project, 3, prefix="bearer")
        await credential_factory.create_many(llm_type, project, 2, prefix="llm")
        await credential_factory.create_many(ssh_type, project, 1, prefix="ssh")
        await test_db_session.commit()

        result = await query_credential_counts(test_db_session)

        assert isinstance(result, CredentialCounts)
        assert result.total == 6
        assert result.type == {
            "HTTP Bearer Token": 3,
            "LLM Provider": 2,
            "SSH Key": 1,
        }

    async def test_handles_no_credentials(self, test_db_session: AsyncSession):
        result = await query_credential_counts(test_db_session)

        assert result.total == 0
        assert result.type == {}


class TestQueryIntegrationHealth:
    """Tests for query_integration_health (now queries mcp_server Integrations)."""

    async def test_handles_no_integrations(self, test_db_session: AsyncSession):
        result = await query_integration_health(test_db_session)

        assert result.total == 0
        assert result.items == {}


class TestQueryIdentityProviderHealth:
    """Tests for query_identity_provider_health."""

    async def test_returns_health(
        self,
        test_db_session: AsyncSession,
        identity_provider_create: IdentityProviderCreate,
    ):
        await identity_provider_create.create_many(2, prefix="enabled", enabled=True)
        await identity_provider_create.create("disabled-0", enabled=False)
        await test_db_session.commit()

        result = await query_identity_provider_health(test_db_session)

        assert isinstance(result, IdentityProviderHealth)
        assert result.total == 3
        assert result.items == {
            "oidc": IdentityProviderInfo(enabled=2, disabled=1),
        }

    async def test_handles_no_providers(self, test_db_session: AsyncSession):
        result = await query_identity_provider_health(test_db_session)

        assert result.total == 0
        assert result.items == {}


class TestQueryCredentialHealth:
    """Tests for query_credential_health."""

    async def test_returns_health_grouped_by_type(
        self,
        test_db_session: AsyncSession,
        credential_factory: CredentialFactory,
    ):
        bearer_type = await credential_factory.create_type("HTTP Bearer Token")
        ssh_type = await credential_factory.create_type("SSH Key")
        project = await credential_factory.create_project()

        await credential_factory.create(bearer_type, project, "bearer-enabled", enabled=True)
        await credential_factory.create(bearer_type, project, "bearer-disabled", enabled=False)
        await credential_factory.create(ssh_type, project, "ssh-disabled", enabled=False)
        await test_db_session.commit()

        result = await query_credential_health(test_db_session)

        assert isinstance(result, CredentialHealth)
        assert result.total == 3
        assert result.enabled == 1
        assert result.disabled == 2
        assert result.items == {
            "HTTP Bearer Token": CredentialInfo(enabled=1, disabled=1),
            "SSH Key": CredentialInfo(enabled=0, disabled=1),
        }

    async def test_handles_no_credentials(self, test_db_session: AsyncSession):
        result = await query_credential_health(test_db_session)

        assert result.total == 0
        assert result.enabled == 0
        assert result.disabled == 0
        assert result.items == {}

    async def test_used_in_nodes_zero_when_no_workflows(
        self,
        test_db_session: AsyncSession,
        credential_factory: CredentialFactory,
    ):
        """used_in_nodes is 0 when no workflows reference credentials."""
        bearer_type = await credential_factory.create_type("Bearer")
        project = await credential_factory.create_project()
        await credential_factory.create_many(bearer_type, project, 5, prefix="bearer")
        await test_db_session.commit()

        result = await query_credential_counts(test_db_session)

        assert result.total == 5
        assert result.used_in_nodes == 0
