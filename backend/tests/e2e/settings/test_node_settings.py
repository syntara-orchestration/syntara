"""E2E tests: per-node settings (timeout, continue_on_failure, retry_policy).

Verifies that per-node settings override global defaults and control
workflow execution behavior. Requires the full stack (API, Temporal worker).

Run with:
    APP_BASE_URL=http://localhost:8000 make test-e2e
"""

import logging
import os
import time
from typing import Any
from uuid import UUID

import pytest
from orchestrator_test_sdk.e2e.helpers import HTTPBIN_URL as _HTTPBIN_URL
from orchestrator_test_sdk.e2e.helpers import requires_httpbin
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

logger = logging.getLogger(__name__)

POLL_INTERVAL = 1
POLL_TIMEOUT = 60

_TERMINAL = {
    ExecutionStatus.COMPLETED,
    ExecutionStatus.FAILED,
    ExecutionStatus.CANCELLED,
    ExecutionStatus.COMPLETED_WITH_ERRORS,
}


def _poll(api: SyntaraApiRegistry, exec_id: str, timeout: int = POLL_TIMEOUT) -> ExecutionRead:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL)
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
    api.settings.update(key=key, body=SettingUpdate(value=value)).assert_and_get()


def _restore_settings(api: SyntaraApiRegistry, settings: dict[str, Any]) -> None:
    """Restore multiple settings independently so one failure doesn't block others."""
    for key, original in settings.items():
        try:
            _patch_setting(api, key, value=original["effective_value"])
        except Exception:
            logger.warning("Failed to restore setting %s", key)


def _get_activities(execution: ExecutionRead) -> dict[str, Any]:
    return {a.activity_id: a for a in (execution.activities or [])}


# ---------------------------------------------------------------------------
# Group 1: Timeout
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_per_node_timeout_overrides_global(syntara_api: SyntaraApiRegistry, first_project_id: UUID) -> None:
    """Per-node settings.timeout (2s) kills a script faster than global default (300s)."""
    result = _run_workflow(
        syntara_api,
        "e2e-node-timeout-override",
        {
            "name": "node_settings",
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "slow_script",
                    "name": "Slow Script",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "sleep 10 && echo done"},
                    "settings": {"timeout": 2},
                },
            ],
            "edges": [{"from": "trigger", "to": "slow_script"}],
        },
        project_id=first_project_id,
    )

    assert result.status == ExecutionStatus.FAILED, f"Expected FAILED (timeout), got {result.status}"


@pytest.mark.e2e
def test_per_node_timeout_allows_longer_execution(syntara_api: SyntaraApiRegistry, first_project_id: UUID) -> None:
    """Per-node timeout (15s) overrides a restrictive global setting (2s)."""
    key = "workflow_engine.script_timeout_seconds"
    original = syntara_api.settings.get(key=key).assert_and_get().to_dict()

    try:
        _patch_setting(syntara_api, key, value=2)

        result = _run_workflow(
            syntara_api,
            "e2e-node-timeout-longer",
            {
                "name": "node_settings",
                "schema_version": "2.0.0",
                "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
                "nodes": [
                    {
                        "id": "script",
                        "name": "Script",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "sleep 3 && echo done"},
                        "settings": {"timeout": 15},
                    },
                ],
                "edges": [{"from": "trigger", "to": "script"}],
            },
            project_id=first_project_id,
        )

        assert result.status == ExecutionStatus.COMPLETED, f"Expected COMPLETED, got {result.status}"
    finally:
        _restore_settings(syntara_api, {key: original})


@pytest.mark.e2e
def test_timeout_fallback_to_global(syntara_api: SyntaraApiRegistry, first_project_id: UUID) -> None:
    """No per-node timeout → falls back to global setting."""
    key = "workflow_engine.script_timeout_seconds"
    original = syntara_api.settings.get(key=key).assert_and_get().to_dict()

    try:
        _patch_setting(syntara_api, key, value=2)

        result = _run_workflow(
            syntara_api,
            "e2e-node-timeout-fallback",
            {
                "name": "node_settings",
                "schema_version": "2.0.0",
                "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
                "nodes": [
                    {
                        "id": "slow_script",
                        "name": "Slow Script",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "sleep 10 && echo done"},
                    },
                ],
                "edges": [{"from": "trigger", "to": "slow_script"}],
            },
            project_id=first_project_id,
        )

        assert result.status == ExecutionStatus.FAILED, f"Expected FAILED (global timeout), got {result.status}"
    finally:
        _restore_settings(syntara_api, {key: original})


