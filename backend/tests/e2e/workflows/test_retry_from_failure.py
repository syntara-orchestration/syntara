"""Backend E2E coverage for retry-from-failure replay and output injection (AAP-99052).

These tests use the generated API client against the live API and Temporal worker.
They assert observable execution state and outputs rather than workflow-engine internals.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import pytest
from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.auth import api_for
from orchestrator_test_sdk.e2e.helpers import create_and_run_workflow, poll_execution_until_complete
from syntara_api_client.models import ExecutionCreate, RetryFailureRequest
from syntara_api_client.models.execution_status import ExecutionStatus

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

pytestmark = [pytest.mark.e2e]


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


def _timestamp(activity: ActivityData, field: str) -> datetime:
    value = getattr(activity, field)
    assert isinstance(value, datetime), f"{activity.activity_id}.{field} must be a timestamp"
    return value


def _start_retry(
    syntara_api: SyntaraApiRegistry,
    execution_id: UUID,
    retry_point_id: str,
    *,
    overrides: dict[str, dict[str, Any]] | None = None,
) -> ExecutionRead:
    request: dict[str, Any] = {"retry_point_ids": [retry_point_id]}
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
            _script_node("repair", "raise SystemExit(1)"),
            _script_node(
                "consumer",
                "import os; print(os.environ['MESSAGE'])",
                environment={"MESSAGE": "$" + "{producer.stdout_json.marker}"},
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

    preview = syntara_api.executions.retry_from_failure_preview(execution_id=source.id).assert_and_get()
    assert preview.eligible is True
    assert preview.eligible_point_ids == ["repair"]

    retried = _start_retry(
        syntara_api,
        source.id,
        "repair",
        overrides={"repair": {"code": "print('repaired')"}},
    )
    assert retried.retried_from_execution_id == source.id
    assert retried.workflow_version_id == source.workflow_version_id

    final = poll_execution_until_complete(syntara_api, retried.id, max_polls=60, poll_interval=1)
    assert final.status == ExecutionStatus.COMPLETED, final.error_details
    retry_activities = _activities_by_id(final)

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
    assert "from-source" in _activity_output(retry_activities["consumer"]).get("stdout", "")

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
        "taken_branch",
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
        "repair",
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
        "repair_branch",
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
    source_activities = _activities_by_id(source)
    assert source_activities["loop_body"].status == "completed"
    assert _activity_output(source_activities["loop_body"]).get("stdout", "").strip() == "alpha"
    assert source_activities["loop_body#iter-1"].status == "failed"

    preview = syntara_api.executions.retry_from_failure_preview(execution_id=source.id).assert_and_get()
    assert preview.eligible is True
    assert "loop_body" in preview.eligible_point_ids

    retried = _start_retry(
        syntara_api,
        source.id,
        "loop_body",
        overrides={"loop_body": {"code": "import os; print(os.environ['ITEM'])"}},
    )
    final = poll_execution_until_complete(syntara_api, retried.id, max_polls=60, poll_interval=1)
    assert final.status == ExecutionStatus.COMPLETED, final.error_details

    retry_activities = _activities_by_id(final)
    # The first iteration is replayed from the source with its original output and times.
    assert retry_activities["loop_body"].status == "completed"
    assert _activity_output(retry_activities["loop_body"]) == _activity_output(source_activities["loop_body"])
    assert _timestamp(retry_activities["loop_body"], "started_at") == _timestamp(
        source_activities["loop_body"], "started_at"
    )
    # The failed iteration is repaired, and the final item runs after the resume point.
    assert retry_activities["loop_body#iter-1"].status == "completed"
    assert _activity_output(retry_activities["loop_body#iter-1"]).get("stdout", "").strip() == "bravo"
    assert retry_activities["loop_body#iter-2"].status == "completed"
    assert _activity_output(retry_activities["loop_body#iter-2"]).get("stdout", "").strip() == "charlie"


def test_retry_input_overrides_require_workflow_update_permission(
    syntara_api: SyntaraApiRegistry,
    syntara_base_url: str,
    create_project: ProjectFactory,
    create_user: UserFactory,
    create_project_role: ProjectRoleFactory,
    assign_project_role_to_user: AssignProjectRoleFactory,
) -> None:
    """A run-only user may retry normally but needs workflow edit permission for overrides."""
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

    run_only_user_id, run_only_username, run_only_password = create_user(syntara_api, "retry-run-only")
    run_only_role = create_project_role(syntara_api, project_id, "retry-run-only", ["execution:run:project"])
    assign_project_role_to_user(syntara_api, project_id, run_only_user_id, run_only_role)
    run_only_api = api_for(syntara_base_url, run_only_username, run_only_password)

    denied_override = run_only_api.executions.retry_from_failure(
        execution_id=source.id,
        body=RetryFailureRequest.from_dict(
            {
                "retry_point_ids": ["failure"],
                "input_parameter_overrides": {"failure": {"code": "print('not authorized')"}},
            }
        ),
    )
    assert denied_override.status_code == HTTPStatus.FORBIDDEN

    # AC-14 only adds workflow edit permission for overrides; ordinary retries still need run.
    ordinary_retry = _start_retry(run_only_api, source.id, "failure")
    ordinary_retry_final = poll_execution_until_complete(syntara_api, ordinary_retry.id, max_polls=60, poll_interval=1)
    assert ordinary_retry_final.status == ExecutionStatus.FAILED

    editor_user_id, editor_username, editor_password = create_user(syntara_api, "retry-workflow-editor")
    editor_role = create_project_role(
        syntara_api,
        project_id,
        "retry-workflow-editor",
        ["execution:run:project", "workflow:update:project"],
    )
    assign_project_role_to_user(syntara_api, project_id, editor_user_id, editor_role)
    editor_api = api_for(syntara_base_url, editor_username, editor_password)

    authorized_retry = _start_retry(
        editor_api,
        source.id,
        "failure",
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
