"""Shared utility functions for Syntara E2E tests."""

from __future__ import annotations

import copy
import os
import time
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import httpx
import pytest
from syntara_api_client.models import (
    ExecutionCreate,
    ExecutionRead,
    WorkflowCreate,
    WorkflowUpdate,
)
from syntara_api_client.models.approval_request_status import ApprovalRequestStatus
from syntara_api_client.models.execution_status import ExecutionStatus
from syntara_api_client.models.workflow_definition import WorkflowDefinition

if TYPE_CHECKING:
    from syntara_api_client.api import SyntaraApiRegistry
    from syntara_api_client.models.approval_request_read import ApprovalRequestRead

POLL_INTERVAL = 1
POLL_TIMEOUT = 20
API_RETRIES = 3
API_RETRY_DELAY = 2

# Inline frozenset of terminal status strings — avoids importing from syntara app source.
TERMINAL_EXECUTION_STATUSES: frozenset[str] = frozenset({"completed", "completed_with_errors", "failed", "cancelled"})


def get_first_non_builtin_project_id(api: SyntaraApiRegistry) -> UUID:
    """Return the ID of the first available non-builtin project.

    Raises AssertionError if no non-builtin projects exist.
    """
    projects_list = api.projects.list().assert_and_get()
    for project in projects_list.resources:
        if not getattr(project, "is_builtin", False):
            return UUID(str(project.id))
    msg = "No non-builtin projects available"
    raise AssertionError(msg)


TERMINAL_STATUSES = {
    ExecutionStatus.COMPLETED,
    ExecutionStatus.COMPLETED_WITH_ERRORS,
    ExecutionStatus.FAILED,
    ExecutionStatus.CANCELLED,
}


def _retry_api_call(fn, *, retries: int = API_RETRIES, delay: float = API_RETRY_DELAY):  # noqa: ANN202
    """Retry an API call on transient failures (connection errors, server disconnects, 500s)."""
    last_exc = None
    for attempt in range(retries):
        try:
            result = fn()
        except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError) as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(delay)
                continue
            raise
        if hasattr(result, "status_code") and result.status_code >= 500 and attempt < retries - 1:
            time.sleep(delay)
            continue
        return result
    raise last_exc  # type: ignore[misc]


def poll_execution(
    api: SyntaraApiRegistry, exec_id: str, timeout: int = POLL_TIMEOUT, interval: int = POLL_INTERVAL
) -> ExecutionRead:
    """Poll until execution reaches a terminal state, returning the final ExecutionRead."""
    elapsed = 0
    while elapsed < timeout:
        time.sleep(interval)
        elapsed += interval
        response = _retry_api_call(lambda: api.executions.get(execution_id=UUID(exec_id), include="activities"))
        execution: ExecutionRead = response.assert_and_get()
        if execution.status in TERMINAL_STATUSES:
            return execution
    pytest.fail(f"Execution {exec_id} did not finish within {timeout}s")


def poll_for_pending_approval(
    api: SyntaraApiRegistry,
    execution_id: UUID,
    timeout: int = 30,
    interval: int = 1,
) -> ApprovalRequestRead:
    """Poll until a PENDING approval request appears for the given execution."""
    elapsed = 0
    while elapsed < timeout:
        time.sleep(interval)
        elapsed += interval
        response = _retry_api_call(
            lambda: api.approvals.list(
                execution_id=execution_id,
                status=ApprovalRequestStatus.PENDING,
                limit=5,
            )
        )
        result = response.assert_and_get()
        if result.resources:
            return cast("ApprovalRequestRead", result.resources[0])
    pytest.fail(
        f"No PENDING approval for execution {execution_id} within {timeout}s. "
        "Check that Temporal is running: make temporal-run"
    )


