"""Unit tests for restart pre-validation (AAP-92820)."""

from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.workflows.exceptions import ExecutionNotFoundError
from syntara.workflows.models.activity_execution import ActivityStatus
from syntara.workflows.models.execution import ExecutionStatus
from syntara.workflows.services.restart_validation import (
    canonical_node,
    collect_upstream_node_ids,
    diff_upstream_nodes,
    strip_iteration_suffix,
    validate_restart_from_failure,
)

TRIGGERS = [{"id": "trigger_1", "type": "manual_trigger", "parameters": {}}]
NODES = [
    {"id": "step_1", "type": "script", "parameters": {"code": "echo hi"}, "position": {"x": 0}},
    {"id": "step_2", "type": "script", "parameters": {"code": "exit 1"}, "position": {"x": 1}},
    {"id": "step_3", "type": "script", "parameters": {"code": "echo done"}, "position": {"x": 2}},
]
EDGES = [
    {"from": "trigger_1", "to": "step_1"},
    {"from": "step_1", "to": "step_2"},
    {"from": "step_2", "to": "step_3"},
]


def _definition(nodes: list | None = None, triggers: list | None = None) -> dict:
    return {
        "triggers": triggers if triggers is not None else TRIGGERS,
        "nodes": nodes if nodes is not None else NODES,
        "edges": EDGES,
    }


def test_strip_iteration_suffix() -> None:
    assert strip_iteration_suffix("step_2#iter-3") == "step_2"
    assert strip_iteration_suffix("step_2") == "step_2"


def test_collect_upstream_inclusive() -> None:
    assert collect_upstream_node_ids(_definition(), ["step_2"]) == {"trigger_1", "step_1", "step_2"}


def test_canonical_node_ignores_position() -> None:
    assert canonical_node({"id": "a", "type": "script", "position": {"x": 1}}) == canonical_node(
        {"id": "a", "type": "script", "position": {"x": 99}}
    )


def test_diff_includes_triggers_without_false_positive() -> None:
    """Regression: triggers anchor every path, so an unchanged trigger must never diff."""
    assert diff_upstream_nodes(_definition(), _definition(), {"trigger_1", "step_1", "step_2"}) == []


def test_diff_detects_upstream_change_only() -> None:
    current = [dict(n, parameters={"code": "exit 0"}) if n["id"] == "step_1" else n for n in NODES]
    assert diff_upstream_nodes(_definition(), _definition(nodes=current), {"trigger_1", "step_1", "step_2"}) == [
        "step_1"
    ]
    downstream = [dict(n, parameters={"code": "changed"}) if n["id"] == "step_3" else n for n in NODES]
    assert diff_upstream_nodes(_definition(), _definition(nodes=downstream), {"trigger_1", "step_1", "step_2"}) == []
    assert diff_upstream_nodes(
        _definition(), _definition(nodes=[n for n in NODES if n["id"] != "step_1"]), {"step_2", "step_1"}
    ) == ["step_1"]


def _mock_session(*results: Mock) -> AsyncSession:
    session = Mock(spec=AsyncSession)
    exec_results = []
    for payload, method in results:
        result = Mock()
        if method == "one":
            result.one_or_none.return_value = payload
        else:
            result.all.return_value = payload
        exec_results.append(result)

    async def _exec(*args: object, **kwargs: object) -> Mock:
        return exec_results.pop(0)

    session.exec.side_effect = _exec
    return session


def _make_execution(status: ExecutionStatus) -> Mock:
    execution = Mock()
    execution.id = uuid4()
    execution.status = status
    execution.workflow_id = uuid4()
    execution.workflow_version_id = uuid4()
    return execution


def _make_activity(name: str) -> Mock:
    activity = Mock()
    activity.activity_name = name
    activity.status = ActivityStatus.FAILED
    return activity


def _make_completed_activity(name: str, output: dict | None = None) -> Mock:
    activity = Mock()
    activity.activity_name = name
    activity.status = ActivityStatus.COMPLETED
    activity.output_data = output if output is not None else {"result": "ok"}
    return activity


