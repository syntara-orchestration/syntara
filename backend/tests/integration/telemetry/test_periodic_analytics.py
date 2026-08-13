"""Integration tests for periodic analytics collection flow.

Validates that:
1. _collect_and_send correctly queries, builds events, and sends them
   through TelemetryClientRegistry.send_event() using a real database.
2. Query functions produce correct SQL against a real PostgreSQL database
   with actual records, soft-delete filtering, and enum handling.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.models.invocation import Invocation
from syntara.agent_orchestrator.token_manager.models import TokenUsageRecord
from syntara.core.models import User
from syntara.integrations.models.integration import Integration
from syntara.telemetry.api_usage_accumulator import AccumulatorSnapshot
from syntara.telemetry.client import TelemetryClientRegistry
from syntara.telemetry.periodic_collector import _collect_and_send
from syntara.telemetry.queries import (
    query_credential_counts,
    query_execution_counts,
    query_model_usage,
    query_tool_counts,
    query_workflow_counts,
)
from syntara.tool_manager.models.tool import Tool
from syntara.tool_manager.models.usage_counter import CounterType, UsageCounter, WindowDuration
from syntara.workflows.models import Workflow, WorkflowVersion
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.models.workflow_publish_event import PublishAction, WorkflowPublishEvent
from tests.integration.helpers.credential import CredentialFactory
from tests.integration.helpers.execution import ExecutionFactory
from tests.integration.helpers.token_usage import TokenUsageFactory
from tests.integration.helpers.workflow import WorkflowFactory


class TestPeriodicAnalyticsFlow:
    """Integration test: full periodic collection lifecycle with real database."""

    @pytest.fixture
    def registry_with_mock_client(
        self,
    ) -> tuple[TelemetryClientRegistry, MagicMock]:
        """Create a registry with a mock Segment client.

        Only the external Segment client is mocked - database queries are real.
        """
        registry = TelemetryClientRegistry()
        mock_client = MagicMock()
        registry._client = mock_client
        registry._anonymous_id = "test-anonymous-001"
        registry._entitlement_id = "test-entitlement-001"
        return registry, mock_client

    async def test_collect_and_send_produces_correct_segment_call(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        registry_with_mock_client: tuple[TelemetryClientRegistry, MagicMock],
        mock_session_factory: async_sessionmaker[AsyncSession],
        workflow_factory: WorkflowFactory,
        execution_factory: ExecutionFactory,
        token_usage_factory: TokenUsageFactory,
    ) -> None:
        """Full integration test: insert real data, run collector, verify Segment call."""
        registry, mock_client = registry_with_mock_client

        # Create workflows: 3 enabled, 2 disabled
        await workflow_factory.create_many(3, is_enabled=True, prefix="enabled")
        await workflow_factory.create_many(2, is_enabled=False, prefix="disabled")

        # Create a workflow and version for executions
        exec_wf, exec_version = await workflow_factory.create("exec-wf")

        # Create executions with various statuses
        now = datetime.now(UTC)
        completed_at = now + timedelta(seconds=60)
        await execution_factory.create_many(
            exec_wf,
            exec_version,
            [
                (ExecutionStatus.COMPLETED, 2),
                (ExecutionStatus.FAILED, 1),
                (ExecutionStatus.RUNNING, 1),
            ],
            completed_at=completed_at,
        )

        # Create invocations with token usage records for model_usage aggregation
        await token_usage_factory.create_many("gpt-4", 1000, 500, 3, timestamp=now)
        await token_usage_factory.create_many("claude-3", 600, 300, 2, timestamp=now)

        await test_db_session.commit()

        # Run the collect_and_send function with real database queries
        await _collect_and_send(mock_session_factory, registry)

        # Verify Segment calls (system_analytics + integration_health)
        assert mock_client.track.call_count == 2
        calls_by_event = {c.kwargs["event"]: c.kwargs for c in mock_client.track.call_args_list}
        call_kwargs = calls_by_event["system_analytics"]

        assert call_kwargs["anonymous_id"] == "test-anonymous-001"
        assert call_kwargs["event"] == "system_analytics"

        props = call_kwargs["properties"]
        assert props["entitlement_id"] == "test-entitlement-001"

        # Verify workflow counts (3 enabled + 2 disabled + 1 exec_wf = 6 total, 4 enabled)
        assert props["workflows"]["total"] == 6
        assert props["workflows"]["enabled"] == 4
        assert props["workflows"]["disabled"] == 2

        # Verify execution counts
        assert props["executions"]["total"] == 4
        assert props["executions"]["completed"] == 2
        assert props["executions"]["failed"] == 1
        assert props["executions"]["running"] == 1

        # No credentials inserted in this test
        assert props["credentials"]["total"] == 0
        assert props["credentials"]["type"] == {}
        assert props["credentials"]["used_in_nodes"] == 0

        assert props["config"]["feature_flags_enabled"] == []

        # Verify tool counts (no usage_counter rows inserted, so all zeros)
        assert props["tools"]["success_count"] == 0
        assert props["tools"]["total_executions"] == 0

        # Verify model usage aggregation
        model_usage = props["model_usage"]
        assert len(model_usage) == 2
        usage_by_model = {m["model"]: m for m in model_usage}
        assert usage_by_model["gpt-4"]["total_prompt_tokens"] == 3000
        assert usage_by_model["gpt-4"]["total_completion_tokens"] == 1500
        assert usage_by_model["gpt-4"]["total_tokens"] == 4500
        assert usage_by_model["gpt-4"]["invocation_count"] == 3
        assert usage_by_model["claude-3"]["total_prompt_tokens"] == 1200
        assert usage_by_model["claude-3"]["total_completion_tokens"] == 600
        assert usage_by_model["claude-3"]["total_tokens"] == 1800
        assert usage_by_model["claude-3"]["invocation_count"] == 2

    async def test_no_state_between_cycles(
        self,
        test_db_session: AsyncSession,
        registry_with_mock_client: tuple[TelemetryClientRegistry, MagicMock],
        mock_session_factory: async_sessionmaker[AsyncSession],
        workflow_factory: WorkflowFactory,
    ) -> None:
        """Each collection cycle is independent — no delta tracking."""
        registry, mock_client = registry_with_mock_client

        await workflow_factory.create("test-wf")
        await test_db_session.commit()

        # Run twice
        await _collect_and_send(mock_session_factory, registry)
        await _collect_and_send(mock_session_factory, registry)

        # Each cycle sends 2 events (system_analytics + integration_health)
        assert mock_client.track.call_count == 4
        analytics_calls = [c for c in mock_client.track.call_args_list if c.kwargs["event"] == "system_analytics"]
        assert len(analytics_calls) == 2
        assert analytics_calls[0].kwargs["properties"] == analytics_calls[1].kwargs["properties"]

    async def test_empty_database_produces_zero_counts(
        self,
        test_db_session: AsyncSession,
        registry_with_mock_client: tuple[TelemetryClientRegistry, MagicMock],
        mock_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Collector handles empty database gracefully."""
        registry, mock_client = registry_with_mock_client

        # No data inserted - database is empty (test_db_session ensures truncation)
        await _collect_and_send(mock_session_factory, registry)

        assert mock_client.track.call_count == 2
        calls_by_event = {c.kwargs["event"]: c.kwargs for c in mock_client.track.call_args_list}
        props = calls_by_event["system_analytics"]["properties"]

        assert props["workflows"]["total"] == 0
        assert props["workflows"]["enabled"] == 0
        assert props["executions"]["total"] == 0
        assert props["credentials"]["total"] == 0
        assert props["credentials"]["type"] == {}
        assert props["tools"]["total_executions"] == 0
        assert props["tools"]["distinct_tools"] == 0
        assert props["model_usage"] == []
        assert props["executions"]["by_trigger_type"] == {}
        assert props["executions"]["by_interface"] == {}

        # Verify new fields default to empty when accumulator has no data
        assert props["unique_callers"]["total"] == 0
        assert props["unique_callers"]["by_principal_type"] == {}
        assert props["unique_callers"]["by_interface"] == {}
        assert props["feature_usage"] == []

    async def test_accumulator_data_appears_in_segment_event(
        self,
        test_db_session: AsyncSession,
        registry_with_mock_client: tuple[TelemetryClientRegistry, MagicMock],
        mock_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Accumulator snapshot data is included in the system_analytics Segment event."""
        registry, mock_client = registry_with_mock_client

        mock_accumulator = MagicMock()
        mock_accumulator.drain.return_value = AccumulatorSnapshot(
            caller_ids=frozenset({"hash-a", "hash-b", "hash-c"}),
            callers_by_type={"user": 2, "service_account": 1},
            callers_by_interface={"api": 2, "ui": 1},
            feature_usage={
                ("/api/v1/workflows", "GET", "api"): 10,
                ("/api/v1/executions", "POST", "ui"): 3,
            },
        )

        with patch(
            "syntara.telemetry.periodic_collector.get_accumulator",
            return_value=mock_accumulator,
        ):
            await _collect_and_send(mock_session_factory, registry)

        calls_by_event = {c.kwargs["event"]: c.kwargs for c in mock_client.track.call_args_list}
        props = calls_by_event["system_analytics"]["properties"]

        assert props["unique_callers"]["total"] == 3
        assert props["unique_callers"]["by_principal_type"] == {"user": 2, "service_account": 1}
        assert props["unique_callers"]["by_interface"] == {"api": 2, "ui": 1}
        assert len(props["feature_usage"]) == 2

        usage_by_endpoint = {e["endpoint_group"]: e for e in props["feature_usage"]}
        assert usage_by_endpoint["/api/v1/workflows"]["request_count"] == 10
        assert usage_by_endpoint["/api/v1/workflows"]["http_method"] == "GET"
        assert usage_by_endpoint["/api/v1/workflows"]["interface"] == "api"
        assert usage_by_endpoint["/api/v1/executions"]["request_count"] == 3
        assert usage_by_endpoint["/api/v1/executions"]["interface"] == "ui"

    async def test_soft_deleted_records_excluded(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        registry_with_mock_client: tuple[TelemetryClientRegistry, MagicMock],
        mock_session_factory: async_sessionmaker[AsyncSession],
        workflow_factory: WorkflowFactory,
    ) -> None:
        """Soft-deleted records are excluded from analytics."""
        registry, mock_client = registry_with_mock_client

        # Create an active workflow
        await workflow_factory.create("active-wf")

        # Create a soft-deleted workflow
        deleted_wf, _ = await workflow_factory.create("deleted-wf")
        deleted_wf.soft_delete(test_user.id)

        await test_db_session.commit()

        await _collect_and_send(mock_session_factory, registry)

        calls_by_event = {c.kwargs["event"]: c.kwargs for c in mock_client.track.call_args_list}
        props = calls_by_event["system_analytics"]["properties"]

        # Only active records should be counted
        assert props["workflows"]["total"] == 1
        assert props["credentials"]["total"] == 0


# ============================================================================
# Real-DB Query Integration Tests
# ============================================================================


class TestQueryWorkflowCountsRealDB:
    """Integration tests for query_workflow_counts against real PostgreSQL."""

    async def test_empty_database(self, test_db_session: AsyncSession):
        result = await query_workflow_counts(test_db_session)
        assert result.total == 0
        assert result.enabled == 0
        assert result.disabled == 0

    async def test_counts_enabled_and_disabled(
        self,
        test_db_session: AsyncSession,
        workflow_factory: WorkflowFactory,
    ):
        """Insert workflows with different is_enabled states and verify counts."""
        await workflow_factory.create_many(3, is_enabled=True, prefix="enabled")
        await workflow_factory.create_many(2, is_enabled=False, prefix="disabled")
        await test_db_session.commit()

        result = await query_workflow_counts(test_db_session)

        assert result.total == 5
        assert result.enabled == 3
        assert result.disabled == 2

    async def test_excludes_soft_deleted_workflows(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        workflow_factory: WorkflowFactory,
    ):
        """Soft-deleted workflows must not be counted."""
        await workflow_factory.create("active-wf")

        deleted_wf, _ = await workflow_factory.create("deleted-wf")
        deleted_wf.soft_delete(test_user.id)

        await test_db_session.commit()

        result = await query_workflow_counts(test_db_session)

        assert result.total == 1
        assert result.enabled == 1


class TestQueryExecutionCountsRealDB:
    """Integration tests for query_execution_counts against real PostgreSQL."""

    async def test_empty_database(self, test_db_session: AsyncSession):
        result = await query_execution_counts(test_db_session)
        assert result.total == 0
        assert result.avg_duration_seconds == 0.0

    async def test_counts_by_status(
        self,
        test_db_session: AsyncSession,
        workflow_factory: WorkflowFactory,
        execution_factory: ExecutionFactory,
    ):
        """Insert executions with various statuses and verify group_by."""
        wf, version = await workflow_factory.create()

        completed_at = datetime.now(UTC) + timedelta(seconds=10)
        await execution_factory.create_many(
            wf,
            version,
            [
                (ExecutionStatus.COMPLETED, 2),
                (ExecutionStatus.FAILED, 1),
                (ExecutionStatus.RUNNING, 1),
                (ExecutionStatus.PENDING, 1),
            ],
            completed_at=completed_at,
        )
        await test_db_session.commit()

        result = await query_execution_counts(test_db_session)

        assert result.total == 5
        assert result.completed == 2
        assert result.failed == 1
        assert result.running == 1
        assert result.pending == 1

    async def test_avg_duration_calculation(
        self,
        test_db_session: AsyncSession,
        workflow_factory: WorkflowFactory,
        execution_factory: ExecutionFactory,
    ):
        """Verify avg_duration_seconds from completed_at - created_at."""
        from sqlalchemy import update

        wf, version = await workflow_factory.create()

        now = datetime.now(UTC)
        # Two completed executions: 60s and 120s duration
        exec1 = await execution_factory.create(
            wf, version, status=ExecutionStatus.COMPLETED, completed_at=now + timedelta(seconds=60)
        )
        exec2 = await execution_factory.create(
            wf, version, status=ExecutionStatus.COMPLETED, completed_at=now + timedelta(seconds=120)
        )

        # Update created_at to `now` so durations are 60s and 120s
        await test_db_session.exec(update(Execution).where(Execution.id == exec1.id).values(created_at=now))  # type: ignore[arg-type]
        await test_db_session.exec(update(Execution).where(Execution.id == exec2.id).values(created_at=now))  # type: ignore[arg-type]
        await test_db_session.commit()

        result = await query_execution_counts(test_db_session)

        # avg of 60 and 120 = 90
        assert result.avg_duration_seconds == pytest.approx(90.0, abs=1.0)


class TestQueryModelUsageRealDB:
    """Integration tests for query_model_usage against real PostgreSQL."""

    async def test_empty_database(self, test_db_session: AsyncSession):
        result = await query_model_usage(test_db_session)
        assert result == []

    async def test_aggregates_by_model(
        self,
        test_db_session: AsyncSession,
        token_usage_factory: TokenUsageFactory,
    ):
        """Insert invocations with token records and verify aggregation by model."""
        now = datetime.now(UTC)

        await token_usage_factory.create_many("gpt-4", 1000, 500, 2, timestamp=now)
        await token_usage_factory.create("claude-3", 600, 300, timestamp=now)

        await test_db_session.commit()

        result = await query_model_usage(test_db_session)

        assert len(result) == 2
        usage_by_model = {m.model: m for m in result}
        assert usage_by_model["gpt-4"].total_prompt_tokens == 2000
        assert usage_by_model["gpt-4"].total_completion_tokens == 1000
        assert usage_by_model["gpt-4"].total_tokens == 3000
        assert usage_by_model["gpt-4"].invocation_count == 2
        assert usage_by_model["claude-3"].total_prompt_tokens == 600
        assert usage_by_model["claude-3"].total_completion_tokens == 300
        assert usage_by_model["claude-3"].total_tokens == 900
        assert usage_by_model["claude-3"].invocation_count == 1

    async def test_excludes_records_without_actual_tokens(
        self, test_db_session: AsyncSession, test_user: User, test_project_id
    ):
        """Records without post-LLM actual tokens (pre-LLM estimates only) are excluded."""
        now = datetime.now(UTC)

        inv = Invocation(
            prompt="in-flight prompt",
            session_id="test-session",
            created_by=test_user.id,
            project_id=test_project_id,
            model_name="gpt-4",
        )
        test_db_session.add(inv)
        await test_db_session.flush()
        # Pre-LLM record: only estimated tokens, no prompt_tokens
        test_db_session.add(
            TokenUsageRecord(
                user_id=test_user.id,
                token_count=500,
                estimated_input_tokens=500,
                invocation_id=inv.id,
                request_timestamp=now,
            )
        )
        await test_db_session.commit()

        result = await query_model_usage(test_db_session)

        assert result == []

    async def test_excludes_records_without_model_name(
        self, test_db_session: AsyncSession, test_user: User, test_project_id
    ):
        """Invocations without a model_name are excluded from aggregation."""
        now = datetime.now(UTC)

        inv = Invocation(
            prompt="no model prompt",
            session_id="test-session",
            created_by=test_user.id,
            project_id=test_project_id,
            model_name=None,
        )
        test_db_session.add(inv)
        await test_db_session.flush()
        test_db_session.add(
            TokenUsageRecord(
                user_id=test_user.id,
                token_count=1500,
                prompt_tokens=1000,
                completion_tokens=500,
                invocation_id=inv.id,
                request_timestamp=now,
            )
        )
        await test_db_session.commit()

        result = await query_model_usage(test_db_session)

        assert result == []


class TestQueryToolCountsRealDB:
    """Integration tests for query_tool_counts against real PostgreSQL."""

    async def test_empty_database(self, test_db_session: AsyncSession):
        result = await query_tool_counts(test_db_session)
        assert result.success_count == 0
        assert result.error_count == 0
        assert result.timeout_count == 0
        assert result.distinct_tools == 0
        assert result.total_executions == 0

    async def test_counts_from_usage_counters(
        self, test_db_session: AsyncSession, test_user: User, test_mcp_integration: Integration
    ):
        """Insert usage_counter rows and verify aggregation."""
        now = datetime.now(UTC)

        tool_1 = Tool(
            name="tool-1",
            integration_id=test_mcp_integration.id,
            namespaced_name="test::tool1",
            created_by=test_user.id,
        )
        tool_2 = Tool(
            name="tool-2",
            integration_id=test_mcp_integration.id,
            namespaced_name="test::tool2",
            created_by=test_user.id,
        )
        test_db_session.add_all([tool_1, tool_2])
        await test_db_session.flush()

        counters = [
            UsageCounter(
                counter_type=CounterType.TOOL,
                tool_id=tool_1.id,
                time_window="2026-04-09-14",
                window_duration=WindowDuration.HOUR,
                request_count=10,
                success_count=8,
                error_count=1,
                timeout_count=1,
                total_duration_ms=5000,
                window_start=now,
                window_end=now + timedelta(hours=1),
                created_by=test_user.id,
            ),
            UsageCounter(
                counter_type=CounterType.TOOL,
                tool_id=tool_2.id,
                time_window="2026-04-09-14",
                window_duration=WindowDuration.HOUR,
                request_count=5,
                success_count=4,
                error_count=1,
                timeout_count=0,
                total_duration_ms=2000,
                window_start=now,
                window_end=now + timedelta(hours=1),
                created_by=test_user.id,
            ),
        ]
        test_db_session.add_all(counters)
        await test_db_session.commit()

        result = await query_tool_counts(test_db_session)

        assert result.success_count == 12
        assert result.error_count == 2
        assert result.timeout_count == 1
        assert result.distinct_tools == 2
        assert result.total_executions == 15

    async def test_excludes_non_tool_counter_types(
        self, test_db_session: AsyncSession, test_user: User, test_mcp_integration: Integration
    ):
        """Only counter_type='tool' rows should be included."""
        now = datetime.now(UTC)

        # Provider counter — should be excluded
        test_db_session.add(
            UsageCounter(
                counter_type=CounterType.PROVIDER,
                integration_id=test_mcp_integration.id,
                time_window="2026-04-09-14",
                window_duration=WindowDuration.HOUR,
                request_count=100,
                success_count=90,
                error_count=10,
                timeout_count=0,
                total_duration_ms=50000,
                window_start=now,
                window_end=now + timedelta(hours=1),
                created_by=test_user.id,
            )
        )
        await test_db_session.commit()

        result = await query_tool_counts(test_db_session)

        assert result.total_executions == 0
        assert result.distinct_tools == 0


class TestQueryCredentialCountsRealDB:
    """Integration tests for query_credential_counts against real PostgreSQL."""

    async def test_counts_by_type(
        self,
        test_db_session: AsyncSession,
        credential_factory: CredentialFactory,
    ):
        """Insert credentials with different types and verify grouped counts."""
        suffix = uuid4().hex[:6]
        bearer_type = await credential_factory.create_type(f"Bearer-{suffix}")
        api_key_type = await credential_factory.create_type(f"LLM-Provider-{suffix}")
        project = await credential_factory.create_project(f"tel-test-{uuid4().hex[:8]}")

        await credential_factory.create_many(bearer_type, project, 3, prefix="bearer-cred")
        await credential_factory.create_many(api_key_type, project, 2, prefix="api-key-cred")
        await test_db_session.commit()

        result = await query_credential_counts(test_db_session)

        # There may be pre-seeded credentials; check that ours are counted correctly
        assert result.total >= 5
        assert result.type[f"Bearer-{suffix}"] == 3
        assert result.type[f"LLM-Provider-{suffix}"] == 2

    async def test_used_in_nodes_counts_distinct_credentials(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        credential_factory: CredentialFactory,
    ):
        """Credentials referenced in workflow nodes are counted as used_in_nodes."""
        cred_id_1 = str(uuid4())
        cred_id_2 = str(uuid4())
        project = await credential_factory.create_project(f"tel-test-{uuid4().hex[:8]}")

        # Create a workflow with two nodes referencing different credentials
        workflow = Workflow(
            name=f"wf-cred-test-{uuid4().hex[:8]}",
            description="test",
            current_version=1,
            is_enabled=False,
            project_id=project.id,
            created_by=test_user.id,
        )
        test_db_session.add(workflow)

        definition = {
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger_manual", "type": "manual_trigger", "parameters": {"inputs": {}}}],
            "nodes": [
                {"id": "node_1", "type": "agentic", "parameters": {"credential_id": cred_id_1}},
                {"id": "node_2", "type": "http_request", "parameters": {"credential_id": cred_id_2}},
                {"id": "node_3", "type": "script", "parameters": {"code": "print('hi')"}},
            ],
            "edges": [
                {"from": "trigger_manual", "to": "node_1"},
                {"from": "node_1", "to": "node_2"},
                {"from": "node_2", "to": "node_3"},
            ],
        }
        version = WorkflowVersion(
            workflow_id=workflow.id,
            version=1,
            schema_version="2.0.0",
            workflow_definition=definition,
            created_by=test_user.id,
        )
        test_db_session.add(version)
        await test_db_session.flush()
        workflow.published_version_id = version.id
        workflow.is_enabled = True
        publish_event = WorkflowPublishEvent(
            workflow_id=workflow.id,
            version_id=version.id,
            action=PublishAction.PUBLISHED,
            actor_id=test_user.id,
        )
        test_db_session.add(publish_event)
        await test_db_session.commit()

        result = await query_credential_counts(test_db_session)

        assert result.used_in_nodes == 2

    async def test_used_in_nodes_deduplicates_same_credential(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        credential_factory: CredentialFactory,
    ):
        """Same credential_id used in multiple nodes/workflows counts once."""
        cred_id = str(uuid4())
        project = await credential_factory.create_project(f"tel-test-{uuid4().hex[:8]}")

        # Two workflows, both referencing the same credential
        for i in range(2):
            workflow = Workflow(
                name=f"wf-dedup-{i}-{uuid4().hex[:8]}",
                description="test",
                current_version=1,
                is_enabled=False,
                project_id=project.id,
                created_by=test_user.id,
            )
            test_db_session.add(workflow)

            definition = {
                "schema_version": "2.0.0",
                "triggers": [{"id": "trigger_manual", "type": "manual_trigger", "parameters": {"inputs": {}}}],
                "nodes": [
                    {"id": "node_1", "type": "agentic", "parameters": {"credential_id": cred_id}},
                ],
                "edges": [{"from": "trigger_manual", "to": "node_1"}],
            }
            version = WorkflowVersion(
                workflow_id=workflow.id,
                version=1,
                schema_version="2.0.0",
                workflow_definition=definition,
                created_by=test_user.id,
            )
            test_db_session.add(version)
            await test_db_session.flush()
            workflow.published_version_id = version.id
            workflow.is_enabled = True
            publish_event = WorkflowPublishEvent(
                workflow_id=workflow.id,
                version_id=version.id,
                action=PublishAction.PUBLISHED,
                actor_id=test_user.id,
            )
            test_db_session.add(publish_event)

        await test_db_session.commit()

        result = await query_credential_counts(test_db_session)

        assert result.used_in_nodes == 1

    async def test_used_in_nodes_excludes_deleted_workflows(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        credential_factory: CredentialFactory,
    ):
        """Soft-deleted workflows should not contribute to used_in_nodes."""
        cred_id = str(uuid4())
        project = await credential_factory.create_project(f"tel-test-{uuid4().hex[:8]}")

        workflow = Workflow(
            name=f"wf-deleted-{uuid4().hex[:8]}",
            description="test",
            current_version=1,
            is_enabled=False,
            project_id=project.id,
            created_by=test_user.id,
        )
        test_db_session.add(workflow)

        definition = {
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger_manual", "type": "manual_trigger", "parameters": {"inputs": {}}}],
            "nodes": [
                {"id": "node_1", "type": "agentic", "parameters": {"credential_id": cred_id}},
            ],
            "edges": [{"from": "trigger_manual", "to": "node_1"}],
        }
        version = WorkflowVersion(
            workflow_id=workflow.id,
            version=1,
            schema_version="2.0.0",
            workflow_definition=definition,
            created_by=test_user.id,
        )
        test_db_session.add(version)
        await test_db_session.flush()
        workflow.published_version_id = version.id
        workflow.is_enabled = True
        publish_event = WorkflowPublishEvent(
            workflow_id=workflow.id,
            version_id=version.id,
            action=PublishAction.PUBLISHED,
            actor_id=test_user.id,
        )
        test_db_session.add(publish_event)
        workflow.soft_delete(test_user.id)
        await test_db_session.commit()

        result = await query_credential_counts(test_db_session)

        assert result.used_in_nodes == 0


class TestQueryExecutionCountsByTriggerTypeRealDB:
    """Integration tests for by_trigger_type in query_execution_counts."""

    async def test_empty_database(self, test_db_session: AsyncSession):
        result = await query_execution_counts(test_db_session)
        assert result.by_trigger_type == {}

    async def test_groups_by_trigger_type(
        self,
        test_db_session: AsyncSession,
        workflow_factory: WorkflowFactory,
        execution_factory: ExecutionFactory,
    ):
        wf, version = await workflow_factory.create()
        now = datetime.now(UTC)
        completed_at = now + timedelta(seconds=10)

        await execution_factory.create(
            wf, version, status=ExecutionStatus.COMPLETED, completed_at=completed_at, trigger_type="manual_trigger"
        )
        await execution_factory.create(
            wf, version, status=ExecutionStatus.COMPLETED, completed_at=completed_at, trigger_type="manual_trigger"
        )
        await execution_factory.create(
            wf, version, status=ExecutionStatus.COMPLETED, completed_at=completed_at, trigger_type="scheduled_trigger"
        )
        await test_db_session.commit()

        result = await query_execution_counts(test_db_session)

        assert result.by_trigger_type == {"manual_trigger": 2, "scheduled_trigger": 1}

    async def test_excludes_null_trigger_type(
        self,
        test_db_session: AsyncSession,
        workflow_factory: WorkflowFactory,
        execution_factory: ExecutionFactory,
    ):
        wf, version = await workflow_factory.create()
        now = datetime.now(UTC)
        completed_at = now + timedelta(seconds=10)

        await execution_factory.create(
            wf, version, status=ExecutionStatus.COMPLETED, completed_at=completed_at, trigger_type="manual_trigger"
        )
        await execution_factory.create(
            wf, version, status=ExecutionStatus.COMPLETED, completed_at=completed_at, trigger_type=None
        )
        await test_db_session.commit()

        result = await query_execution_counts(test_db_session)

        assert result.by_trigger_type == {"manual_trigger": 1}


class TestQueryExecutionCountsByInterfaceRealDB:
    """Integration tests for by_interface in query_execution_counts."""

    async def test_empty_database(self, test_db_session: AsyncSession):
        result = await query_execution_counts(test_db_session)
        assert result.by_interface == {}

    async def test_groups_by_interface(
        self,
        test_db_session: AsyncSession,
        workflow_factory: WorkflowFactory,
        execution_factory: ExecutionFactory,
    ):
        wf, version = await workflow_factory.create()
        now = datetime.now(UTC)
        completed_at = now + timedelta(seconds=10)

        await execution_factory.create(
            wf, version, status=ExecutionStatus.COMPLETED, completed_at=completed_at, interface="ui"
        )
        await execution_factory.create(
            wf, version, status=ExecutionStatus.COMPLETED, completed_at=completed_at, interface="api"
        )
        await execution_factory.create(
            wf, version, status=ExecutionStatus.COMPLETED, completed_at=completed_at, interface="api"
        )
        await test_db_session.commit()

        result = await query_execution_counts(test_db_session)

        assert result.by_interface == {"ui": 1, "api": 2}

    async def test_excludes_null_interface(
        self,
        test_db_session: AsyncSession,
        workflow_factory: WorkflowFactory,
        execution_factory: ExecutionFactory,
    ):
        wf, version = await workflow_factory.create()

        await execution_factory.create(wf, version, interface="ui")
        await execution_factory.create(wf, version, interface=None)
        await test_db_session.commit()

        result = await query_execution_counts(test_db_session)

        assert result.by_interface == {"ui": 1}
