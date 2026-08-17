"""Integration test for wait node workflow dispatch and orchestration.

Tests the workflow-level handling of wait nodes using Temporal's time-skipping
test environment. Uses a test-friendly wait activity that returns normally
(instead of raise_complete_async) because the time-skipping test server does
not reliably support async activity completion RPCs.

The async completion pattern (raise_complete_async → external complete) is
validated in unit tests: test_wait_activity.py.
"""

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

import syntara.settings.cache.settings_cache as _settings_mod
from syntara.workflows.workflow_engine.activities.manual_trigger import manual_trigger
from syntara.workflows.workflow_engine.activities.runtime_settings_activity import fetch_workflow_runtime_settings
from syntara.workflows.workflow_engine.activities.wait_activity import complete_wait
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName
from syntara.workflows.workflow_engine.services.activity_sync_registry import (
    get_activity_sync_service,
    set_activity_sync_service,
)
from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService
from tests.fixtures.settings import FakeSettingsCache


@activity.defn(name=ActivityName.WAIT)
async def _test_wait_activity(
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
) -> dict[str, Any]:
    """Test-friendly wait activity that returns normally.

    Validates config the same way the real activity does, but returns a result
    instead of calling raise_complete_async(). This avoids the async activity
    completion RPC which is not supported in the time-skipping test environment.
    """
    total_seconds = input_config.get("duration", 0)
    if isinstance(total_seconds, bool) or not isinstance(total_seconds, int) or total_seconds <= 0:
        return {"output": {"status": "failed", "error": "Wait duration must be a positive integer (seconds)"}}

    return {"output": {"status": "completed", "total_seconds": total_seconds}}


def _create_wait_workflow_yaml(wait_seconds: int = 5) -> dict[str, Any]:
    """Create a minimal workflow definition with a wait node."""
    workflow_yaml = f"""
schema_version: "2.0.0"
name: wait-integration-test
description: Integration test for wait node
triggers:
- id: trigger_manual
  type: manual_trigger
nodes:
- id: wait_node
  type: wait
  parameters:
    duration: {wait_seconds}
edges:
- from: trigger_manual
  to: wait_node
"""
    result: dict[str, Any] = yaml.safe_load(workflow_yaml)
    return result


@pytest.mark.integration
@pytest.mark.asyncio
class TestWaitNodeIntegration:
    """End-to-end integration tests for wait node workflow dispatch."""

    async def test_wait_node_completes_after_timer(self, temporal_env: WorkflowEnvironment) -> None:
        """Workflow dispatches to wait node, sleeps, then completes."""
        task_queue = "wait-integration-queue"

        mock_sync_service = MagicMock()
        mock_sync_service.temporal_client = temporal_env.client
        original_service = get_activity_sync_service()
        set_activity_sync_service(mock_sync_service)

        original_settings = _settings_mod._runtime_settings
        _settings_mod._runtime_settings = FakeSettingsCache()  # type: ignore[assignment]

        try:
            async with Worker(
                temporal_env.client,
                task_queue=task_queue,
                workflows=[OrchestratorWorkflow],
                activities=[manual_trigger, _test_wait_activity, complete_wait, fetch_workflow_runtime_settings],
            ):
                execution_service = TemporalExecutionService(
                    temporal_client=temporal_env.client,
                    task_queue=task_queue,
                )

                workflow_def = _create_wait_workflow_yaml(wait_seconds=2)

                result = await execution_service.start_workflow(
                    workflow_def=workflow_def,
                    workflow_name="wait-integration-test",
                    trigger_node_id="trigger_manual",
                )

                handle = execution_service.temporal_client.get_workflow_handle(
                    result.temporal_workflow_id, run_id=result.temporal_run_id
                )
                workflow_result = await asyncio.wait_for(handle.result(), timeout=30)

                assert workflow_result["status"] == "completed"
        finally:
            set_activity_sync_service(original_service)
            _settings_mod._runtime_settings = original_settings

    async def test_wait_node_invalid_config_fails(self, temporal_env: WorkflowEnvironment) -> None:
        """Wait node with zero duration completes workflow (node fails gracefully)."""
        task_queue = "wait-invalid-queue"

        original_settings = _settings_mod._runtime_settings
        _settings_mod._runtime_settings = FakeSettingsCache()  # type: ignore[assignment]

        try:
            async with Worker(
                temporal_env.client,
                task_queue=task_queue,
                workflows=[OrchestratorWorkflow],
                activities=[manual_trigger, _test_wait_activity, complete_wait, fetch_workflow_runtime_settings],
            ):
                execution_service = TemporalExecutionService(
                    temporal_client=temporal_env.client,
                    task_queue=task_queue,
                )

                workflow_def = _create_wait_workflow_yaml(wait_seconds=0)

                result = await execution_service.start_workflow(
                    workflow_def=workflow_def,
                    workflow_name="wait-invalid-test",
                    trigger_node_id="trigger_manual",
                )

                handle = execution_service.temporal_client.get_workflow_handle(
                    result.temporal_workflow_id, run_id=result.temporal_run_id
                )
                workflow_result = await asyncio.wait_for(handle.result(), timeout=30)

                assert workflow_result["status"] == "failed"
        finally:
            _settings_mod._runtime_settings = original_settings

    async def test_wait_node_short_duration(self, temporal_env: WorkflowEnvironment) -> None:
        """Wait node with 1 second duration completes quickly with time skipping."""
        task_queue = "wait-short-queue"

        mock_sync_service = MagicMock()
        mock_sync_service.temporal_client = temporal_env.client
        original_service = get_activity_sync_service()
        set_activity_sync_service(mock_sync_service)

        original_settings = _settings_mod._runtime_settings
        _settings_mod._runtime_settings = FakeSettingsCache()  # type: ignore[assignment]

        try:
            async with Worker(
                temporal_env.client,
                task_queue=task_queue,
                workflows=[OrchestratorWorkflow],
                activities=[manual_trigger, _test_wait_activity, complete_wait, fetch_workflow_runtime_settings],
            ):
                execution_service = TemporalExecutionService(
                    temporal_client=temporal_env.client,
                    task_queue=task_queue,
                )

                workflow_def = _create_wait_workflow_yaml(wait_seconds=1)

                result = await execution_service.start_workflow(
                    workflow_def=workflow_def,
                    workflow_name="wait-short-test",
                    trigger_node_id="trigger_manual",
                )

                handle = execution_service.temporal_client.get_workflow_handle(
                    result.temporal_workflow_id, run_id=result.temporal_run_id
                )
                workflow_result = await asyncio.wait_for(handle.result(), timeout=30)

                assert workflow_result["status"] == "completed"
        finally:
            set_activity_sync_service(original_service)
            _settings_mod._runtime_settings = original_settings
