r"""CLI tool for executing V2 workflows from JSON files.

## Purpose

This is a **development and debugging utility** for manual verification of V2 workflow execution.
It is NOT intended to be used in production or imported by the application code.

This script serves as:
- A manual testing tool for developers to validate V2 workflow JSON files
- A debugging utility to inspect workflow execution locally
- A quick way to verify Temporal integration without running the full API

## Test Coverage

This file is intentionally excluded from automated test coverage because:
1. It's a manual utility, not application code
2. Testing CLI argument parsing provides minimal value
3. Manual verification is more appropriate for CLI tools

## Usage

    # Run V2 workflow
    python tools/workflow_cli.py run <workflow.json> --trigger-id trigger1
    python tools/workflow_cli.py run workflow.json --trigger-id manual_trigger --inputs '{"key": "value"}'
"""
# pragma: no cover - Manual verification utility, excluded from coverage

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from temporalio.client import Client
from temporalio.worker import Worker

from syntara.core.config.base import get_settings
from syntara.core.logging import configure_structlog
from syntara.workflows.workflow_engine.activities.condition import condition
from syntara.workflows.workflow_engine.activities.converge import converge
from syntara.workflows.workflow_engine.activities.http_request_activity import execute_http_request_activity
from syntara.workflows.workflow_engine.activities.loop import loop
from syntara.workflows.workflow_engine.activities.manual_trigger import manual_trigger
from syntara.workflows.workflow_engine.activities.script_activity import execute_script_activity
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.models import WorkflowResultResponse

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def run_workflow(
    workflow_file: Path,
    trigger_id: str,
    inputs: dict[str, Any] | None = None,
    temporal_address: str = "localhost:7233",
) -> WorkflowResultResponse:
    """Run a V2 workflow from a JSON file.

    Args:
        workflow_file: Path to V2 workflow JSON file
        trigger_id: ID of the trigger node to execute
        inputs: Input parameters for the trigger
        temporal_address: Temporal server address

    Returns:
        WorkflowResultResponse containing workflow execution result

    Raises:
        FileNotFoundError: If workflow file doesn't exist
        Exception: If workflow execution fails

    """
    # Read workflow file
    if not workflow_file.exists():
        msg = f"Workflow file not found: {workflow_file}"
        raise FileNotFoundError(msg)

    workflow_name = workflow_file.stem

    # Load workflow definition
    workflow_content = workflow_file.read_text()
    logger.info("Loading V2 workflow from: %s", workflow_file)
    try:
        workflow_def = json.loads(workflow_content)
    except json.JSONDecodeError as e:
        msg = f"Invalid JSON in workflow file: {e}"
        raise ValueError(msg) from e

    # Validate it's a V2 workflow
    if "triggers" not in workflow_def or "nodes" not in workflow_def or "edges" not in workflow_def:
        msg = "Invalid V2 workflow: missing 'triggers', 'nodes', or 'edges'"
        raise ValueError(msg)

    logger.info("Connecting to Temporal at: %s", temporal_address)
    client = await Client.connect(temporal_address)
    logger.info("✓ Connected to Temporal server")

    # Generate unique IDs
    execution_id = str(uuid.uuid4())
    task_queue = f"cli-workflow-{uuid.uuid4()}"
    workflow_id = f"cli-{workflow_name}-{datetime.now(tz=UTC).strftime('%Y%m%d-%H%M%S')}"

    logger.info("Execution ID: %s", execution_id)
    logger.info("Task Queue: %s", task_queue)
    logger.info("Workflow ID: %s", workflow_id)

    # Start embedded worker
    logger.info("Starting embedded worker...")
    async with Worker(
        client,
        task_queue=task_queue,
        workflows=[OrchestratorWorkflow],
        activities=[
            # Workflow activities (no internal activities - CLI has no database)
            manual_trigger,
            execute_http_request_activity,
            converge,
            execute_script_activity,
            condition,
            loop,
        ],
    ):
        logger.info("✓ Worker started")

        # Start workflow
        logger.info("\n=== Starting Workflow: %s ===", workflow_name)
        logger.info("Trigger ID: %s", trigger_id)
        if inputs:
            logger.info("Inputs: %s", json.dumps(inputs, indent=2))

        start_time = datetime.now(tz=UTC)

        result_dict = await client.execute_workflow(
            OrchestratorWorkflow.run,
            args=[workflow_def, execution_id, trigger_id, inputs or {}, True],  # include_node_results=True for CLI
            id=workflow_id,
            task_queue=task_queue,
        )

        end_time = datetime.now(tz=UTC)
        duration = (end_time - start_time).total_seconds()

        # Convert to WorkflowResultResponse
        workflow_result = WorkflowResultResponse(**result_dict)

        logger.info("\n✓ Workflow completed in %.2f seconds!", duration)
        logger.info("  Status: %s", workflow_result.status)
        logger.info("  Activities completed: %s", len(workflow_result.completed_activities))

        # Display full result as formatted JSON
        logger.info("\n=== Workflow Result ===")
        logger.info(json.dumps(workflow_result.model_dump(), indent=2))

        logger.info("\n=== Workflow Complete ===")

        return workflow_result


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Execute V2 workflows from JSON files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run a V2 workflow
  python tools/workflow_cli.py run workflow.json --trigger-id trigger1

  # Run with inputs
  python tools/workflow_cli.py run workflow.json --trigger-id manual_trigger \\
    --inputs '{"url": "https://example.com"}'

  # Use custom Temporal server
  python tools/workflow_cli.py run workflow.json --trigger-id trigger1 \\
    --temporal-address localhost:7233
        """,
    )

    parser.add_argument("command", choices=["run"], help="Command to execute")

    parser.add_argument("workflow_file", type=Path, help="Path to V2 workflow JSON file")

    parser.add_argument("--trigger-id", "-t", required=True, help="ID of the trigger node to execute")

    parser.add_argument("--inputs", "-i", type=str, help="Trigger input parameters as JSON string")

    parser.add_argument(
        "--temporal-address", default="localhost:7233", help="Temporal server address (default: localhost:7233)"
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        os.environ["APP_FALLBACK_LOG_LEVEL"] = "DEBUG"
        get_settings.cache_clear()

    # Configure logging (will read APP_FALLBACK_LOG_LEVEL if set)
    configure_structlog()

    # Get logger after configuration
    logger = structlog.stdlib.get_logger(__name__)

    # Parse inputs
    inputs = None
    if args.inputs:
        try:
            inputs = json.loads(args.inputs)
        except json.JSONDecodeError:
            logger.exception("Invalid JSON in --inputs")
            sys.exit(1)

    # Run workflow
    try:
        asyncio.run(
            run_workflow(
                workflow_file=args.workflow_file,
                trigger_id=args.trigger_id,
                inputs=inputs,
                temporal_address=args.temporal_address,
            )
        )
    except KeyboardInterrupt:
        logger.info("\nWorkflow execution interrupted")
        sys.exit(1)
    except Exception:
        logger.exception("Workflow execution failed", exc_info=args.verbose)
        sys.exit(1)


if __name__ == "__main__":
    main()
