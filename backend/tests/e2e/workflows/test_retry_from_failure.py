"""Backend E2E coverage for retry-from-failure replay and output injection.

These tests use the generated API client against the live API and Temporal worker.
They assert observable execution state and outputs rather than workflow-engine internals.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, TypeVar

import pytest
from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.auth import api_for
from orchestrator_test_sdk.e2e.helpers import create_and_run_workflow, poll_execution_until_complete
from syntara_api_client.models import ExecutionCreate, RetryFailureRequest, RetryFromFailureValidationResponse
from syntara_api_client.models.execution_status import ExecutionStatus
from syntara_api_client.types import UnexpectedResponseException, Unset

if TYPE_CHECKING:
    from uuid import UUID

    from orchestrator_test_sdk.factories import (
        AssignProjectRoleFactory,
        ProjectFactory,
        ProjectRoleFactory,
        UserFactory,
    )
    from syntara_api_client.api import SyntaraApiRegistry
    from syntara_api_client.models import ExecutionRead
    from syntara_api_client.models.activity_data import ActivityData
    from syntara_api_client.models.activity_execution import ActivityExecution

pytestmark = [pytest.mark.e2e]

_RETRY_RUN_POLICIES = [
    "workflow:read:project",
    "execution:run:project",
    "execution:read:project",
]

_T = TypeVar("_T")

# Cluster load can leave activity rows and stdout 30s+ behind a terminal execution.
_ACTIVITY_SYNC_POLLS = 90
_ACTIVITY_SYNC_INTERVAL = 1
_TRANSIENT_GATEWAY_STATUSES = {502}
_TERMINAL_ACTIVITY_STATUSES = frozenset({"completed", "failed", "skipped", "cancelled"})


def _script_node(node_id: str, code: str, *, environment: dict[str, str] | None = None) -> dict[str, Any]:
    parameters: dict[str, Any] = {"language": "python", "code": code}
    if environment is not None:
        parameters["environment"] = environment
    return {"id": node_id, "name": node_id, "type": "script", "parameters": parameters}


def _workflow_definition(
    name: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "name": name,
        "schema_version": "2.0.0",
        "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
        "nodes": nodes,
        "edges": edges,
    }


def _parallel_failure_definition(name: str) -> dict[str, Any]:
    """Build two independent failure branches with work that follows each one."""
    return _workflow_definition(
        name,
        [
            _script_node("failure_a", "raise SystemExit(1)"),
            _script_node("failure_b", "raise SystemExit(1)"),
            _script_node("after_a", "print('after-a')"),
            _script_node("after_b", "print('after-b')"),
        ],
        [
            {"from": "trigger", "to": "failure_a"},
            {"from": "trigger", "to": "failure_b"},
            {"from": "failure_a", "to": "after_a"},
            {"from": "failure_b", "to": "after_b"},
        ],
    )


def _activities_by_id(execution: ExecutionRead) -> dict[str, ActivityData]:
    activities = execution.activities
    assert isinstance(activities, list), "Execution response must include activities"
    return {activity.activity_id: activity for activity in activities}


def _activity_output(activity: ActivityData | ActivityExecution) -> dict[str, Any]:
    value = activity.output_data
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    additional_properties = getattr(value, "additional_properties", None)
    return dict(additional_properties) if isinstance(additional_properties, Mapping) else {}


def _activity_input(activity: ActivityExecution) -> dict[str, Any]:
    value = activity.input_data
    if isinstance(value, Unset):
        return {}
    return dict(value.additional_properties)


def _activity_status(activity: ActivityData | ActivityExecution) -> str:
    return str(getattr(activity.status, "value", activity.status))


def _is_terminal_activity(activity: ActivityData | ActivityExecution) -> bool:
    return _activity_status(activity) in _TERMINAL_ACTIVITY_STATUSES


def _skip_transient_gateway(exc: UnexpectedResponseException) -> None:
    if exc.status_code in _TRANSIENT_GATEWAY_STATUSES:
        pytest.skip("Backend returned 502 Bad Gateway — transient infrastructure issue")


def _activity_executions_by(
    syntara_api: SyntaraApiRegistry,
    execution_id: UUID,
    key: Callable[[ActivityExecution], str],
) -> dict[str, ActivityExecution]:
    executions = syntara_api.executions.list_activities(execution_id=execution_id, limit=100).assert_and_get()
    return {key(activity): activity for activity in executions.resources}


def _wait_until(
    fetch_next: Callable[[], _T],
    is_ready: Callable[[_T], bool],
    timeout_details: Callable[[_T], str],
    *,
    description: str,
    max_polls: int,
    poll_interval: int,
) -> _T:
    """Poll one value consistently, with ``max_polls`` counting observations."""
    value: _T | None = None
    for attempt in range(max_polls):
        try:
            value = fetch_next()
        except UnexpectedResponseException as exc:
            if exc.status_code in _TRANSIENT_GATEWAY_STATUSES:
                if attempt + 1 < max_polls:
                    time.sleep(poll_interval)
                    continue
                pytest.skip("Backend returned 502 Bad Gateway — transient infrastructure issue")
            raise
        if is_ready(value):
            return value
        if attempt + 1 < max_polls:
            time.sleep(poll_interval)
    assert value is not None
    msg = f"Timed out waiting for {description}. {timeout_details(value)}"
    raise AssertionError(msg)


def _wait_for_activity_executions(
    syntara_api: SyntaraApiRegistry,
    execution_id: UUID,
    required_temporal_ids: set[str],
    *,
    required_stdouts: Mapping[str, str] | None = None,
    max_polls: int = _ACTIVITY_SYNC_POLLS,
    poll_interval: int = _ACTIVITY_SYNC_INTERVAL,
) -> dict[str, ActivityExecution]:
    """Wait for activity rows, terminal status, and optional stdout to sync."""
    stdout_snippets = dict(required_stdouts or {})

    def fetch_rows() -> dict[str, ActivityExecution]:
        return _activity_executions_by(syntara_api, execution_id, lambda activity: activity.temporal_activity_id)

    def is_ready(rows: dict[str, ActivityExecution]) -> bool:
        if not required_temporal_ids <= rows.keys():
            return False
        if not all(_is_terminal_activity(rows[temporal_id]) for temporal_id in required_temporal_ids):
            return False
        return all(snippet in _listed_stdout(rows[temporal_id]) for temporal_id, snippet in stdout_snippets.items())

    def missing_rows(rows: dict[str, ActivityExecution]) -> str:
        missing = sorted(required_temporal_ids - rows.keys())
        pending = sorted(
            temporal_id
            for temporal_id in required_temporal_ids
            if temporal_id in rows and not _is_terminal_activity(rows[temporal_id])
        )
        stdout_missing = {
            temporal_id: _listed_stdout(rows[temporal_id])
            for temporal_id, snippet in stdout_snippets.items()
            if temporal_id in rows and snippet not in _listed_stdout(rows[temporal_id])
        }
        return (
            f"Execution {execution_id} is missing activity rows: {missing}; "
            f"non-terminal: {pending}; stdout still missing: {stdout_missing}"
        )

    return _wait_until(
        fetch_rows,
        is_ready,
        missing_rows,
        description=f"activity rows for execution {execution_id}",
        max_polls=max_polls,
        poll_interval=poll_interval,
    )


def _timestamp(activity: ActivityData | ActivityExecution, field: str) -> datetime:
    value = getattr(activity, field)
    label = getattr(activity, "activity_id", None) or getattr(activity, "activity_name", field)
    assert isinstance(value, datetime), f"{label}.{field} must be a timestamp"
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _wait_for_activity_ids(
    syntara_api: SyntaraApiRegistry,
    execution: ExecutionRead,
    required_ids: set[str],
    *,
    required_stdouts: Mapping[str, str] | None = None,
    max_polls: int = _ACTIVITY_SYNC_POLLS,
    poll_interval: int = _ACTIVITY_SYNC_INTERVAL,
) -> ExecutionRead:
    """Wait until include=activities has every expected terminal row.

    Loop iterations are written as later composite keys (``loop_body#iter-1``).
    The execution can already be terminal before those rows have been synced.
    """
    stdout_snippets = dict(required_stdouts or {})

    def present(current: ExecutionRead) -> dict[str, ActivityData]:
        activities = current.activities
        return {activity.activity_id: activity for activity in activities} if isinstance(activities, list) else {}

    def is_ready(current: ExecutionRead) -> bool:
        rows = present(current)
        if not required_ids <= rows.keys():
            return False
        if not all(_is_terminal_activity(rows[activity_id]) for activity_id in required_ids):
            return False
        return all(
            snippet in str(_activity_output(rows[activity_id]).get("stdout", ""))
            for activity_id, snippet in stdout_snippets.items()
        )

    def missing_rows(current: ExecutionRead) -> str:
        rows = present(current)
        missing = sorted(required_ids - rows.keys())
        pending = sorted(
            activity_id
            for activity_id in required_ids
            if activity_id in rows and not _is_terminal_activity(rows[activity_id])
        )
        stdout_missing = {
            activity_id: str(_activity_output(rows[activity_id]).get("stdout", ""))
            for activity_id, snippet in stdout_snippets.items()
            if activity_id in rows and snippet not in str(_activity_output(rows[activity_id]).get("stdout", ""))
        }
        return (
            f"Execution {current.id} is missing activity rows: {missing}; "
            f"non-terminal: {pending}; stdout still missing: {stdout_missing}"
        )

    return _wait_until(
        lambda: syntara_api.executions.get(execution_id=execution.id, include="activities").assert_and_get(),
        is_ready,
        missing_rows,
        description=f"activity rows for execution {execution.id}",
        max_polls=max_polls,
        poll_interval=poll_interval,
    )


def _listed_stdout(activity: ActivityData | ActivityExecution) -> str:
    return str(_activity_output(activity).get("stdout", "")).strip()


def _create_and_run(
    syntara_api: SyntaraApiRegistry,
    name: str,
    definition: dict[str, Any],
    *,
    timeout: int,
    project_id: UUID,
) -> ExecutionRead:
    try:
        return create_and_run_workflow(
            syntara_api,
            name,
            definition,
            timeout=timeout,
            project_id=project_id,
        )
    except UnexpectedResponseException as exc:
        _skip_transient_gateway(exc)
        raise


def _start_retry(
    syntara_api: SyntaraApiRegistry,
    execution_id: UUID,
    retry_point_ids: list[str] | None = None,
    *,
    overrides: dict[str, dict[str, Any]] | None = None,
) -> ExecutionRead:
    request: dict[str, Any] = {}
    if retry_point_ids is not None:
        request["retry_point_ids"] = retry_point_ids
    if overrides is not None:
        request["input_parameter_overrides"] = overrides
    try:
        response = syntara_api.executions.retry_from_failure(
            execution_id=execution_id,
            body=RetryFailureRequest.from_dict(request),
        )
    except UnexpectedResponseException as exc:
        _skip_transient_gateway(exc)
        raise
    if response.status_code in _TRANSIENT_GATEWAY_STATUSES:
        pytest.skip("Backend returned 502 Bad Gateway — transient infrastructure issue")
    assert response.status_code == HTTPStatus.CREATED
    return response.assert_and_get()


def _preview_retry(syntara_api: SyntaraApiRegistry, execution_id: UUID) -> RetryFromFailureValidationResponse:
    try:
        return syntara_api.executions.retry_from_failure_preview(execution_id=execution_id).assert_and_get()
    except UnexpectedResponseException as exc:
        _skip_transient_gateway(exc)
        raise


def _create_failed_parallel_source(
    syntara_api: SyntaraApiRegistry,
    project_id: UUID,
    *,
    name_prefix: str,
) -> tuple[ExecutionRead, dict[str, ActivityData]]:
    """Create a failed parallel run with both failures and preview eligibility confirmed."""
    name = unique_name(name_prefix)
    source = _create_and_run(
        syntara_api,
        name,
        _parallel_failure_definition(name),
        timeout=60,
        project_id=project_id,
    )
    assert source.status == ExecutionStatus.FAILED
    source = _wait_for_activity_ids(syntara_api, source, {"failure_a", "failure_b"})
    source_activities = _activities_by_id(source)
    assert source_activities["failure_a"].status == "failed"
    assert source_activities["failure_b"].status == "failed"

    preview = _preview_retry(syntara_api, source.id)
    assert preview.eligible is True
    assert set(preview.eligible_point_ids) == {"failure_a", "failure_b"}
    return source, source_activities


def test_retry_replays_upstream_output_and_applies_override_for_retry_only(
    syntara_api: SyntaraApiRegistry,
    first_project_id: UUID,
) -> None:
    """A retry restores its upstream value, reruns downstream work, and keeps overrides run-local."""
    name = unique_name("e2e-retry-replay-output")
    definition = _workflow_definition(
        name,
        [
            _script_node("producer", 'print(\'{"marker": "from-source"}\')'),
            _script_node(
                "repair",
                "import os; print(os.environ['MESSAGE']); raise SystemExit(1)",
                environment={"MESSAGE": "$" + "{producer.stdout_json.marker}"},
            ),
            _script_node(
                "consumer",
                "import os; print(os.environ['MESSAGE'])",
                environment={"MESSAGE": "$" + "{repair.stdout}"},
            ),
        ],
        [
            {"from": "trigger", "to": "producer"},
            {"from": "producer", "to": "repair"},
            {"from": "repair", "to": "consumer"},
        ],
    )

    source = _create_and_run(
        syntara_api,
        name,
        definition,
        timeout=60,
        project_id=first_project_id,
    )
    assert source.status == ExecutionStatus.FAILED
    source = _wait_for_activity_ids(syntara_api, source, {"producer", "repair", "trigger"})
    source_activities = _activities_by_id(source)
    assert source_activities["producer"].status == "completed"
    assert source_activities["repair"].status == "failed"
    source_activity_executions = _wait_for_activity_executions(
        syntara_api, source.id, {"producer", "repair", "trigger"}
    )
    assert _activity_input(source_activity_executions["repair"]).get("environment") == {"MESSAGE": "from-source"}
    source_trigger = source_activity_executions["trigger"]
    assert source_trigger.status == "completed"

    preview = _preview_retry(syntara_api, source.id)
    assert preview.eligible is True
    assert preview.eligible_point_ids == ["repair"]

    retried = _start_retry(
        syntara_api,
        source.id,
        ["repair"],
        overrides={
            "repair": {
                "code": "import os; print(os.environ['MESSAGE'])",
                "environment": {"MESSAGE": "retry-only"},
            }
        },
    )
    assert retried.retried_from_execution_id == source.id
    assert retried.workflow_version_id == source.workflow_version_id

    final = poll_execution_until_complete(syntara_api, retried.id, max_polls=90, poll_interval=1)
    assert final.status == ExecutionStatus.COMPLETED, final.error_details
    final = _wait_for_activity_ids(
        syntara_api,
        final,
        {"producer", "repair", "consumer", "trigger"},
        required_stdouts={"consumer": "retry-only"},
    )
    retry_activities = _activities_by_id(final)
    retry_activity_executions = _wait_for_activity_executions(
        syntara_api,
        final.id,
        {"producer", "repair", "consumer", "trigger"},
        required_stdouts={"consumer": "retry-only"},
    )
    assert _activity_input(retry_activity_executions["repair"]).get("environment") == {"MESSAGE": "retry-only"}

    # Retry dispatches the trigger again but keeps its original display timestamps.
    retry_trigger = retry_activity_executions["trigger"]
    assert retry_trigger.id != source_trigger.id
    assert retry_trigger.status == "completed"
    assert _timestamp(retry_trigger, "started_at") == _timestamp(source_trigger, "started_at")
    assert _timestamp(retry_trigger, "completed_at") == _timestamp(source_trigger, "completed_at")

    # Replayed activities retain their source timestamps and output.
    assert _activity_output(retry_activities["producer"]) == _activity_output(source_activities["producer"])
    assert _timestamp(retry_activities["producer"], "started_at") == _timestamp(
        source_activities["producer"], "started_at"
    )
    assert _timestamp(retry_activities["producer"], "completed_at") == _timestamp(
        source_activities["producer"], "completed_at"
    )

    # The selected failure and its downstream node execute in the retry run.
    assert retry_activities["repair"].status == "completed"
    assert _timestamp(retry_activities["repair"], "started_at") > _timestamp(source_activities["repair"], "started_at")
    assert retry_activities["consumer"].status == "completed"
    assert "retry-only" in _activity_output(retry_activities["consumer"]).get("stdout", "")

    # A later ordinary run uses the unchanged workflow definition and fails again.
    try:
        ordinary_run = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=source.workflow_id, trigger_node_id="trigger")
        ).assert_and_get()
    except UnexpectedResponseException as exc:
        _skip_transient_gateway(exc)
        raise
    ordinary_final = poll_execution_until_complete(
        syntara_api,
        ordinary_run.id,
        max_polls=90,
        poll_interval=1,
    )
    assert ordinary_final.status == ExecutionStatus.FAILED
    ordinary_activity_executions = _wait_for_activity_executions(syntara_api, ordinary_run.id, {"repair"})
    assert _activity_input(ordinary_activity_executions["repair"]).get("environment") == {"MESSAGE": "from-source"}


def test_completed_execution_is_not_eligible_for_retry_from_failure(
    syntara_api: SyntaraApiRegistry,
    first_project_id: UUID,
) -> None:
    name = unique_name("e2e-retry-not-eligible")
    source = _create_and_run(
        syntara_api,
        name,
        _workflow_definition(
            name,
            [_script_node("finished", "print('done')")],
            [{"from": "trigger", "to": "finished"}],
        ),
        timeout=60,
        project_id=first_project_id,
    )
    assert source.status == ExecutionStatus.COMPLETED

    preview = _preview_retry(syntara_api, source.id)
    assert preview.eligible is False
    assert preview.reason

    response = syntara_api.executions.retry_from_failure(
        execution_id=source.id,
        body=RetryFailureRequest.from_dict({"retry_point_ids": []}),
    )
    if response.status_code in _TRANSIENT_GATEWAY_STATUSES:
        pytest.skip("Backend returned 502 Bad Gateway — transient infrastructure issue")
    assert response.status_code == HTTPStatus.CONFLICT
    assert getattr(response.parsed, "code", None) == "EXECUTION_NOT_RETRYABLE_FROM_FAILURE"


def test_retry_handles_an_unselected_branch_without_replay_output(
    syntara_api: SyntaraApiRegistry,
    first_project_id: UUID,
) -> None:
    """A non-taken branch has no reusable output; retry follows the recorded condition route safely."""
    name = unique_name("e2e-retry-missing-branch-output")
    definition = _workflow_definition(
        name,
        [
            {"id": "condition", "name": "Condition", "type": "condition", "parameters": {"condition": "1 == 1"}},
            _script_node("taken_branch", "raise SystemExit(1)"),
            _script_node("untaken_branch", "print('must-not-run')"),
        ],
        [
            {"from": "trigger", "to": "condition"},
            {"from": "condition", "to": "taken_branch", "from_port": "true"},
            {"from": "condition", "to": "untaken_branch", "from_port": "false"},
        ],
    )
    source = _create_and_run(
        syntara_api,
        name,
        definition,
        timeout=60,
        project_id=first_project_id,
    )
    assert source.status == ExecutionStatus.FAILED
    source = _wait_for_activity_ids(syntara_api, source, {"condition", "taken_branch"})
    source_activities = _activities_by_id(source)
    assert source_activities["taken_branch"].status == "failed"

    # The unselected branch has no successful output in the source run.
    untaken_source = source_activities.get("untaken_branch")
    assert untaken_source is None or untaken_source.status == "skipped"
    if untaken_source is not None:
        assert not _activity_output(untaken_source)

    retried = _start_retry(
        syntara_api,
        source.id,
        ["taken_branch"],
        overrides={"taken_branch": {"code": "print('recovered')"}},
    )
    final = poll_execution_until_complete(syntara_api, retried.id, max_polls=60, poll_interval=1)
    assert final.status == ExecutionStatus.COMPLETED, final.error_details

    final = _wait_for_activity_ids(syntara_api, final, {"taken_branch"}, required_stdouts={"taken_branch": "recovered"})
    retry_activities = _activities_by_id(final)
    assert retry_activities["taken_branch"].status == "completed"
    untaken_retry = retry_activities.get("untaken_branch")
    assert untaken_retry is None or untaken_retry.status == "skipped"
    if untaken_retry is not None:
        assert not _activity_output(untaken_retry)


def test_retry_replays_converge_when_branch_state_matches_source(
    syntara_api: SyntaraApiRegistry,
    first_project_id: UUID,
) -> None:
    """A converge whose predecessor state is unchanged reuses its source result."""
    name = unique_name("e2e-retry-converge-replay")
    definition = _workflow_definition(
        name,
        [
            _script_node("branch_a", "print('A')"),
            _script_node("branch_b", "print('B')"),
            {"id": "join", "name": "Join", "type": "converge", "parameters": {}},
            _script_node("repair", "raise SystemExit(1)"),
        ],
        [
            {"from": "trigger", "to": "branch_a"},
            {"from": "trigger", "to": "branch_b"},
            {"from": "branch_a", "to": "join"},
            {"from": "branch_b", "to": "join"},
            {"from": "join", "to": "repair"},
        ],
    )
    source = _create_and_run(
        syntara_api,
        name,
        definition,
        timeout=60,
        project_id=first_project_id,
    )
    assert source.status == ExecutionStatus.FAILED
    source = _wait_for_activity_ids(syntara_api, source, {"branch_a", "branch_b", "join", "repair"})
    source_activities = _activities_by_id(source)
    assert source_activities["join"].status == "completed"
    assert source_activities["repair"].status == "failed"

    retried = _start_retry(
        syntara_api,
        source.id,
        ["repair"],
        overrides={"repair": {"code": "print('repaired')"}},
    )
    final = poll_execution_until_complete(syntara_api, retried.id, max_polls=60, poll_interval=1)
    assert final.status == ExecutionStatus.COMPLETED, final.error_details
    final = _wait_for_activity_ids(syntara_api, final, {"branch_a", "branch_b", "join", "repair"})
    retry_activities = _activities_by_id(final)

    assert retry_activities["join"].status == "completed"
    assert _activity_output(retry_activities["join"]) == _activity_output(source_activities["join"])
    assert _timestamp(retry_activities["join"], "started_at") == _timestamp(source_activities["join"], "started_at")
    assert _timestamp(retry_activities["join"], "completed_at") == _timestamp(source_activities["join"], "completed_at")


def test_retry_reexecutes_converge_after_repaired_branch_changes_gate_state(
    syntara_api: SyntaraApiRegistry,
    first_project_id: UUID,
) -> None:
    """Repairing a failed branch lets the downstream converge gate complete with both branches."""
    name = unique_name("e2e-retry-converge-rerun")
    definition = _workflow_definition(
        name,
        [
            _script_node("repair_branch", "raise SystemExit(1)"),
            _script_node(
                "after_repair",
                "import os; print(os.environ['VALUE'])",
                environment={"VALUE": "$" + "{repair_branch.stdout_json.value}"},
            ),
            _script_node("stable_branch", "print('stable')"),
            {"id": "join", "name": "Join", "type": "converge", "parameters": {}},
            _script_node(
                "consumer",
                "import os; print(os.environ['VALUE'])",
                environment={"VALUE": "$" + "{after_repair.stdout}"},
            ),
        ],
        [
            {"from": "trigger", "to": "repair_branch"},
            {"from": "trigger", "to": "stable_branch"},
            {"from": "repair_branch", "to": "after_repair"},
            {"from": "after_repair", "to": "join"},
            {"from": "stable_branch", "to": "join"},
            {"from": "join", "to": "consumer"},
        ],
    )
    source = _create_and_run(
        syntara_api,
        name,
        definition,
        timeout=60,
        project_id=first_project_id,
    )
    assert source.status == ExecutionStatus.FAILED
    source = _wait_for_activity_ids(
        syntara_api, source, {"repair_branch", "after_repair", "stable_branch", "join", "consumer"}
    )
    source_activities = _activities_by_id(source)
    assert source_activities["repair_branch"].status == "failed"

    retried = _start_retry(
        syntara_api,
        source.id,
        ["repair_branch"],
        overrides={"repair_branch": {"code": 'print(\'{"value": "repaired-branch"}\')'}},
    )
    final = poll_execution_until_complete(syntara_api, retried.id, max_polls=60, poll_interval=1)
    assert final.status == ExecutionStatus.COMPLETED, final.error_details
    final = _wait_for_activity_ids(
        syntara_api,
        final,
        {"repair_branch", "after_repair", "stable_branch", "join", "consumer"},
        required_stdouts={"consumer": "repaired-branch"},
    )
    retry_activities = _activities_by_id(final)

    assert retry_activities["join"].status == "completed"
    join_output = _activity_output(retry_activities["join"])
    if isinstance(join_output.get("output"), Mapping):
        join_output = dict(join_output["output"])
    assert join_output.get("completed_count") == 2
    assert "repaired-branch" in _activity_output(retry_activities["consumer"]).get("stdout", "")


def test_retry_any_converge_does_not_wait_for_an_unnecessary_slow_branch(
    syntara_api: SyntaraApiRegistry,
    first_project_id: UUID,
) -> None:
    """An n-of-m retry can proceed from a satisfied quorum without waiting for a slow branch."""
    name = unique_name("e2e-retry-any-converge-unneeded-slow-branch")
    definition = _workflow_definition(
        name,
        [
            _script_node("fast_a", "print('fast-a')"),
            _script_node("fast_b", "print('fast-b')"),
            {"id": "slow_branch", "name": "Slow branch", "type": "wait", "parameters": {"duration": 60}},
            {
                "id": "join",
                "name": "Any two of three",
                "type": "converge",
                "parameters": {"strategy": "any", "n_required": 2},
            },
            _script_node("repair", "raise SystemExit(1)"),
        ],
        [
            {"from": "trigger", "to": "fast_a"},
            {"from": "trigger", "to": "fast_b"},
            {"from": "trigger", "to": "slow_branch"},
            {"from": "fast_a", "to": "join"},
            {"from": "fast_b", "to": "join"},
            {"from": "slow_branch", "to": "join"},
            {"from": "join", "to": "repair"},
        ],
    )

    source = _create_and_run(
        syntara_api,
        name,
        definition,
        timeout=60,
        project_id=first_project_id,
    )
    assert source.status == ExecutionStatus.FAILED
    source = _wait_for_activity_ids(syntara_api, source, {"fast_a", "fast_b", "join", "repair"})
    source_activities = _activities_by_id(source)
    assert source_activities["fast_a"].status == "completed"
    assert source_activities["fast_b"].status == "completed"
    assert source_activities["join"].status == "completed"
    assert source_activities["repair"].status == "failed"
    slow_source = source_activities.get("slow_branch")
    assert slow_source is None or slow_source.status != "completed"

    retried = _start_retry(
        syntara_api,
        source.id,
        ["repair"],
        overrides={"repair": {"code": "print('repaired')"}},
    )
    final = poll_execution_until_complete(syntara_api, retried.id, max_polls=90, poll_interval=1)
    assert final.status == ExecutionStatus.COMPLETED, final.error_details

    final = _wait_for_activity_ids(syntara_api, final, {"fast_a", "fast_b", "join", "repair"})
    retry_activities = _activities_by_id(final)
    assert retry_activities["fast_a"].status == "completed"
    assert retry_activities["fast_b"].status == "completed"
    assert _activity_output(retry_activities["fast_a"]) == _activity_output(source_activities["fast_a"])
    assert _activity_output(retry_activities["fast_b"]) == _activity_output(source_activities["fast_b"])
    assert _timestamp(retry_activities["fast_a"], "started_at") == _timestamp(source_activities["fast_a"], "started_at")
    assert _timestamp(retry_activities["fast_b"], "started_at") == _timestamp(source_activities["fast_b"], "started_at")
    assert retry_activities["join"].status == "completed"
    assert retry_activities["repair"].status == "completed"
    slow_retry = retry_activities.get("slow_branch")
    assert slow_retry is None or slow_retry.status != "completed"


def test_retrying_a_quorum_branch_prevents_stale_failed_converge_restoration(
    syntara_api: SyntaraApiRegistry,
    first_project_id: UUID,
) -> None:
    """Repairing a quorum branch reruns the failed n-of-m converge instead of restoring its failure."""
    name = unique_name("e2e-retry-any-converge-repaired-quorum-branch")
    definition = _workflow_definition(
        name,
        [
            _script_node("already_successful", "print('existing-success')"),
            _script_node("repair_branch", "raise SystemExit(1)"),
            _script_node("retained_failure", "raise SystemExit(1)"),
            {
                "id": "join",
                "name": "Any two of three",
                "type": "converge",
                "parameters": {"strategy": "any", "n_required": 2},
            },
            _script_node("after_join", "print('quorum-reached')"),
        ],
        [
            {"from": "trigger", "to": "already_successful"},
            {"from": "trigger", "to": "repair_branch"},
            {"from": "trigger", "to": "retained_failure"},
            {"from": "already_successful", "to": "join"},
            {"from": "repair_branch", "to": "join"},
            {"from": "retained_failure", "to": "join"},
            {"from": "join", "to": "after_join"},
        ],
    )

    source = _create_and_run(
        syntara_api,
        name,
        definition,
        timeout=60,
        project_id=first_project_id,
    )
    assert source.status == ExecutionStatus.FAILED
    source = _wait_for_activity_ids(
        syntara_api,
        source,
        {"already_successful", "repair_branch", "retained_failure", "join"},
    )
    source_rows = _activities_by_id(source)
    assert source_rows["already_successful"].status == "completed"
    assert source_rows["repair_branch"].status == "failed"
    assert source_rows["retained_failure"].status == "failed"
    assert source_rows["join"].status == "failed"

    preview = _preview_retry(syntara_api, source.id)
    assert preview.eligible is True
    assert "repair_branch" in preview.eligible_point_ids

    retried = _start_retry(
        syntara_api,
        source.id,
        ["repair_branch"],
        overrides={"repair_branch": {"code": "print('repaired-quorum-branch')"}},
    )
    final = poll_execution_until_complete(syntara_api, retried.id, max_polls=60, poll_interval=1)
    # The unselected failure is retained, so a satisfied ANY quorum completes with errors.
    assert final.status == ExecutionStatus.COMPLETED_WITH_ERRORS, final.error_details
    final = _wait_for_activity_ids(
        syntara_api,
        final,
        {"already_successful", "repair_branch", "retained_failure", "join", "after_join"},
        required_stdouts={
            "repair_branch": "repaired-quorum-branch",
            "after_join": "quorum-reached",
        },
    )
    retry_rows = _activities_by_id(final)

    assert retry_rows["already_successful"].status == "completed"
    assert _timestamp(retry_rows["already_successful"], "started_at") == _timestamp(
        source_rows["already_successful"], "started_at"
    )
    assert retry_rows["repair_branch"].status == "completed"
    assert "repaired-quorum-branch" in _listed_stdout(retry_rows["repair_branch"])
    assert _timestamp(retry_rows["repair_branch"], "started_at") > _timestamp(
        source_rows["repair_branch"], "started_at"
    )
    # The unselected failed path remains failed, but two successful predecessors now satisfy the quorum.
    assert retry_rows["retained_failure"].status == "failed"
    assert retry_rows["retained_failure"].error_details == source_rows["retained_failure"].error_details
    assert _timestamp(retry_rows["retained_failure"], "started_at") == _timestamp(
        source_rows["retained_failure"], "started_at"
    )
    assert retry_rows["join"].status == "completed"
    # Converge controls are synchronized without an activity start timestamp;
    # completion and downstream execution prove that the stale failure was not restored.
    assert retry_rows["after_join"].status == "completed"


def test_retry_resumes_loop_at_failed_iteration_and_replays_earlier_iteration(
    syntara_api: SyntaraApiRegistry,
    first_project_id: UUID,
) -> None:
    """A selected loop-body failure resumes that occurrence without rerunning earlier work."""
    name = unique_name("e2e-retry-loop-resume")
    definition = _workflow_definition(
        name,
        [
            {
                "id": "loop",
                "name": "Loop",
                "type": "loop",
                "parameters": {"type": "for_each", "items": '["alpha", "bravo", "charlie"]'},
            },
            _script_node(
                "loop_body",
                "import os\nitem = os.environ['ITEM']\nprint(item)\nif item == 'bravo':\n    raise SystemExit(1)",
                environment={"ITEM": "$" + "{loop.item}"},
            ),
        ],
        [
            {"from": "trigger", "to": "loop"},
            {"from": "loop", "to": "loop_body", "from_port": "iterate"},
            {"from": "loop_body", "to": "loop", "to_port": "iterate"},
        ],
    )
    source = _create_and_run(
        syntara_api,
        name,
        definition,
        timeout=90,
        project_id=first_project_id,
    )
    assert source.status == ExecutionStatus.FAILED
    source_rows = _wait_for_activity_executions(syntara_api, source.id, {"loop_body_iter_0", "loop_body_iter_1"})
    source_alpha = source_rows["loop_body_iter_0"]
    source_bravo = source_rows["loop_body_iter_1"]
    assert _activity_status(source_alpha) == "completed"
    assert _activity_status(source_bravo) == "failed"
    assert _activity_input(source_alpha).get("environment") == {"ITEM": "alpha"}
    assert _listed_stdout(source_alpha) == "alpha"
    assert _activity_input(source_bravo).get("environment") == {"ITEM": "bravo"}

    preview = _preview_retry(syntara_api, source.id)
    assert preview.eligible is True
    assert "loop_body" in preview.eligible_point_ids

    retried = _start_retry(
        syntara_api,
        source.id,
        ["loop_body"],
        overrides={"loop_body": {"code": "import os; print(os.environ['ITEM'])"}},
    )
    final = poll_execution_until_complete(syntara_api, retried.id, max_polls=90, poll_interval=1)
    assert final.status == ExecutionStatus.COMPLETED, final.error_details
    final = _wait_for_activity_ids(
        syntara_api,
        final,
        {"loop_body", "loop_body#iter-1", "loop_body#iter-2"},
        required_stdouts={"loop_body#iter-1": "bravo", "loop_body#iter-2": "charlie"},
    )
    retry_rows = _activity_executions_by(syntara_api, final.id, lambda activity: activity.temporal_activity_id)
    retry_alpha = retry_rows["loop_body_iter_0"]
    retry_bravo = retry_rows["loop_body_iter_1"]
    retry_charlie = retry_rows["loop_body_iter_2"]

    # The first iteration is restored with its resolved input, output, and original timestamps.
    assert _activity_status(retry_alpha) == "completed"
    assert _activity_input(retry_alpha) == _activity_input(source_alpha)
    assert _activity_output(retry_alpha) == _activity_output(source_alpha)
    assert _timestamp(retry_alpha, "started_at") == _timestamp(source_alpha, "started_at")
    assert _timestamp(retry_alpha, "completed_at") == _timestamp(source_alpha, "completed_at")
    # The failed occurrence reruns with the override, then iteration 2 proceeds.
    assert _activity_status(retry_bravo) == "completed"
    assert _activity_input(retry_bravo).get("environment") == _activity_input(source_bravo).get("environment")
    assert _timestamp(retry_bravo, "started_at") > _timestamp(source_bravo, "started_at")
    assert _activity_status(retry_charlie) == "completed"


def test_retry_replays_nested_loop_iterations_and_control_node_routes(
    syntara_api: SyntaraApiRegistry,
    first_project_id: UUID,
) -> None:
    """A nested-loop retry restores prior routes and resumes the selected body occurrence."""
    name = unique_name("e2e-retry-nested-loop-control-route")
    definition = _workflow_definition(
        name,
        [
            {
                "id": "outer_loop",
                "name": "Outer loop",
                "type": "loop",
                "parameters": {
                    "type": "for_each",
                    "items": '[["safe:first", "safe:second"], ["fail:first", "fail:second"]]',
                },
            },
            {
                "id": "inner_loop",
                "name": "Inner loop",
                "type": "loop",
                "parameters": {"type": "for_each", "items": "${loop.item}"},
            },
            {
                "id": "route",
                "name": "Route to the selected failure",
                "type": "condition",
                "parameters": {"condition": "${loop.item} == 'fail:second'"},
            },
            _script_node(
                "repair_body",
                "import os; print(f\"repair:{os.environ['ITEM']}\"); raise SystemExit(1)",
                environment={"ITEM": "${loop.item}"},
            ),
            _script_node(
                "alternate_body",
                "import os; print(f\"alternate:{os.environ['ITEM']}\")",
                environment={"ITEM": "${loop.item}"},
            ),
            _script_node("finished", "print('nested-loop-finished')"),
        ],
        [
            {"from": "trigger", "to": "outer_loop"},
            {"from": "outer_loop", "to": "inner_loop", "from_port": "iterate"},
            {"from": "inner_loop", "to": "route", "from_port": "iterate"},
            {"from": "route", "to": "repair_body", "from_port": "true"},
            {"from": "route", "to": "alternate_body", "from_port": "false"},
            {"from": "repair_body", "to": "inner_loop", "to_port": "iterate"},
            {"from": "alternate_body", "to": "inner_loop", "to_port": "iterate"},
            {"from": "inner_loop", "to": "outer_loop", "from_port": "complete", "to_port": "iterate"},
            {"from": "outer_loop", "to": "finished", "from_port": "complete"},
        ],
    )

    source = _create_and_run(
        syntara_api,
        name,
        definition,
        timeout=90,
        project_id=first_project_id,
    )
    assert source.status == ExecutionStatus.FAILED, [
        (activity.activity_id, activity.status, activity.error_details, _activity_output(activity))
        for activity in source.activities or []
    ]
    source_rows = _wait_for_activity_executions(
        syntara_api,
        source.id,
        {
            "route_iter_0_iter_0",
            "alternate_body_iter_0_iter_0",
            "route_iter_0_iter_1",
            "alternate_body_iter_0_iter_1",
            "route_iter_1_iter_0",
            "alternate_body_iter_1_iter_0",
            "route_iter_1_iter_1",
            "repair_body_iter_1_iter_1",
        },
        required_stdouts={
            "alternate_body_iter_0_iter_0": "alternate:safe:first",
            "alternate_body_iter_0_iter_1": "alternate:safe:second",
            "alternate_body_iter_1_iter_0": "alternate:fail:first",
        },
    )
    for temporal_id in (
        "route_iter_0_iter_0",
        "route_iter_0_iter_1",
        "route_iter_1_iter_0",
    ):
        assert _activity_output(source_rows[temporal_id]).get("evaluated_result") is False
    assert source_rows["alternate_body_iter_0_iter_0"].status == "completed"
    assert source_rows["alternate_body_iter_0_iter_1"].status == "completed"
    assert source_rows["alternate_body_iter_1_iter_0"].status == "completed"
    assert _activity_output(source_rows["route_iter_1_iter_1"]).get("evaluated_result") is True
    assert _activity_status(source_rows["repair_body_iter_1_iter_1"]) == "failed"
    assert _activity_input(source_rows["repair_body_iter_1_iter_1"]).get("environment") == {"ITEM": "fail:second"}

    preview = _preview_retry(syntara_api, source.id)
    assert preview.eligible is True
    assert "repair_body" in preview.eligible_point_ids

    retried = _start_retry(
        syntara_api,
        source.id,
        ["repair_body"],
        overrides={"repair_body": {"code": "import os; print(f\"recovered:{os.environ['ITEM']}\")"}},
    )
    final = poll_execution_until_complete(syntara_api, retried.id, max_polls=90, poll_interval=1)
    assert final.status == ExecutionStatus.COMPLETED, final.error_details
    retry_rows = _wait_for_activity_executions(
        syntara_api,
        final.id,
        {
            "route_iter_0_iter_0",
            "alternate_body_iter_0_iter_0",
            "route_iter_0_iter_1",
            "alternate_body_iter_0_iter_1",
            "route_iter_1_iter_0",
            "alternate_body_iter_1_iter_0",
            "route_iter_1_iter_1",
            "repair_body_iter_1_iter_1",
            "finished",
        },
        required_stdouts={
            "alternate_body_iter_0_iter_0": "alternate:safe:first",
            "alternate_body_iter_0_iter_1": "alternate:safe:second",
            "alternate_body_iter_1_iter_0": "alternate:fail:first",
            "repair_body_iter_1_iter_1": "recovered:fail:second",
            "finished": "nested-loop-finished",
        },
    )

    # Earlier outer and inner occurrences, including their control routes, retain source results.
    for temporal_id in (
        "route_iter_0_iter_0",
        "alternate_body_iter_0_iter_0",
        "route_iter_0_iter_1",
        "alternate_body_iter_0_iter_1",
        "route_iter_1_iter_0",
        "alternate_body_iter_1_iter_0",
    ):
        assert retry_rows[temporal_id].status == source_rows[temporal_id].status
        assert _activity_output(retry_rows[temporal_id]) == _activity_output(source_rows[temporal_id])
        assert _timestamp(retry_rows[temporal_id], "started_at") == _timestamp(source_rows[temporal_id], "started_at")
        assert _timestamp(retry_rows[temporal_id], "completed_at") == _timestamp(
            source_rows[temporal_id], "completed_at"
        )

    repaired = retry_rows["repair_body_iter_1_iter_1"]
    assert repaired.status == "completed"
    assert _activity_input(repaired).get("environment") == _activity_input(
        source_rows["repair_body_iter_1_iter_1"]
    ).get("environment")
    assert _timestamp(repaired, "started_at") > _timestamp(source_rows["repair_body_iter_1_iter_1"], "started_at")
    assert _activity_output(retry_rows["route_iter_1_iter_1"]).get("evaluated_result") is True
    assert retry_rows["finished"].status == "completed"


def test_retry_defaults_to_all_failed_parallel_branches_when_selection_is_omitted(
    syntara_api: SyntaraApiRegistry,
    first_project_id: UUID,
) -> None:
    """Omitting retry_point_ids retries every currently failed branch."""
    source, source_activities = _create_failed_parallel_source(
        syntara_api,
        first_project_id,
        name_prefix="e2e-retry-parallel-default-selection",
    )

    # Omit retry_point_ids entirely to exercise the API's default selection behavior.
    retried = _start_retry(
        syntara_api,
        source.id,
        overrides={
            "failure_a": {"code": "print('fixed-a')"},
            "failure_b": {"code": "print('fixed-b')"},
        },
    )
    final = poll_execution_until_complete(syntara_api, retried.id, max_polls=90, poll_interval=1)
    assert final.status == ExecutionStatus.COMPLETED, final.error_details
    retry_rows = _wait_for_activity_executions(
        syntara_api,
        final.id,
        {"failure_a", "failure_b", "after_a", "after_b"},
        required_stdouts={"failure_a": "fixed-a"},
    )
    for node_id, code in (("failure_a", "print('fixed-a')"), ("failure_b", "print('fixed-b')")):
        assert _activity_status(retry_rows[node_id]) == "completed"
        assert _activity_input(retry_rows[node_id]).get("code") == code
        assert _timestamp(retry_rows[node_id], "started_at") > _timestamp(source_activities[node_id], "started_at")
    assert _activity_status(retry_rows["after_a"]) == "completed"
    assert _activity_status(retry_rows["after_b"]) == "completed"


def test_retry_can_select_a_subset_of_parallel_failed_branches(
    syntara_api: SyntaraApiRegistry,
    first_project_id: UUID,
) -> None:
    """A selected failure and its downstream work rerun while the other failure is retained."""
    source, source_activities = _create_failed_parallel_source(
        syntara_api,
        first_project_id,
        name_prefix="e2e-retry-parallel-subset-selection",
    )

    retried = _start_retry(
        syntara_api,
        source.id,
        ["failure_a"],
        overrides={"failure_a": {"code": "print('fixed-a')"}},
    )
    final = poll_execution_until_complete(syntara_api, retried.id, max_polls=60, poll_interval=1)
    assert final.status == ExecutionStatus.FAILED
    final = _wait_for_activity_ids(
        syntara_api,
        final,
        {"failure_a", "after_a", "failure_b"},
        required_stdouts={"failure_a": "fixed-a", "after_a": "after-a"},
    )
    retry_activities = _activities_by_id(final)
    assert retry_activities["failure_a"].status == "completed"
    assert retry_activities["after_a"].status == "completed"
    assert _activity_output(retry_activities["after_a"]).get("stdout", "").strip() == "after-a"
    assert retry_activities["failure_b"].status == "failed"
    assert _timestamp(retry_activities["failure_b"], "started_at") == _timestamp(
        source_activities["failure_b"], "started_at"
    )
    after_b = retry_activities.get("after_b")
    assert after_b is None or after_b.status == "skipped"


def test_retry_accepts_multiple_selected_parallel_failure_points(
    syntara_api: SyntaraApiRegistry,
    first_project_id: UUID,
) -> None:
    """Explicitly selecting multiple eligible failures reruns both parallel paths."""
    source, source_activities = _create_failed_parallel_source(
        syntara_api,
        first_project_id,
        name_prefix="e2e-retry-parallel-multiple-selection",
    )

    retried = _start_retry(
        syntara_api,
        source.id,
        ["failure_b", "failure_a"],
        overrides={
            "failure_a": {"code": "print('fixed-a')"},
            "failure_b": {"code": "print('fixed-b')"},
        },
    )
    final = poll_execution_until_complete(syntara_api, retried.id, max_polls=60, poll_interval=1)
    assert final.status == ExecutionStatus.COMPLETED, final.error_details
    retry_rows = _wait_for_activity_executions(
        syntara_api,
        final.id,
        {"failure_a", "failure_b", "after_a", "after_b"},
        required_stdouts={"failure_a": "fixed-a", "failure_b": "fixed-b"},
    )
    for node_id, code in (("failure_a", "print('fixed-a')"), ("failure_b", "print('fixed-b')")):
        assert _activity_status(retry_rows[node_id]) == "completed"
        assert _activity_input(retry_rows[node_id]).get("code") == code
        assert _timestamp(retry_rows[node_id], "started_at") > _timestamp(source_activities[node_id], "started_at")
    assert _activity_status(retry_rows["after_a"]) == "completed"
    assert _activity_status(retry_rows["after_b"]) == "completed"


def test_retry_input_overrides_are_run_local_and_reject_unknown_keys(
    syntara_api: SyntaraApiRegistry,
    syntara_base_url: str,
    create_project: ProjectFactory,
    create_user: UserFactory,
    create_project_role: ProjectRoleFactory,
    assign_project_role_to_user: AssignProjectRoleFactory,
) -> None:
    """Only workflow editors can override retry inputs; retries never change the definition."""
    project_id, _ = create_project(syntara_api, "retry-override-authz")
    name = unique_name("e2e-retry-override-authz")
    definition = _workflow_definition(
        name,
        [_script_node("failure", "raise SystemExit(1)")],
        [{"from": "trigger", "to": "failure"}],
    )
    source = _create_and_run(
        syntara_api,
        name,
        definition,
        timeout=60,
        project_id=project_id,
    )
    assert source.status == ExecutionStatus.FAILED
    source = _wait_for_activity_ids(syntara_api, source, {"failure"})

    run_user_id, run_username, run_password = create_user(syntara_api, "retry-run-user")
    run_role = create_project_role(syntara_api, project_id, "retry-run-user", _RETRY_RUN_POLICIES)
    assign_project_role_to_user(syntara_api, project_id, run_user_id, run_role)
    run_api = api_for(syntara_base_url, run_username, run_password)

    rejected_override = run_api.executions.retry_from_failure(
        execution_id=source.id,
        body=RetryFailureRequest.from_dict(
            {
                "retry_point_ids": ["failure"],
                "input_parameter_overrides": {"failure": {"code": "print('run-only user cannot override')"}},
            }
        ),
    )
    if rejected_override.status_code in _TRANSIENT_GATEWAY_STATUSES:
        pytest.skip("Backend returned 502 Bad Gateway — transient infrastructure issue")
    assert rejected_override.status_code == HTTPStatus.FORBIDDEN

    # AC-14 only gates changing inputs. A user with run permission can retry unchanged inputs.
    unchanged_retry = _start_retry(run_api, source.id, ["failure"])
    unchanged_retry_final = poll_execution_until_complete(
        syntara_api, unchanged_retry.id, max_polls=60, poll_interval=1
    )
    assert unchanged_retry_final.status == ExecutionStatus.FAILED

    editor_policies = [*_RETRY_RUN_POLICIES, "workflow:update:project"]
    editor_user_id, editor_username, editor_password = create_user(syntara_api, "retry-workflow-editor")
    editor_role = create_project_role(syntara_api, project_id, "retry-workflow-editor", editor_policies)
    assign_project_role_to_user(syntara_api, project_id, editor_user_id, editor_role)
    editor_api = api_for(syntara_base_url, editor_username, editor_password)

    rejected_new_input_key = editor_api.executions.retry_from_failure(
        execution_id=source.id,
        body=RetryFailureRequest.from_dict(
            {
                "retry_point_ids": ["failure"],
                "input_parameter_overrides": {"failure": {"new_parameter": "not allowed"}},
            }
        ),
    )
    if rejected_new_input_key.status_code in _TRANSIENT_GATEWAY_STATUSES:
        pytest.skip("Backend returned 502 Bad Gateway — transient infrastructure issue")
    assert rejected_new_input_key.status_code == HTTPStatus.CONFLICT
    assert getattr(rejected_new_input_key.parsed, "code", None) == "EXECUTION_NOT_RETRYABLE_FROM_FAILURE"

    editor_retry = _start_retry(
        editor_api,
        source.id,
        ["failure"],
        overrides={"failure": {"code": "print('repaired')"}},
    )
    assert editor_retry.retried_from_execution_id == source.id
    assert editor_retry.workflow_version_id == source.workflow_version_id
    editor_retry_final = poll_execution_until_complete(syntara_api, editor_retry.id, max_polls=90, poll_interval=1)
    assert editor_retry_final.status == ExecutionStatus.COMPLETED, editor_retry_final.error_details
    editor_retry_final = _wait_for_activity_ids(
        syntara_api, editor_retry_final, {"failure"}, required_stdouts={"failure": "repaired"}
    )

    # The override belongs only to the retry; a later standard run still executes the failing definition.
    try:
        later_run = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=source.workflow_id, trigger_node_id="trigger")
        ).assert_and_get()
    except UnexpectedResponseException as exc:
        _skip_transient_gateway(exc)
        raise
    later_run_final = poll_execution_until_complete(syntara_api, later_run.id, max_polls=60, poll_interval=1)
    assert later_run_final.status == ExecutionStatus.FAILED