def _make_version(version: int, nodes: list | None = None) -> Mock:
    record = Mock()
    record.version = version
    record.workflow_definition = _definition(nodes=nodes)
    return record


def _make_workflow(version: int) -> Mock:
    workflow = Mock()
    workflow.id = uuid4()
    workflow.current_version = version
    return workflow


@pytest.mark.asyncio
async def test_validate_restart_missing_execution() -> None:
    session = _mock_session((None, "one"))
    with pytest.raises(ExecutionNotFoundError):
        await validate_restart_from_failure(session, uuid4(), ["step_2"])


@pytest.mark.asyncio
async def test_validate_restart_rejects_non_restartable_state() -> None:
    execution = _make_execution(ExecutionStatus.COMPLETED)
    workflow = _make_workflow(1)
    execution.workflow_id = workflow.id
    session = _mock_session(
        (execution, "one"),
        ([_make_activity("step_2")], "all"),
        ([], "all"),
        (_make_version(1), "one"),
        (workflow, "one"),
        (_make_version(1), "one"),
    )
    verdict = await validate_restart_from_failure(session, execution.id, ["step_2"])
    assert verdict.eligible is False
    assert "completed" in (verdict.reason or "")


@pytest.mark.asyncio
async def test_validate_restart_rejects_unknown_failure_point() -> None:
    execution = _make_execution(ExecutionStatus.FAILED)
    workflow = _make_workflow(1)
    execution.workflow_id = workflow.id
    session = _mock_session(
        (execution, "one"),
        ([_make_activity("step_2")], "all"),
        ([], "all"),
        (_make_version(1), "one"),
        (workflow, "one"),
        (_make_version(1), "one"),
    )
    verdict = await validate_restart_from_failure(session, execution.id, ["nope"])
    assert verdict.eligible is False
    assert "nope" in (verdict.reason or "")


@pytest.mark.asyncio
async def test_validate_restart_passes_clean_path() -> None:
    execution = _make_execution(ExecutionStatus.FAILED)
    workflow = _make_workflow(2)
    execution.workflow_id = workflow.id
    session = _mock_session(
        (execution, "one"),
        ([_make_activity("step_2")], "all"),
        ([_make_completed_activity("step_1")], "all"),
        (_make_version(1), "one"),
        (workflow, "one"),
        (_make_version(2), "one"),
    )
    verdict = await validate_restart_from_failure(session, execution.id, ["step_2"])
    assert verdict.eligible is True
    assert verdict.reason is None
    assert verdict.failure_point_ids == ["step_2"]
    assert verdict.snapshot_version == 1
    assert verdict.current_version == 2


@pytest.mark.asyncio
async def test_validate_restart_rejects_upstream_change() -> None:
    execution = _make_execution(ExecutionStatus.COMPLETED_WITH_ERRORS)
    workflow = _make_workflow(2)
    execution.workflow_id = workflow.id
    changed = [dict(n, parameters={"code": "exit 0"}) if n["id"] == "step_1" else n for n in NODES]
    session = _mock_session(
        (execution, "one"),
        ([_make_activity("step_2#iter-1")], "all"),
        ([], "all"),
        (_make_version(1), "one"),
        (workflow, "one"),
        (_make_version(2, nodes=changed), "one"),
    )
    verdict = await validate_restart_from_failure(session, execution.id, ["step_2"])
    assert verdict.eligible is False
    assert verdict.changed_node_ids == ["step_1"]
    assert "step_1" in (verdict.reason or "")