def wait_for_agentic_activity(
    api: SyntaraApiRegistry,
    execution_id: UUID,
    activity_id: str,
    *,
    max_polls: int = 30,
    poll_interval: int = 1,
) -> None:
    """Poll until the agentic activity is running and ready for a signal.

    Agentic nodes stay in ``running`` while blocked on the completion
    callback — they never reach ``waiting`` (that status is only for
    approval and wait nodes).  ``pending`` is too early: the Temporal
    workflow may not have started yet.
    """
    for _ in range(max_polls):
        exec_state = _retry_api_call(lambda: api.executions.get(execution_id=execution_id, include="activities"))
        execution: ExecutionRead = exec_state.assert_and_get()

        if execution.status in TERMINAL_STATUSES:
            pytest.fail(
                f"Execution reached terminal state '{execution.status}' before signal could be sent. "
                "The agent orchestrator may have completed the activity, or the activity failed."
            )

        activities_by_id = {a.activity_id: a for a in (execution.activities or [])}
        activity = activities_by_id.get(activity_id)
        if activity and activity.status in {"running", "waiting"}:
            return

        time.sleep(poll_interval)

    pytest.fail(f"Agentic activity '{activity_id}' did not reach running state within {max_polls * poll_interval}s")


def create_and_run_workflow(
    api: SyntaraApiRegistry,
    name: str,
    definition: dict[str, Any],
    timeout: int = POLL_TIMEOUT,
    project_id: UUID | None = None,
) -> ExecutionRead:
    """Create (or update) a workflow, execute it, and return the completed ExecutionRead.

    If *project_id* is not provided, the first available project is looked up from the API.
    """
    if project_id is None:
        project_id = get_first_non_builtin_project_id(api)

    list_response = _retry_api_call(
        lambda: api.workflows.list(additional_params={"name": name, "project_id[eq]": str(project_id)})
    )
    workflows_list = list_response.assert_and_get()
    existing = [w for w in workflows_list.resources if w.name == name]

    wf_def = WorkflowDefinition.from_dict(definition)

    if existing:
        wf_id = existing[0].id
        update_response = _retry_api_call(
            lambda: api.workflows.update(workflow_id=wf_id, body=WorkflowUpdate(workflow_definition=wf_def))
        )
        update_response.assert_and_get()
    else:
        create_response = _retry_api_call(
            lambda: api.workflows.create(
                body=WorkflowCreate(
                    name=name,
                    description=f"E2E test: {name}",
                    workflow_definition=wf_def,
                    project_id=project_id,
                )
            )
        )
        workflow = create_response.assert_and_get()
        wf_id = workflow.id

    trigger_node_id = definition.get("triggers", [{}])[0].get("id", "trigger")
    exec_response = _retry_api_call(
        lambda: api.executions.create(body=ExecutionCreate(workflow_id=wf_id, trigger_node_id=trigger_node_id))
    )
    execution = exec_response.assert_and_get()
    return poll_execution(api, str(execution.id), timeout=timeout)


# ---------------------------------------------------------------------------
# Reusable workflow definitions for verification / test-node tests
# ---------------------------------------------------------------------------

_TRIGGER: dict[str, Any] = {"id": "trigger", "type": "manual_trigger", "parameters": {}}

_CONDITION_NODE: dict[str, Any] = {
    "id": "condition_node",
    "name": "Check Condition",
    "type": "condition",
    "parameters": {"condition": "true"},
}

_ACTION_NODE: dict[str, Any] = {
    "id": "action_node",
    "name": "Run Action",
    "type": "script",
    "parameters": {"language": "bash", "code": "echo 'action executed'"},
}

_EXTRA_NODE: dict[str, Any] = {
    "id": "extra_node",
    "name": "Extra Step",
    "type": "script",
    "parameters": {"language": "bash", "code": "echo 'extra step'"},
}


