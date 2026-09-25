"""Run the OpenShift HTTP→Python workflow through real Temporal and EP workers."""
# ruff: noqa: INP001, T201

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from pathlib import Path

from temporalio.client import Client
from temporalio.worker import Worker

from syntara.core.database.session import AsyncSessionLocal
from syntara.core.tls.temporal import build_temporal_tls_config
from syntara.settings.cache.settings_cache import SettingsCache, set_runtime_settings
from syntara.workflows.workflow_engine.activities.condition import condition
from syntara.workflows.workflow_engine.activities.converge import converge
from syntara.workflows.workflow_engine.activities.ep.ep_dispatch_activity import execute_script_activity
from syntara.workflows.workflow_engine.activities.http_request_activity import execute_http_request_activity
from syntara.workflows.workflow_engine.activities.loop import loop
from syntara.workflows.workflow_engine.activities.manual_trigger import manual_trigger
from syntara.workflows.workflow_engine.activities.runtime_settings_activity import fetch_workflow_runtime_settings
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow


async def verify(path: Path, temporal_address: str) -> None:
    """Execute both node types and assert dynamic outputs through Temporal."""
    definition = json.loads(path.read_text())
    set_runtime_settings(SettingsCache(session_factory=AsyncSessionLocal))
    client = await Client.connect(temporal_address, tls=build_temporal_tls_config())
    queue = f"ep-integration-check-{uuid.uuid4()}"
    workflow_id = f"ep-integration-check-{uuid.uuid4()}"
    async with Worker(
        client,
        task_queue=queue,
        workflows=[OrchestratorWorkflow],
        activities=[
            manual_trigger,
            execute_http_request_activity,
            execute_script_activity,
            fetch_workflow_runtime_settings,
            converge,
            condition,
            loop,
        ],
    ):
        result = await client.execute_workflow(
            OrchestratorWorkflow.run,
            args=[definition, str(uuid.uuid4()), "trigger_manual", {}, True],
            id=workflow_id,
            task_queue=queue,
        )
    outputs = result.get("activity_outputs") or {}
    print(
        json.dumps(
            {
                "workflow_id": workflow_id,
                "status": result.get("status"),
                "completed_activities": result.get("completed_activities"),
                "http_status_code": (outputs.get("fetch_zen") or {}).get("status_code"),
                "script_stdout_json": (outputs.get("run_python") or {}).get("stdout_json"),
            },
            default=str,
            indent=2,
        )
    )
    if result.get("status") != "completed":
        raise RuntimeError("Workflow did not complete successfully")
    completed = set(result.get("completed_activities") or [])
    if "fetch_zen" not in completed:
        raise RuntimeError("HTTP node result is missing")
    if "run_python" not in completed:
        raise RuntimeError("Python node result is missing")
    if (outputs.get("fetch_zen") or {}).get("status_code") != 200:
        raise RuntimeError("HTTP node did not return status 200")
    if (outputs.get("run_python") or {}).get("stdout_json") != {"value": 18}:
        raise RuntimeError("Python node did not return its computed JSON result")


def main() -> None:
    """Parse paths and run a dedicated Temporal test worker."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workflow_file", type=Path)
    parser.add_argument("--temporal-address", default="temporal:7233")
    args = parser.parse_args()
    asyncio.run(verify(args.workflow_file, args.temporal_address))


if __name__ == "__main__":
    main()