@pytest.mark.asyncio
async def test_validate_restart_rejects_inserted_upstream_node() -> None:
    """A node inserted on the upstream path in the current version rejects."""
    execution = _make_execution(ExecutionStatus.FAILED)
    workflow = _make_workflow(2)
    execution.workflow_id = workflow.id
    gate = {"id": "step_1b", "type": "script", "parameters": {"code": "echo gate"}}
    current_nodes = [NODES[0], gate, NODES[1], NODES[2]]
    current_edges = [
        {"from": "trigger_1", "to": "step_1"},
        {"from": "step_1", "to": "step_1b"},
        {"from": "step_1b", "to": "step_2"},
        {"from": "step_2", "to": "step_3"},
    ]
    current_version = _make_version(2, nodes=current_nodes)
    current_version.workflow_definition["edges"] = current_edges
    session = _mock_session(
        (execution, "one"),
        ([_make_activity("step_2")], "all"),
        ([], "all"),
        (_make_version(1), "one"),
        (workflow, "one"),
        (current_version, "one"),
    )
    verdict = await validate_restart_from_failure(session, execution.id, ["step_2"])
    assert verdict.eligible is False
    assert verdict.changed_node_ids == ["step_1b"]
    assert "step_1b" in (verdict.reason or "")


@pytest.mark.asyncio
async def test_validate_restart_rejects_sanitized_upstream_output() -> None:
    """Persisted [REDACTED] output referenced downstream rejects; unreferenced markers pass."""
    execution = _make_execution(ExecutionStatus.FAILED)
    workflow = _make_workflow(2)
    execution.workflow_id = workflow.id
    ref_nodes = [
        dict(n, parameters={**n.get("parameters", {}), "input_ref": "${step_1.token}"}) if n["id"] == "step_2" else n
        for n in NODES
    ]

    def _session_for(outputs: list) -> Mock:
        snapshot = _make_version(1, nodes=ref_nodes)
        current = _make_version(2, nodes=ref_nodes)
        return _mock_session(
            (execution, "one"),
            ([_make_activity("step_2")], "all"),
            (outputs, "all"),
            (snapshot, "one"),
            (workflow, "one"),
            (current, "one"),
        )

    verdict = await validate_restart_from_failure(
        _session_for(
            [
                _make_completed_activity("step_1", {"token": "[REDACTED]"}),
                _make_completed_activity("step_3", {"note": "[REDACTED]"}),
            ]
        ),
        execution.id,
        ["step_2"],
    )
    assert verdict.eligible is False
    assert verdict.sanitized_node_ids == ["step_1"]
    assert "step_1" in (verdict.reason or "")

    clean = await validate_restart_from_failure(
        _session_for([_make_completed_activity("step_1", {"token": "abc123"})]),
        execution.id,
        ["step_2"],
    )
    assert clean.eligible is True
    assert clean.sanitized_node_ids == []


@pytest.mark.asyncio
async def test_validate_restart_flags_rewired_into_path_node() -> None:
    """A snapshot node rewired into the upstream path counts as inserted."""
    execution = _make_execution(ExecutionStatus.FAILED)
    workflow = _make_workflow(2)
    execution.workflow_id = workflow.id
    sidecar = {"id": "sidecar", "type": "script", "parameters": {"code": "echo side"}}
    snapshot_version = _make_version(1, nodes=[*NODES, sidecar])
    snapshot_version.workflow_definition["edges"] = [*EDGES]
    current_nodes = [n for n in NODES if n["id"] != "step_1"] + [
        {"id": "step_1", "type": "script", "parameters": {"code": "echo hi"}},
        sidecar,
    ]
    current_edges = [
        {"from": "trigger_1", "to": "sidecar"},
        {"from": "sidecar", "to": "step_1"},
        {"from": "step_1", "to": "step_2"},
        {"from": "step_2", "to": "step_3"},
    ]
    current_version = _make_version(2, nodes=current_nodes)
    current_version.workflow_definition["edges"] = current_edges
    session = _mock_session(
        (execution, "one"),
        ([_make_activity("step_2")], "all"),
        ([], "all"),
        (snapshot_version, "one"),
        (workflow, "one"),
        (current_version, "one"),
    )
    verdict = await validate_restart_from_failure(session, execution.id, ["step_2"])
    assert verdict.eligible is False
    assert verdict.changed_node_ids == ["sidecar"]
