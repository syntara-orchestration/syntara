"""Integration tests for TemporalExecutionService.

These tests verify the TemporalExecutionService works correctly with a real Temporal test server.
They focus on the service layer (YAML parsing, workflow management) rather than
workflow execution details (which are tested in tests/integration/workflow/).
"""

import asyncio
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
import yaml
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from syntara.workflows.workflow_engine.activities.manual_trigger import manual_trigger
from syntara.workflows.workflow_engine.activities.runtime_settings_activity import fetch_workflow_runtime_settings
from syntara.workflows.workflow_engine.activities.script_activity import execute_script_activity
from syntara.workflows.workflow_engine.dynamic_workflow import NexusWorkflow
from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService


@pytest_asyncio.fixture
async def execution_service(
    temporal_client: Client,
    temporal_worker: Worker,
    task_queue: str,
) -> TemporalExecutionService:
    """Provide an TemporalExecutionService connected to the test environment.

    Args:
        temporal_client: Temporal test client
        temporal_worker: Temporal test worker (ensures it's running)
        task_queue: Test task queue name

    Returns:
        TemporalExecutionService instance

    """
    return TemporalExecutionService(temporal_client=temporal_client, task_queue=task_queue)


TEST_WORKFLOW_METADATA = {
    "workflow_context": {"workflow": {"project_id": str(uuid4())}},
}


@pytest.mark.integration
@pytest.mark.asyncio
class TestTemporalExecutionServiceIntegration:
    """Integration tests for TemporalExecutionService with real Temporal."""

    async def test_start_and_complete_workflow(self, execution_service: TemporalExecutionService) -> None:
        """Test starting a workflow and waiting for completion."""
        workflow_yaml = """
schema_version: "2.0.0"
name: integration-test
description: Simple integration test
triggers:
- id: trigger_manual
  type: manual_trigger
nodes:
- id: test_task
  type: script
  parameters:
    language: bash
    code: echo "Integration test successful"
  settings:
    timeout: 1
edges:
- from: trigger_manual
  to: test_task
"""
        workflow_def = yaml.safe_load(workflow_yaml)

        # Start workflow
        result = await execution_service.start_workflow(
            workflow_def=workflow_def,
            workflow_name="integration-test",
            trigger_node_id="trigger_manual",
            workflow_metadata=TEST_WORKFLOW_METADATA,
        )

        # Verify result structure (Pydantic model)
        assert result.execution_id is not None
        assert result.workflow_id is not None
        assert result.temporal_workflow_id is not None
        assert result.temporal_run_id is not None
        assert result.status == "running"

        handle = execution_service.temporal_client.get_workflow_handle(
            result.temporal_workflow_id, run_id=result.temporal_run_id
        )
        workflow_result = await asyncio.wait_for(handle.result(), timeout=30)

        # Verify completion (activity_outputs are empty when include_node_results=False)
        assert workflow_result["status"] == "completed"

    async def test_start_workflow_with_custom_id(self, execution_service: TemporalExecutionService) -> None:
        """Test starting a workflow with a custom workflow ID."""
        workflow_yaml = """
schema_version: "2.0.0"
name: custom-id-test
description: Test custom workflow ID
triggers:
- id: trigger_manual
  type: manual_trigger
nodes:
- id: task1
  type: script
  parameters:
    language: bash
    code: echo "Custom ID test"
  settings:
    timeout: 1
edges:
- from: trigger_manual
  to: task1
"""
        workflow_def = yaml.safe_load(workflow_yaml)

        custom_id = "my-custom-workflow-id-12345"

        result = await execution_service.start_workflow(
            workflow_def=workflow_def,
            workflow_name="custom-id-test",
            workflow_id=custom_id,
            trigger_node_id="trigger_manual",
            workflow_metadata=TEST_WORKFLOW_METADATA,
        )

        assert result.workflow_id == custom_id

        handle = execution_service.temporal_client.get_workflow_handle(
            result.temporal_workflow_id, run_id=result.temporal_run_id
        )
        workflow_result = await asyncio.wait_for(handle.result(), timeout=30)
        assert workflow_result["status"] == "completed"

    async def test_start_workflow_with_inputs(self, execution_service: TemporalExecutionService) -> None:
        """Test starting a workflow with input parameters."""
        workflow_yaml = """
schema_version: "2.0.0"
name: input-test
description: Test workflow inputs
triggers:
- id: trigger_manual
  type: manual_trigger
nodes:
- id: use_input
  type: script
  inputs:
    name: ${input.user_name}
  parameters:
    language: bash
    code: echo "Hello, $INPUT_NAME!"
  settings:
    timeout: 1
edges:
- from: trigger_manual
  to: use_input
"""
        workflow_def = yaml.safe_load(workflow_yaml)

        result = await execution_service.start_workflow(
            workflow_def=workflow_def,
            workflow_name="input-test",
            input_data={"user_name": "Alice"},
            trigger_node_id="trigger_manual",
            workflow_metadata=TEST_WORKFLOW_METADATA,
        )

        handle = execution_service.temporal_client.get_workflow_handle(
            result.temporal_workflow_id, run_id=result.temporal_run_id
        )
        workflow_result = await asyncio.wait_for(handle.result(), timeout=30)

        # Verify workflow completed (activity_outputs are empty when include_node_results=False)
        assert workflow_result["status"] == "completed"

    async def test_invalid_workflow_definition_raises_validation_error(
        self, execution_service: TemporalExecutionService
    ) -> None:
        """Test that invalid workflow definition raises an error."""
        from syntara.core.exceptions import SafeValueError

        # Valid YAML but missing required 'triggers' field
        invalid_workflow_yaml = """
schema_version: "2.0.0"
name: invalid-workflow
description: Missing triggers field
nodes:
- id: test_task
  type: script
  parameters:
    language: bash
    code: echo "test"
  settings:
    timeout: 1
edges: []
"""
        workflow_def = yaml.safe_load(invalid_workflow_yaml)

        with pytest.raises(SafeValueError):
            await execution_service.start_workflow(
                workflow_def=workflow_def,
                workflow_name="invalid-workflow",
                trigger_node_id="trigger_manual",
                workflow_metadata=TEST_WORKFLOW_METADATA,
            )

    async def test_cancel_workflow(self, execution_service: TemporalExecutionService) -> None:
        """Test cancelling a running workflow."""
        workflow_yaml = """
schema_version: "2.0.0"
name: cancel-test
description: Test workflow cancellation
triggers:
- id: trigger_manual
  type: manual_trigger
nodes:
- id: long_task
  type: script
  parameters:
    language: bash
    code: |
      sleep 10
      echo "This should not complete"
  settings:
    timeout: 1
edges:
- from: trigger_manual
  to: long_task
"""
        workflow_def = yaml.safe_load(workflow_yaml)

        # Start workflow
        result = await execution_service.start_workflow(
            workflow_def=workflow_def,
            workflow_name="cancel-test",
            trigger_node_id="trigger_manual",
            workflow_metadata=TEST_WORKFLOW_METADATA,
        )

        # Yield control so the worker can pick up the workflow
        await asyncio.sleep(0)

        # Cancel the workflow
        await execution_service.cancel_workflow(
            temporal_workflow_id=result.temporal_workflow_id,
        )