def connected_definition() -> dict[str, Any]:
    """Trigger -> Condition -> Action (valid, fully connected)."""
    return copy.deepcopy(
        {
            "name": "verification-e2e",
            "schema_version": "2.0.0",
            "triggers": [_TRIGGER],
            "nodes": [_CONDITION_NODE, _ACTION_NODE],
            "edges": [
                {"from": "trigger", "to": "condition_node"},
                {"from": "condition_node", "to": "action_node", "from_port": "true"},
            ],
        }
    )


def orphaned_definition() -> dict[str, Any]:
    """Trigger -> Action only; Condition is orphaned (no incoming edge)."""
    return copy.deepcopy(
        {
            "name": "verification-e2e",
            "schema_version": "2.0.0",
            "triggers": [_TRIGGER],
            "nodes": [_CONDITION_NODE, _ACTION_NODE],
            "edges": [
                {"from": "trigger", "to": "action_node"},
            ],
        }
    )


def extended_definition() -> dict[str, Any]:
    """Trigger -> Condition -> Extra -> Action (valid, with extra node)."""
    return copy.deepcopy(
        {
            "name": "verification-e2e",
            "schema_version": "2.0.0",
            "triggers": [_TRIGGER],
            "nodes": [_CONDITION_NODE, _EXTRA_NODE, _ACTION_NODE],
            "edges": [
                {"from": "trigger", "to": "condition_node"},
                {"from": "condition_node", "to": "extra_node", "from_port": "true"},
                {"from": "extra_node", "to": "action_node"},
            ],
        }
    )


# ---------------------------------------------------------------------------
# Execution polling helper (from tests/e2e/conftest.py)
# ---------------------------------------------------------------------------


def poll_execution_until_complete(
    syntara_api: SyntaraApiRegistry,
    execution_id: UUID,
    max_polls: int = 30,
    poll_interval: int = 2,
) -> ExecutionRead:
    """Poll execution until it reaches a terminal state.

    Args:
        syntara_api: API client for making requests
        execution_id: ID of the execution to poll
        max_polls: Maximum number of polling attempts (default: 30)
        poll_interval: Seconds to wait between polls (default: 2)

    Returns:
        ExecutionRead with final terminal state (completed, failed, cancelled, or completed_with_errors)

    Raises:
        AssertionError: If execution does not reach terminal state within timeout

    """
    for _ in range(max_polls):
        execution = syntara_api.executions.get(
            execution_id=execution_id,
            include="activities",
        ).assert_and_get()

        status = str(execution.status)
        if status in TERMINAL_EXECUTION_STATUSES:
            return execution

        time.sleep(poll_interval)

    timeout_seconds = max_polls * poll_interval
    msg = (
        f"Execution {execution_id} did not complete within {timeout_seconds}s. "
        "Temporal may not be running. Start it with: make temporal-run"
    )
    raise AssertionError(msg)


# ---------------------------------------------------------------------------
# httpbin helpers — shared across E2E test files
# ---------------------------------------------------------------------------

_HTTPBIN_ALLOWED_HOSTS = {"httpbin.org", "httpbin"}

HTTPBIN_URL: str = os.environ.get("HTTPBIN_URL", "https://httpbin.org")

_parsed = urllib.parse.urlparse(HTTPBIN_URL)
if _parsed.scheme not in ("http", "https") or not any(h in (_parsed.hostname or "") for h in _HTTPBIN_ALLOWED_HOSTS):
    HTTPBIN_URL = "https://httpbin.org"


_httpbin_cached: bool | None = None


def httpbin_available() -> bool:
    """Check if httpbin is reachable. Cache the result for the session."""
    global _httpbin_cached  # noqa: PLW0603
    if _httpbin_cached is None:
        try:
            urllib.request.urlopen(f"{HTTPBIN_URL}/status/200", timeout=5)  # noqa: S310
            _httpbin_cached = True
        except Exception:
            _httpbin_cached = False
    return _httpbin_cached


requires_httpbin = pytest.mark.skipif(
    not httpbin_available(),
    reason=f"httpbin not reachable at {HTTPBIN_URL}. Set HTTPBIN_URL to override.",
)