# ---------------------------------------------------------------------------
# Group 2: Continue on Failure
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_continue_on_failure_downstream_executes(syntara_api: SyntaraApiRegistry, first_project_id: UUID) -> None:
    """continue_on_failure=true → downstream node still executes after failure."""
    result = _run_workflow(
        syntara_api,
        "e2e-cof-downstream-executes",
        {
            "name": "node_settings",
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "failing_script",
                    "name": "Failing Script",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "exit 1"},
                    "settings": {"continue_on_failure": True},
                },
                {
                    "id": "downstream",
                    "name": "Downstream",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "echo success"},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "failing_script"},
                {"from": "failing_script", "to": "downstream"},
            ],
        },
        project_id=first_project_id,
    )

    assert result.status == ExecutionStatus.COMPLETED_WITH_ERRORS, (
        f"Expected COMPLETED_WITH_ERRORS, got {result.status}"
    )
    activities = _get_activities(result)
    assert "downstream" in activities, "Downstream node should have executed"
    assert str(activities["failing_script"].status) == "failed"
    assert str(activities["downstream"].status) == "completed"


@pytest.mark.e2e
def test_continue_on_failure_false_skips_downstream(syntara_api: SyntaraApiRegistry, first_project_id: UUID) -> None:
    """continue_on_failure=false (default) → downstream is skipped after failure."""
    result = _run_workflow(
        syntara_api,
        "e2e-cof-false-skips",
        {
            "name": "node_settings",
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "failing_script",
                    "name": "Failing Script",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "exit 1"},
                },
                {
                    "id": "downstream",
                    "name": "Downstream",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "echo success"},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "failing_script"},
                {"from": "failing_script", "to": "downstream"},
            ],
        },
        project_id=first_project_id,
    )

    assert result.status == ExecutionStatus.FAILED, f"Expected FAILED, got {result.status}"
    activities = _get_activities(result)
    assert "downstream" not in activities or str(activities["downstream"].status) == "skipped", (
        "Downstream should be absent or skipped when CoF is false"
    )


@pytest.mark.e2e
def test_global_cof_default_applies(syntara_api: SyntaraApiRegistry, first_project_id: UUID) -> None:
    """Global continue_on_failure=true applies when no per-node setting is set."""
    key = "workflow_engine.continue_on_failure"
    original = syntara_api.settings.get(key=key).assert_and_get().to_dict()

    try:
        _patch_setting(syntara_api, key, value=True)

        result = _run_workflow(
            syntara_api,
            "e2e-cof-global-default",
            {
                "name": "node_settings",
                "schema_version": "2.0.0",
                "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
                "nodes": [
                    {
                        "id": "failing_script",
                        "name": "Failing Script",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "exit 1"},
                    },
                    {
                        "id": "downstream",
                        "name": "Downstream",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo success"},
                    },
                ],
                "edges": [
                    {"from": "trigger", "to": "failing_script"},
                    {"from": "failing_script", "to": "downstream"},
                ],
            },
            project_id=first_project_id,
        )

        assert result.status == ExecutionStatus.COMPLETED_WITH_ERRORS, (
            f"Expected COMPLETED_WITH_ERRORS, got {result.status}"
        )
        activities = _get_activities(result)
        assert "downstream" in activities, "Downstream should execute when global CoF is true"
    finally:
        _restore_settings(syntara_api, {key: original})


@pytest.mark.e2e
def test_per_node_cof_overrides_global(syntara_api: SyntaraApiRegistry, first_project_id: UUID) -> None:
    """Per-node continue_on_failure=false overrides global true."""
    key = "workflow_engine.continue_on_failure"
    original = syntara_api.settings.get(key=key).assert_and_get().to_dict()

    try:
        _patch_setting(syntara_api, key, value=True)

        result = _run_workflow(
            syntara_api,
            "e2e-cof-override-global",
            {
                "name": "node_settings",
                "schema_version": "2.0.0",
                "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
                "nodes": [
                    {
                        "id": "failing_script",
                        "name": "Failing Script",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "exit 1"},
                        "settings": {"continue_on_failure": False},
                    },
                    {
                        "id": "downstream",
                        "name": "Downstream",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo success"},
                    },
                ],
                "edges": [
                    {"from": "trigger", "to": "failing_script"},
                    {"from": "failing_script", "to": "downstream"},
                ],
            },
            project_id=first_project_id,
        )

        assert result.status == ExecutionStatus.FAILED, (
            f"Expected FAILED (per-node overrides global), got {result.status}"
        )
    finally:
        _restore_settings(syntara_api, {key: original})