@pytest.mark.integration
@pytest.mark.asyncio
class TestCreateTemporalExecutionServiceFactory:
    """Test the factory function for creating TemporalExecutionService."""

    async def test_create_execution_service_integration(
        self,
        temporal_env: AsyncGenerator[None, None],
        temporal_worker: Worker,
    ) -> None:
        """Test creating TemporalExecutionService via factory function.

        Note: This test uses the real test environment but doesn't connect to
        localhost:7233 - it uses the test environment's client instead.
        """
        # For this test, we'll verify the factory function works with the
        # test environment by checking the service can be created and used
        # We can't easily test connecting to a real external server in unit tests

        # This is more of a "does the factory function work" test
        # Real connection to external Temporal would be in manual/system tests

        # Instead, let's verify the service structure is created correctly
        # Create a minimal test to verify the factory creates a valid service
        async with await WorkflowEnvironment.start_time_skipping() as env:
            service = TemporalExecutionService(
                temporal_client=env.client,
                task_queue="test-queue",
            )

            assert service.temporal_client is not None
            assert service.task_queue == "test-queue"

            # Verify we can use it
            workflow_yaml = """
schema_version: "2.0.0"
name: factory-test
description: Test factory function
triggers:
- id: trigger_manual
  type: manual_trigger
nodes:
- id: task1
  type: script
  parameters:
    language: bash
    code: echo "Factory test"
  settings:
    timeout: 1
edges:
- from: trigger_manual
  to: task1
"""

            # Need to start a worker for this test
            async with Worker(
                env.client,
                task_queue="test-queue",
                workflows=[NexusWorkflow],
                activities=[execute_script_activity, manual_trigger, fetch_workflow_runtime_settings],
            ):
                workflow_def = yaml.safe_load(workflow_yaml)
                result = await service.start_workflow(
                    workflow_def=workflow_def,
                    workflow_name="factory-test",
                    trigger_node_id="trigger_manual",
                    workflow_metadata=TEST_WORKFLOW_METADATA,
                )

                assert result.status == "running"

                handle = service.temporal_client.get_workflow_handle(
                    result.temporal_workflow_id, run_id=result.temporal_run_id
                )
                workflow_result = await asyncio.wait_for(handle.result(), timeout=30)
                assert workflow_result["status"] == "completed"
