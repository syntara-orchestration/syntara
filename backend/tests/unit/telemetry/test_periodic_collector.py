"""Unit tests for PeriodicCollector background task.

Since PeriodicCollector now wraps PeriodicWorker, these tests focus on
the integration between the two and verify that:
1. Lifecycle methods delegate correctly to the worker
2. Cleanup callback (registry.flush) is invoked on stop
3. The collect_and_send callback is wired correctly

For error resilience and coordination tests, see tests/unit/core/workers/test_periodic_worker.py.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.telemetry.api_usage_accumulator import AccumulatorSnapshot
from syntara.telemetry.events.integration_health import (
    CredentialHealth,
    CredentialInfo,
    IdentityProviderHealth,
    IdentityProviderInfo,
    IntegrationHealth,
    IntegrationInfo,
)
from syntara.telemetry.periodic_collector import PeriodicCollector, _collect_and_send


def _mock_session_factory() -> MagicMock:
    """Create a mock async_sessionmaker that returns an async-context session."""
    session = AsyncMock()
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory


@pytest.fixture
def mock_registry() -> MagicMock:
    """Create a mock TelemetryClientRegistry."""
    registry = MagicMock()
    registry.is_initialized.return_value = True
    registry.entitlement_id = "test-entitlement-123"
    registry.send_event = MagicMock()
    registry.flush = MagicMock()
    return registry


class TestPeriodicCollectorLifecycle:
    """Tests for start/stop lifecycle delegation to PeriodicWorker."""

    async def test_start_creates_background_task(self, mock_registry: MagicMock) -> None:
        """start() creates an asyncio task via the underlying worker."""
        collector = PeriodicCollector(
            registry=mock_registry,
            session_factory=_mock_session_factory(),
        )

        collector.start()

        # Verify the worker has a running task
        assert collector._worker._task is not None
        assert not collector._worker._task.done()

        # Cleanup
        await collector.stop()

    async def test_stop_cancels_task_and_flushes(self, mock_registry: MagicMock) -> None:
        """stop() cancels the task and calls registry.flush() via cleanup callback."""
        collector = PeriodicCollector(
            registry=mock_registry,
            session_factory=_mock_session_factory(),
        )
        collector.start()

        await collector.stop()

        # Task should be stopped
        assert collector._worker._task is None
        # Cleanup callback should have called flush
        mock_registry.flush.assert_called_once()

    async def test_stop_noop_when_not_started(self, mock_registry: MagicMock) -> None:
        """Calling stop() without start() should not raise or flush."""
        collector = PeriodicCollector(
            registry=mock_registry,
            session_factory=_mock_session_factory(),
        )

        await collector.stop()  # Should not raise

        mock_registry.flush.assert_not_called()

    async def test_idempotent_start(self, mock_registry: MagicMock) -> None:
        """Calling start() multiple times creates only one task (via worker)."""
        collector = PeriodicCollector(
            registry=mock_registry,
            session_factory=_mock_session_factory(),
        )

        collector.start()
        first_task = collector._worker._task
        collector.start()
        second_task = collector._worker._task

        assert first_task is second_task

        await collector.stop()


class TestCollectAndSendFunction:
    """Tests for the _collect_and_send module-level function."""

    async def test_collect_and_send_queries_and_sends_event(self, mock_registry: MagicMock) -> None:
        """_collect_and_send queries the database and sends both events."""
        session_factory = _mock_session_factory()

        mock_accumulator = MagicMock()
        mock_accumulator.drain.return_value = AccumulatorSnapshot(
            caller_ids=frozenset({"hash-1", "hash-2"}),
            callers_by_type={"user": 1, "service_account": 1},
            callers_by_interface={"api": 2},
            feature_usage={("/api/v1/workflows", "GET", "api"): 5},
        )

        with (
            patch(
                "syntara.telemetry.periodic_collector.query_workflow_counts",
                new_callable=AsyncMock,
            ) as mock_wf,
            patch(
                "syntara.telemetry.periodic_collector.query_execution_counts",
                new_callable=AsyncMock,
            ) as mock_exec,
            patch(
                "syntara.telemetry.periodic_collector.query_credential_counts",
                new_callable=AsyncMock,
            ) as mock_creds,
            patch(
                "syntara.telemetry.periodic_collector.get_enabled_feature_flags",
            ) as mock_flags,
            patch(
                "syntara.telemetry.periodic_collector.query_model_usage",
                new_callable=AsyncMock,
            ) as mock_model_usage,
            patch(
                "syntara.telemetry.periodic_collector.query_tool_counts",
                new_callable=AsyncMock,
            ) as mock_tool_counts,
            patch(
                "syntara.telemetry.periodic_collector.query_integration_health",
                new_callable=AsyncMock,
            ) as mock_tp_health,
            patch(
                "syntara.telemetry.periodic_collector.query_identity_provider_health",
                new_callable=AsyncMock,
            ) as mock_idp_health,
            patch(
                "syntara.telemetry.periodic_collector.query_credential_health",
                new_callable=AsyncMock,
            ) as mock_cred_health,
            patch(
                "syntara.telemetry.periodic_collector.get_accumulator",
                return_value=mock_accumulator,
            ),
        ):
            # Set up return values
            mock_wf.return_value = MagicMock(total=10, enabled=8, disabled=2)
            mock_exec.return_value = MagicMock(
                total=100,
                completed=80,
                failed=10,
                running=5,
                pending=5,
                by_trigger_type={"manual_trigger": 60, "scheduled_trigger": 40},
                by_interface={"ui": 70, "api": 30},
            )
            mock_creds.return_value = MagicMock(total=5, type={"Bearer": 3, "LLM Provider": 2})
            mock_flags.return_value = ["feature_a"]
            mock_model_usage.return_value = []
            mock_tool_counts.return_value = MagicMock(success_count=0, error_count=0, timeout_count=0, distinct_tools=0)
            mock_tp_health.return_value = IntegrationHealth(
                items={"mcp": IntegrationInfo(enabled=1, disabled=1)},
                total=2,
            )
            mock_idp_health.return_value = IdentityProviderHealth(
                items={"oidc": IdentityProviderInfo(enabled=1, disabled=0)},
                total=1,
            )
            mock_cred_health.return_value = CredentialHealth(
                items={"HTTP Bearer Token": CredentialInfo(enabled=1, disabled=0)},
                total=1,
                enabled=1,
                disabled=0,
            )

            await _collect_and_send(session_factory, mock_registry)

            # Verify all queries were called
            mock_wf.assert_called_once()
            mock_exec.assert_called_once()
            mock_creds.assert_called_once()
            mock_flags.assert_called_once()
            mock_model_usage.assert_called_once()
            mock_tool_counts.assert_called_once()
            mock_tp_health.assert_called_once()
            mock_idp_health.assert_called_once()
            mock_cred_health.assert_called_once()

            # Verify accumulator was drained
            mock_accumulator.drain.assert_called_once()

            # Verify both events were sent (system analytics + integration health)
            assert mock_registry.send_event.call_count == 2

            # Verify unique_callers and feature_usage in the system analytics event
            system_event = mock_registry.send_event.call_args_list[0][0][0]
            assert system_event.unique_callers.total == 2
            assert system_event.unique_callers.by_principal_type == {"user": 1, "service_account": 1}
            assert system_event.unique_callers.by_interface == {"api": 2}
            assert len(system_event.feature_usage) == 1
            assert system_event.feature_usage[0].endpoint_group == "/api/v1/workflows"
            assert system_event.feature_usage[0].request_count == 5

    async def test_collect_and_send_propagates_exceptions(self, mock_registry: MagicMock) -> None:
        """_collect_and_send propagates exceptions (error handling is in worker)."""
        session_factory = _mock_session_factory()

        with (
            patch(
                "syntara.telemetry.periodic_collector.query_workflow_counts",
                new_callable=AsyncMock,
                side_effect=RuntimeError("db error"),
            ),
            pytest.raises(RuntimeError, match="db error"),
        ):
            await _collect_and_send(session_factory, mock_registry)


class TestPeriodicCollectorIntegration:
    """Integration tests for callback wiring with PeriodicWorker."""

    async def test_worker_calls_collect_and_send(self, mock_registry: MagicMock) -> None:
        """Verify the worker callback invokes _collect_and_send correctly."""
        session_factory = _mock_session_factory()
        collector = PeriodicCollector(
            registry=mock_registry,
            session_factory=session_factory,
        )

        # Patch at module level to intercept the call
        with patch(
            "syntara.telemetry.periodic_collector._collect_and_send",
            new_callable=AsyncMock,
        ) as mock_collect:
            # Manually invoke the callback that was passed to the worker
            await collector._worker._callback(session_factory)

            mock_collect.assert_called_once_with(session_factory, mock_registry)