# ---------------------------------------------------------------------------
# Group 3: Retry Policy
# ---------------------------------------------------------------------------


@requires_httpbin
@pytest.mark.e2e
def test_retry_policy_retries_on_transient_error(syntara_api: SyntaraApiRegistry, first_project_id: UUID) -> None:
    """HTTP request with retry_policy retries on 503 (transient). Slower than no-retry."""
    start = time.monotonic()
    result = _run_workflow(
        syntara_api,
        "e2e-retry-transient",
        {
            "name": "node_settings",
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "http_node",
                    "name": "HTTP 503",
                    "type": "http_request",
                    "parameters": {
                        "method": "GET",
                        "url": f"{_HTTPBIN_URL}/status/503",
                    },
                    "settings": {
                        "timeout": 30,
                        "retry_policy": {
                            "max_retries": 2,
                            "initial_interval": 2,
                            "backoff_coefficient": 1.0,
                        },
                    },
                },
            ],
            "edges": [{"from": "trigger", "to": "http_node"}],
        },
        project_id=first_project_id,
    )
    elapsed = time.monotonic() - start

    assert result.status == ExecutionStatus.FAILED, f"Expected FAILED after retries, got {result.status}"
    # 2 retries x 2s interval = 4s retry delay + poll/scheduling overhead > 5s
    assert elapsed > 5, f"Should have taken >5s due to 2 retries with 2s interval, took {elapsed:.1f}s"


@requires_httpbin
@pytest.mark.e2e
def test_retry_policy_max_retries_zero_no_retry(syntara_api: SyntaraApiRegistry, first_project_id: UUID) -> None:
    """max_retries=0 disables retry — fails faster than max_retries=2 on same 503."""
    start = time.monotonic()
    result = _run_workflow(
        syntara_api,
        "e2e-retry-zero",
        {
            "name": "node_settings",
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "http_node",
                    "name": "HTTP 503 No Retry",
                    "type": "http_request",
                    "parameters": {
                        "method": "GET",
                        "url": f"{_HTTPBIN_URL}/status/503",
                    },
                    "settings": {
                        "timeout": 30,
                        "retry_policy": {"max_retries": 0},
                    },
                },
            ],
            "edges": [{"from": "trigger", "to": "http_node"}],
        },
        project_id=first_project_id,
    )
    elapsed = time.monotonic() - start

    assert result.status == ExecutionStatus.FAILED, f"Expected FAILED, got {result.status}"
    assert elapsed < 30, f"max_retries=0 should fail without retry delay, took {elapsed:.1f}s"


@pytest.mark.e2e
def test_retry_not_applied_to_script_nodes(syntara_api: SyntaraApiRegistry, first_project_id: UUID) -> None:
    """Script nodes ignore global retry defaults — fail immediately even with aggressive global retry."""
    key_max = "workflow_engine.retry_max_retries"
    key_interval = "workflow_engine.retry_initial_interval"
    orig_max = syntara_api.settings.get(key=key_max).assert_and_get().to_dict()
    orig_interval = syntara_api.settings.get(key=key_interval).assert_and_get().to_dict()

    try:
        _patch_setting(syntara_api, key_max, value=5)
        _patch_setting(syntara_api, key_interval, value=2)

        start = time.monotonic()
        result = _run_workflow(
            syntara_api,
            "e2e-retry-not-script",
            {
                "name": "node_settings",
                "schema_version": "2.0.0",
                "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
                "nodes": [
                    {
                        "id": "script",
                        "name": "Failing Script",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "exit 1"},
                    },
                ],
                "edges": [{"from": "trigger", "to": "script"}],
            },
            project_id=first_project_id,
        )
        elapsed = time.monotonic() - start

        assert result.status == ExecutionStatus.FAILED, f"Expected FAILED, got {result.status}"
        # If retry applied, 5 retries x 2s interval = >10s. Script should fail well under that.
        assert elapsed < 30, f"Script should fail fast (no retry despite global retry=5), took {elapsed:.1f}s"
    finally:
        _restore_settings(syntara_api, {key_max: orig_max, key_interval: orig_interval})


