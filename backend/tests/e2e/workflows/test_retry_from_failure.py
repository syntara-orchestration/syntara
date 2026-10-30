"""Backend E2E coverage for retry-from-failure replay and output injection.

These tests use the generated API client against the live API and Temporal worker.
They assert observable execution state and outputs rather than workflow-engine internals.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from datetime import UTC, datetime
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import pytest
from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.auth import api_for
from orchestrator_test_sdk.e2e.helpers import create_and_run_workflow, poll_execution_until_complete
from syntara_api_client.models import ExecutionCreate, RetryFailureRequest
from syntara_api_client.models.execution_status import ExecutionStatus
from syntara_api_client.types import Unset

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


def _activity_output(activity: ActivityData) -> dict[str, Any]:
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


def _activity_executions_by_name(
    syntara_api: SyntaraApiRegistry,
    execution_id: UUID,
) -> dict[str, ActivityExecution]:
    executions = syntara_api.executions.list_activities(execution_id=execution_id, limit=100).assert_and_get()
    return {activity.activity_name: activity for activity in executions.resources}


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
    max_polls: int = 30,
    poll_interval: int = 1,
) -> ExecutionRead:
    """Wait until include=activities has every expected row.

    Loop iterations are written as later composite keys (``loop_body#iter-1``).
    The execution can already be terminal before those rows have been synced.
    """
    for _ in range(max_polls):
        activities = execution.activities
        present = {activity.activity_id for activity in activities} if isinstance(activities, list) else set()
        if required_ids <= present:
            return execution
        time.sleep(poll_interval)
        execution = syntara_api.executions.get(execution_id=execution.id, include="activities").assert_and_get()
    activities = execution.activities
    present = {activity.activity_id for activity in activities} if isinstance(activities, list) else set()
    missing = sorted(required_ids - present)
    msg = f"Execution {execution.id} is missing activity rows: {missing}"
    raise AssertionError(msg)


def _listed_stdout(activity: ActivityExecution) -> str:
    value = activity.output_data
    if value is None or isinstance(value, Unset):
        return ""
    if isinstance(value, Mapping):
        data = dict(value)
    else:
        extra = getattr(value, "additional_properties", None)
        data = dict(extra) if isinstance(extra, Mapping) else {}
    return str(data.get("stdout", "")).strip()


def _loop_body_rows(syntara_api: SyntaraApiRegistry, execution_id: UUID) -> dict[str, ActivityExecution]:
    return {
        name: activity
        for name, activity in _activity_executions_by_name(syntara_api, execution_id).items()
        if name == "loop_body" or name.startswith("loop_body#iter-")
    }


def _wait_for_loop_stdouts(
    syntara_api: SyntaraApiRegistry,
    execution_id: UUID,
    required_stdouts: set[str],
    *,
    max_polls: int = 30,
    poll_interval: int = 1,
) -> dict[str, ActivityExecution]:
    """Wait until listed loop-body rows include every expected stdout value."""
    rows: dict[str, ActivityExecution] = {}
    for _ in range(max_polls):
        rows = _loop_body_rows(syntara_api, execution_id)
        present = {_listed_stdout(activity) for activity in rows.values()}
        if required_stdouts <= present:
            return rows
        time.sleep(poll_interval)
    present = sorted({_listed_stdout(activity) for activity in rows.values()})
    msg = (
        f"Execution {execution_id} loop body rows {sorted(rows)} have stdout {present}, "
        f"wanted {sorted(required_stdouts)}"
    )
    raise AssertionError(msg)


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
    response = syntara_api.executions.retry_from_failure(
        execution_id=execution_id,
        body=RetryFailureRequest.from_dict(request),
    )
    assert response.status_code == HTTPStatus.CREATED
    return response.assert_and_get()


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

    source = create_and_run_workflow(
        syntara_api,
        name,
        definition,
        timeout=60,
        project_id=first_project_id,
    )
    assert source.status == ExecutionStatus.FAILED
    source_activities = _activities_by_id(source)
    assert source_activities["producer"].status == "completed"
    assert source_activities["repair"].status == "failed"
    source_activity_executions = _activity_executions_by_name(syntara_api, source.id)
    assert _activity_input(source_activity_executions["repair"]).get("environment") == {"MESSAGE": "from-source"}

    preview = syntara_api.executions.retry_from_failure_preview(execution_id=source.id).assert_and_get()
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

    final = poll_execution_until_complete(syntara_api, retried.id, max_polls=60, poll_interval=1)
    assert final.status == ExecutionStatus.COMPLETED, final.error_details
    retry_activities = _activities_by_id(final)
    retry_activity_executions = _activity_executions_by_name(syntara_api, final.id)
    assert _activity_input(retry_activity_executions["repair"]).get("environment") == {"MESSAGE": "retry-only"}

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
    ordinary_run = syntara_api.executions.create(
        body=ExecutionCreate(workflow_id=source.workflow_id, trigger_node_id="trigger")
    ).assert_and_get()
    ordinary_final = poll_execution_until_complete(
        syntara_api,
        ordinary_run.id,
        max_polls=60,
        poll_interval=1,
    )
    assert ordinary_final.status == ExecutionStatus.FAILED
    ordinary_activity_executions = _activity_executions_by_name(syntara_api, ordinary_run.id)
    assert _activity_input(ordinary_activity_executions["repair"]).get("environment") == {"MESSAGE": "from-source"}


def test_completed_execution_is_not_eligible_for_retry_from_failure(
    syntara_api: SyntaraApiRegistry,
    first_project_id: UUID,
) -> None:
    name = unique_name("e2e-retry-not-eligible")
    source = create_and_run_workflow(
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

    preview = syntara_api.executions.retry_from_failure_preview(execution_id=source.id).assert_and_get()
    assert preview.eligible is False
    assert preview.reason

    response = syntara_api.executions.retry_from_failure(
        execution_id=source.id,
        body=RetryFailureRequest.from_dict({"retry_point_ids": []}),
    )
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
    source = create_and_run_workflow(
        syntara_api,
        name,
        definition,
        timeout=60,
        project_id=first_project_id,
    )
    assert source.status == ExecutionStatus.FAILED
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
    source = create_and_run_workflow(
        syntara_api,
        name,
        definition,
        timeout=60,
        project_id=first_project_id,
    )
    assert source.status == ExecutionStatus.FAILED
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
    source = create_and_run_workflow(
        syntara_api,
        name,
        definition,
        timeout=60,
        project_id=first_project_id,
    )
    assert source.status == ExecutionStatus.FAILED
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
    retry_activities = _activities_by_id(final)

    assert retry_activities["join"].status == "completed"
    join_output = _activity_output(retry_activities["join"])
    if isinstance(join_output.get("output"), Mapping):
        join_output = dict(join_output["output"])
    assert join_output.get("completed_count") == 2
    assert "repaired-branch" in _activity_output(retry_activities["consumer"]).get("stdout", "")


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
                "import os, sys\nitem = os.environ['ITEM']\nprint(item)\nif item == 'bravo':\n    raise SystemExit(1)",
                environment={"ITEM": "$" + "{loop.item}"},
            ),
        ],
        [
            {"from": "trigger", "to": "loop"},
            {"from": "loop", "to": "loop_body", "from_port": "iterate"},
            {"from": "loop_body", "to": "loop", "to_port": "iterate"},
        ],
    )
    source = create_and_run_workflow(
        syntara_api,
        name,
        definition,
        timeout=60,
        project_id=first_project_id,
    )
    assert source.status == ExecutionStatus.FAILED
    source_rows = _wait_for_loop_stdouts(syntara_api, source.id, {"alpha", "bravo"})
    source_by_stdout = {_listed_stdout(activity): activity for activity in source_rows.values()}
    assert getattr(source_by_stdout["alpha"].status, "value", source_by_stdout["alpha"].status) == "completed"
    assert getattr(source_by_stdout["bravo"].status, "value", source_by_stdout["bravo"].status) == "failed"

    preview = syntara_api.executions.retry_from_failure_preview(execution_id=source.id).assert_and_get()
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
    retry_rows = _wait_for_loop_stdouts(syntara_api, final.id, {"alpha", "bravo", "charlie"})
    retry_by_stdout = {_listed_stdout(activity): activity for activity in retry_rows.values()}

    # The first iteration is replayed from the source with its original output and times.
    assert getattr(retry_by_stdout["alpha"].status, "value", retry_by_stdout["alpha"].status) == "completed"
    assert _listed_stdout(retry_by_stdout["alpha"]) == _listed_stdout(source_by_stdout["alpha"])
    assert _timestamp(retry_by_stdout["alpha"], "started_at") == _timestamp(source_by_stdout["alpha"], "started_at")
    # The failed iteration is repaired, and the final item runs after the resume point.
    assert getattr(retry_by_stdout["bravo"].status, "value", retry_by_stdout["bravo"].status) == "completed"
    assert getattr(retry_by_stdout["charlie"].status, "value", retry_by_stdout["charlie"].status) == "completed"


def test_retry_defaults_to_all_failed_parallel_branches_when_selection_is_omitted(
    syntara_api: SyntaraApiRegistry,
    first_project_id: UUID,
) -> None:
    """An empty retry_point_ids list retries every currently failed branch."""
    name = unique_name("e2e-retry-parallel-default-selection")
    source = create_and_run_workflow(
        syntara_api,
        name,
        _parallel_failure_definition(name),
        timeout=60,
        project_id=first_project_id,
    )
    assert source.status == ExecutionStatus.FAILED
    source = _wait_for_activity_ids(syntara_api, source, {"failure_a", "failure_b"})
    source_activities = _activities_by_id(source)
    assert source_activities["failure_a"].status == "failed"
    assert source_activities["failure_b"].status == "failed"

    preview = syntara_api.executions.retry_from_failure_preview(execution_id=source.id).assert_and_get()
    assert preview.eligible is True
    assert set(preview.eligible_point_ids) == {"failure_a", "failure_b"}

    # Empty retry_point_ids is the documented default: retry every currently failed point.
    retried = _start_retry(
        syntara_api,
        source.id,
        [],
        overrides={
            "failure_a": {"code": "print('fixed-a')"},
            "failure_b": {"code": "print('fixed-b')"},
        },
    )
    final = poll_execution_until_complete(syntara_api, retried.id, max_polls=90, poll_interval=1)
    assert final.status == ExecutionStatus.COMPLETED, final.error_details
    final = _wait_for_activity_ids(syntara_api, final, {"failure_a", "failure_b", "after_a", "after_b"})
    retry_activities = _activities_by_id(final)
    assert retry_activities["failure_a"].status == "completed"
    assert retry_activities["failure_b"].status == "completed"
    assert "fixed-a" in _activity_output(retry_activities["failure_a"]).get("stdout", "")
    assert "fixed-b" in _activity_output(retry_activities["failure_b"]).get("stdout", "")
    assert "after-a" in _activity_output(retry_activities["after_a"]).get("stdout", "")
    assert "after-b" in _activity_output(retry_activities["after_b"]).get("stdout", "")


def test_retry_can_select_a_subset_of_parallel_failed_branches(
    syntara_api: SyntaraApiRegistry,
    first_project_id: UUID,
) -> None:
    """A selected failure and its downstream work rerun while the other failure is retained."""
    name = unique_name("e2e-retry-parallel-subset-selection")
    source = create_and_run_workflow(
        syntara_api,
        name,
        _parallel_failure_definition(name),
        timeout=60,
        project_id=first_project_id,
    )
    assert source.status == ExecutionStatus.FAILED
    source_activities = _activities_by_id(source)
    assert source_activities["failure_a"].status == "failed"
    assert source_activities["failure_b"].status == "failed"

    preview = syntara_api.executions.retry_from_failure_preview(execution_id=source.id).assert_and_get()
    assert preview.eligible is True
    assert preview.eligible_point_ids == ["failure_a", "failure_b"]

    retried = _start_retry(
        syntara_api,
        source.id,
        ["failure_a"],
        overrides={"failure_a": {"code": "print('fixed-a')"}},
    )
    final = poll_execution_until_complete(syntara_api, retried.id, max_polls=60, poll_interval=1)
    assert final.status == ExecutionStatus.FAILED
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
    name = unique_name("e2e-retry-parallel-multiple-selection")
    source = create_and_run_workflow(
        syntara_api,
        name,
        _parallel_failure_definition(name),
        timeout=60,
        project_id=first_project_id,
    )
    assert source.status == ExecutionStatus.FAILED
    source_activities = _activities_by_id(source)
    assert source_activities["failure_a"].status == "failed"
    assert source_activities["failure_b"].status == "failed"

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
    retry_activities = _activities_by_id(final)
    assert retry_activities["failure_a"].status == "completed"
    assert retry_activities["failure_b"].status == "completed"
    assert retry_activities["after_a"].status == "completed"
    assert retry_activities["after_b"].status == "completed"


def test_retry_input_overrides_are_run_local_and_reject_unknown_keys(
    syntara_api: SyntaraApiRegistry,
    syntara_base_url: str,
    create_project: ProjectFactory,
    create_user: UserFactory,
    create_project_role: ProjectRoleFactory,
    assign_project_role_to_user: AssignProjectRoleFactory,
) -> None:
    """Run permission is enough for overrides; unknown keys are rejected; the definition stays unchanged."""
    project_id, _ = create_project(syntara_api, "retry-override-authz")
    name = unique_name("e2e-retry-override-authz")
    definition = _workflow_definition(
        name,
        [_script_node("failure", "raise SystemExit(1)")],
        [{"from": "trigger", "to": "failure"}],
    )
    source = create_and_run_workflow(
        syntara_api,
        name,
        definition,
        timeout=60,
        project_id=project_id,
    )
    assert source.status == ExecutionStatus.FAILED

    run_user_id, run_username, run_password = create_user(syntara_api, "retry-run-user")
    run_role = create_project_role(syntara_api, project_id, "retry-run-user", _RETRY_RUN_POLICIES)
    assign_project_role_to_user(syntara_api, project_id, run_user_id, run_role)
    run_api = api_for(syntara_base_url, run_username, run_password)

    rejected_new_input_key = run_api.executions.retry_from_failure(
        execution_id=source.id,
        body=RetryFailureRequest.from_dict(
            {
                "retry_point_ids": ["failure"],
                "input_parameter_overrides": {"failure": {"new_parameter": "not allowed"}},
            }
        ),
    )
    assert rejected_new_input_key.status_code == HTTPStatus.CONFLICT
    assert getattr(rejected_new_input_key.parsed, "code", None) == "EXECUTION_NOT_RETRYABLE_FROM_FAILURE"

    authorized_retry = _start_retry(
        run_api,
        source.id,
        ["failure"],
        overrides={"failure": {"code": "print('repaired')"}},
    )
    assert authorized_retry.retried_from_execution_id == source.id
    assert authorized_retry.workflow_version_id == source.workflow_version_id
    authorized_retry_final = poll_execution_until_complete(
        syntara_api, authorized_retry.id, max_polls=60, poll_interval=1
    )
    assert authorized_retry_final.status == ExecutionStatus.COMPLETED, authorized_retry_final.error_details

    # The override belongs only to the retry; a later standard run still executes the failing definition.
    later_run = syntara_api.executions.create(
        body=ExecutionCreate(workflow_id=source.workflow_id, trigger_node_id="trigger")
    ).assert_and_get()
    later_run_final = poll_execution_until_complete(syntara_api, later_run.id, max_polls=60, poll_interval=1)
    assert later_run_final.status == ExecutionStatus.FAILED
