"""E2E tests: runtime settings affect workflow execution behavior.

Verifies that changing a setting via the Settings API changes actual
workflow behavior without restart. Requires the full stack (API,
Temporal worker, containers).

Run with:
    APP_BASE_URL=http://localhost:8000 make test-e2e
"""

import os
import time
from typing import Any
from uuid import UUID

import pytest
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models import (
    ExecutionCreate,
    ExecutionRead,
    SettingUpdate,
    WorkflowCreate,
    WorkflowUpdate,
)
from syntara_api_client.models.execution_status import ExecutionStatus
from syntara_api_client.models.workflow_definition import WorkflowDefinition

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)

POLL_INTERVAL = 1
POLL_TIMEOUT = 30

_TERMINAL = {ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED}


def _poll(api: SyntaraApiRegistry, exec_id: str, timeout: int = POLL_TIMEOUT) -> ExecutionRead:
    elapsed = 0
    while elapsed < timeout:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        execution = api.executions.get(execution_id=UUID(exec_id), include="activities").assert_and_get()
        if execution.status in _TERMINAL:
            return execution
    pytest.fail(f"Execution {exec_id} did not finish within {timeout}s")


def _run_workflow(
    api: SyntaraApiRegistry,
    name: str,
    definition: dict[str, Any],
    timeout: int = POLL_TIMEOUT,
    project_id: UUID | None = None,
) -> ExecutionRead:
    workflows_list = api.workflows.list(additional_params={"name": name}).assert_and_get()
    existing = [w for w in workflows_list.resources if w.name == name]

    wf_def = WorkflowDefinition.from_dict(definition)

    if existing:
        wf_id = existing[0].id
        api.workflows.update(
            workflow_id=wf_id,
            body=WorkflowUpdate(workflow_definition=wf_def),
        )
    else:
        workflow = api.workflows.create(
            body=WorkflowCreate(
                name=name,
                description=f"E2E: {name}",
                workflow_definition=wf_def,
                project_id=project_id,
            )
        ).assert_and_get()
        wf_id = workflow.id

    execution = api.executions.create(
        body=ExecutionCreate(workflow_id=wf_id, trigger_node_id="trigger")
    ).assert_and_get()
    return _poll(api, str(execution.id), timeout=timeout)


def _patch_setting(api: SyntaraApiRegistry, key: str, *, value: int | bool) -> None:
    """Update a setting."""
    api.settings.update(key=key, body=SettingUpdate(value=value)).assert_and_get()


# ---------------------------------------------------------------------------
# script_timeout_seconds — verify timeout actually kills a slow script
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_script_timeout_setting_affects_execution(
    syntara_api: SyntaraApiRegistry,
    first_project_id: UUID,
) -> None:
    """Changing script_timeout_seconds causes a slow script to time out."""
    key = "workflow_engine.script_timeout_seconds"
    original = syntara_api.settings.get(key=key).assert_and_get().to_dict()

    try:
        # Set timeout to 2 seconds
        _patch_setting(syntara_api, key, value=2)

        # Run a script that sleeps for 10 seconds — should be killed by timeout
        result = _run_workflow(
            syntara_api,
            "e2e-settings-script-timeout",
            {
                "name": "runtime_setting",
                "schema_version": "2.0.0",
                "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
                "nodes": [
                    {
                        "id": "slow_script",
                        "name": "Slow Script",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "sleep 10 && echo done"},
                    }
                ],
                "edges": [{"from": "trigger", "to": "slow_script"}],
            },
            project_id=first_project_id,
        )

        assert result.status == ExecutionStatus.FAILED, f"Expected FAILED (timeout), got {result.status}"
    finally:
        _patch_setting(syntara_api, key, value=original["effective_value"])


# ---------------------------------------------------------------------------
# max_loop_iterations — verify loop stops at the configured limit
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_max_loop_iterations_setting_affects_execution(
    syntara_api: SyntaraApiRegistry,
    first_project_id: UUID,
) -> None:
    """Changing max_loop_iterations causes an infinite loop to fail with MaxIterationsError."""
    key = "workflow_engine.max_loop_iterations"
    original = syntara_api.settings.get(key=key).assert_and_get().to_dict()

    try:
        # Set max iterations to 3
        _patch_setting(syntara_api, key, value=3)

        # Run a do_while loop with always-true condition (no max_iterations in config)
        result = _run_workflow(
            syntara_api,
            "e2e-settings-max-loop",
            {
                "name": "runtime_setting",
                "schema_version": "2.0.0",
                "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
                "nodes": [
                    {
                        "id": "loop",
                        "name": "Loop",
                        "type": "loop",
                        "parameters": {
                            "type": "do_while",
                            "condition": "1 == 1",
                        },
                    },
                    {
                        "id": "body",
                        "name": "Body",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo iteration"},
                    },
                ],
                "edges": [
                    {"from": "trigger", "to": "loop"},
                    {"from": "loop", "to": "body", "from_port": "iterate"},
                    {"from": "body", "to": "loop", "to_port": "iterate"},
                ],
            },
            project_id=first_project_id,
        )

        # Exceeding max_iterations raises MaxIterationsError → execution fails
        assert result.status == ExecutionStatus.FAILED, f"Expected FAILED (max iterations), got {result.status}"
    finally:
        _patch_setting(syntara_api, key, value=original["effective_value"])