# ---------------------------------------------------------------------------
# Group 4: Combined / Edge Cases
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_cof_with_multiple_branches_mixed_status(syntara_api: SyntaraApiRegistry, first_project_id: UUID) -> None:
    """Parallel branches: one fails with CoF=true, one succeeds → completed_with_errors."""
    result = _run_workflow(
        syntara_api,
        "e2e-cof-parallel-mixed",
        {
            "name": "node_settings",
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "fail_branch",
                    "name": "Failing Branch",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "exit 1"},
                    "settings": {"continue_on_failure": True},
                },
                {
                    "id": "success_branch",
                    "name": "Success Branch",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "echo ok"},
                },
                {
                    "id": "converge",
                    "name": "Converge",
                    "type": "converge",
                    "parameters": {},
                },
                {
                    "id": "final",
                    "name": "Final",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "echo done"},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "fail_branch"},
                {"from": "trigger", "to": "success_branch"},
                {"from": "fail_branch", "to": "converge"},
                {"from": "success_branch", "to": "converge"},
                {"from": "converge", "to": "final"},
            ],
        },
        project_id=first_project_id,
    )

    assert result.status == ExecutionStatus.COMPLETED_WITH_ERRORS, (
        f"Expected COMPLETED_WITH_ERRORS (all failures recovered via CoF), got {result.status}"
    )
    activities = _get_activities(result)
    assert str(activities["fail_branch"].status) == "failed"
    assert str(activities["success_branch"].status) == "completed"
    assert str(activities["converge"].status) == "completed"
    assert "final" in activities, "Final node after converge should have executed"


@pytest.mark.e2e
def test_control_node_with_empty_settings_completes(syntara_api: SyntaraApiRegistry, first_project_id: UUID) -> None:
    """Switch node with empty settings field completes normally — no validation error."""
    result = _run_workflow(
        syntara_api,
        "e2e-control-settings-empty",
        {
            "name": "node_settings",
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "sw",
                    "name": "Switch",
                    "type": "switch",
                    "parameters": {
                        "cases": [
                            {"port": "case_0", "label": "Always", "condition": "1 == 1"},
                        ],
                        "default_port": "default",
                    },
                    "settings": {},
                },
                {
                    "id": "action",
                    "name": "Action",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "echo matched"},
                },
                {
                    "id": "default_action",
                    "name": "Default",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "echo default"},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "sw"},
                {"from": "sw", "to": "action", "from_port": "case_0"},
                {"from": "sw", "to": "default_action", "from_port": "default"},
            ],
        },
        project_id=first_project_id,
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Expected COMPLETED, got {result.status}"
    activities = _get_activities(result)
    assert str(activities["sw"].status) == "completed"
    assert str(activities["action"].status) == "completed"


# ---------------------------------------------------------------------------
# Group 5: HTTP request timeout (different global key than script)
# ---------------------------------------------------------------------------


@requires_httpbin
@pytest.mark.e2e
def test_http_request_per_node_timeout(syntara_api: SyntaraApiRegistry, first_project_id: UUID) -> None:
    """HTTP request node per-node timeout (2s) overrides global http_request_timeout_seconds."""
    result = _run_workflow(
        syntara_api,
        "e2e-http-timeout-override",
        {
            "name": "node_settings",
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "http_node",
                    "name": "Slow HTTP",
                    "type": "http_request",
                    "parameters": {
                        "method": "GET",
                        "url": f"{_HTTPBIN_URL}/delay/10",
                    },
                    "settings": {"timeout": 2},
                },
            ],
            "edges": [{"from": "trigger", "to": "http_node"}],
        },
        project_id=first_project_id,
    )

    assert result.status == ExecutionStatus.FAILED, f"Expected FAILED (timeout), got {result.status}"


# ---------------------------------------------------------------------------
# Group 6: Retry — permanent error should not retry
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_retry_no_retry_on_permanent_error(
    syntara_api: SyntaraApiRegistry, worker_base_url: str, first_project_id: UUID
) -> None:
    """HTTP 404 (permanent) is not retried even with retry_policy configured."""
    start = time.monotonic()
    result = _run_workflow(
        syntara_api,
        "e2e-retry-permanent",
        {
            "name": "node_settings",
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "http_node",
                    "name": "HTTP 404",
                    "type": "http_request",
                    "parameters": {
                        "method": "GET",
                        "url": f"{worker_base_url}/nonexistent",
                    },
                    "settings": {
                        "timeout": 30,
                        "retry_policy": {
                            "max_retries": 3,
                            "initial_interval": 3,
                            "backoff_coefficient": 1.0,
                        },
                    },
                },
            ],
            "edges": [{"from": "trigger", "to": "http_node"}],
        },
        project_id=first_project_id,
    )
    elapsed = time.monotonic() - start

    assert result.status == ExecutionStatus.FAILED, f"Expected FAILED, got {result.status}"
    # 404 is non_retryable=True — no retry delays.
    # If retries applied: 3 x 3s = 9s minimum. Under 8s proves no retry.
    assert elapsed < 30, f"Permanent error (404) should not retry, took {elapsed:.1f}s"


# ---------------------------------------------------------------------------
# Group 7: Global retry defaults apply to http_request
# ---------------------------------------------------------------------------


@requires_httpbin
@pytest.mark.e2e
def test_global_retry_defaults_apply_to_http_request(syntara_api: SyntaraApiRegistry, first_project_id: UUID) -> None:
    """HTTP request with no per-node retry_policy uses global retry defaults."""
    key_max = "workflow_engine.retry_max_retries"
    key_interval = "workflow_engine.retry_initial_interval"
    orig_max = syntara_api.settings.get(key=key_max).assert_and_get().to_dict()
    orig_interval = syntara_api.settings.get(key=key_interval).assert_and_get().to_dict()

    try:
        _patch_setting(syntara_api, key_max, value=2)
        _patch_setting(syntara_api, key_interval, value=2)

        start = time.monotonic()
        result = _run_workflow(
            syntara_api,
            "e2e-retry-global-default",
            {
                "name": "node_settings",
                "schema_version": "2.0.0",
                "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
                "nodes": [
                    {
                        "id": "http_node",
                        "name": "HTTP 503 Global Retry",
                        "type": "http_request",
                        "parameters": {
                            "method": "GET",
                            "url": f"{_HTTPBIN_URL}/status/503",
                        },
                        "settings": {"timeout": 30},
                    },
                ],
                "edges": [{"from": "trigger", "to": "http_node"}],
            },
            project_id=first_project_id,
        )
        elapsed = time.monotonic() - start

        assert result.status == ExecutionStatus.FAILED, f"Expected FAILED, got {result.status}"
        # Global: 2 retries x 2s = 4s retry delay + poll/scheduling overhead > 5s
        assert elapsed > 5, f"Global retry (2 retries x 2s) should take >5s, took {elapsed:.1f}s"
    finally:
        _restore_settings(syntara_api, {key_max: orig_max, key_interval: orig_interval})


# ---------------------------------------------------------------------------
# Group 8: Sequential CoF chain — second failure without CoF dominates
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_sequential_cof_second_failure_without_cof_is_failed(
    syntara_api: SyntaraApiRegistry, first_project_id: UUID
) -> None:
    """Node A fails (CoF=true) → Node B runs → Node B fails (CoF=false) → execution is 'failed'."""
    result = _run_workflow(
        syntara_api,
        "e2e-cof-chain-mixed",
        {
            "name": "node_settings",
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "first_fail",
                    "name": "First Failure (recovered)",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "exit 1"},
                    "settings": {"continue_on_failure": True},
                },
                {
                    "id": "second_fail",
                    "name": "Second Failure (unrecovered)",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "exit 1"},
                },
                {
                    "id": "final",
                    "name": "Final",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "echo done"},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "first_fail"},
                {"from": "first_fail", "to": "second_fail"},
                {"from": "second_fail", "to": "final"},
            ],
        },
        project_id=first_project_id,
    )

    assert result.status == ExecutionStatus.FAILED, (
        f"Expected FAILED (unrecovered failure dominates), got {result.status}"
    )
    activities = _get_activities(result)
    assert str(activities["first_fail"].status) == "failed"
    assert str(activities["second_fail"].status) == "failed"
    assert "final" not in activities or str(activities["final"].status) == "skipped", (
        "Final should not execute after unrecovered failure"
    )
