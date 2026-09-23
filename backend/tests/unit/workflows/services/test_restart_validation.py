"""Unit tests for restart pre-validation (AAP-92820)."""

from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.workflows.exceptions import ExecutionNotFoundError
from syntara.workflows.models.activity_execution import ActivityStatus
from syntara.workflows.models.execution import ExecutionStatus
from syntara.workflows.services.restart_validation import (
    collect_downstream_node_ids,
    collect_upstream_node_ids,
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


def test_collect_downstream_inclusive() -> None:
    assert collect_downstream_node_ids(_definition(), ["step_2"]) == {"step_2", "step_3"}


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


@pytest.mark.asyncio
async def test_validate_restart_missing_execution() -> None:
    session = _mock_session((None, "one"))
    with pytest.raises(ExecutionNotFoundError):
        await validate_restart_from_failure(session, uuid4(), ["step_2"])


@pytest.mark.asyncio
async def test_validate_restart_rejects_non_restartable_state() -> None:
    execution = _make_execution(ExecutionStatus.COMPLETED)
    session = _mock_session(
        (execution, "one"),
        ([_make_activity("step_2")], "all"),
        ([], "all"),
        (_make_version(1), "one"),
    )
    verdict = await validate_restart_from_failure(session, execution.id, ["step_2"])
    assert verdict.eligible is False
    assert "completed" in (verdict.reason or "")


@pytest.mark.asyncio
async def test_validate_restart_rejects_unknown_failure_point() -> None:
    execution = _make_execution(ExecutionStatus.FAILED)
    session = _mock_session(
        (execution, "one"),
        ([_make_activity("step_2")], "all"),
        ([], "all"),
        (_make_version(1), "one"),
    )
    verdict = await validate_restart_from_failure(session, execution.id, ["nope"])
    assert verdict.eligible is False
    assert "nope" in (verdict.reason or "")


@pytest.mark.asyncio
async def test_validate_restart_passes_clean_path() -> None:
    execution = _make_execution(ExecutionStatus.FAILED)
    session = _mock_session(
        (execution, "one"),
        ([_make_activity("step_2")], "all"),
        ([_make_completed_activity("step_1")], "all"),
        (_make_version(1), "one"),
    )
    verdict = await validate_restart_from_failure(session, execution.id, ["step_2"])
    assert verdict.eligible is True
    assert verdict.reason is None
    assert verdict.failure_point_ids == ["step_2"]
    assert verdict.snapshot_version == 1
    assert verdict.step_count_by_failure_point == {"step_2": 2}
    assert verdict.total_step_count == 2


@pytest.mark.asyncio
async def test_validate_restart_ignores_later_definition_changes() -> None:
    """Retry always uses the retained version — later saves never affect it (SDP R10)."""
    execution = _make_execution(ExecutionStatus.COMPLETED_WITH_ERRORS)
    session = _mock_session(
        (execution, "one"),
        ([_make_activity("step_2#iter-1")], "all"),
        ([], "all"),
        (_make_version(1), "one"),
    )
    verdict = await validate_restart_from_failure(session, execution.id, ["step_2"])
    assert verdict.eligible is True


@pytest.mark.asyncio
async def test_validate_restart_rejects_sanitized_upstream_output() -> None:
    """Persisted [REDACTED] output referenced downstream rejects; unreferenced markers pass."""
    execution = _make_execution(ExecutionStatus.FAILED)
    ref_nodes = [
        dict(n, parameters={**n.get("parameters", {}), "input_ref": "${step_1.token}"}) if n["id"] == "step_2" else n
        for n in NODES
    ]

    def _session_for(outputs: list) -> Mock:
        snapshot = _make_version(1, nodes=ref_nodes)
        return _mock_session(
            (execution, "one"),
            ([_make_activity("step_2")], "all"),
            (outputs, "all"),
            (snapshot, "one"),
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
async def test_template_reference_forms() -> None:
    """Field paths extracted precisely; whole-namespace refs yield empty paths; prefixes safe."""
    from syntara.workflows.utils.template_refs import find_template_refs as _all_template_refs

    assert _all_template_refs("${step_1.output}") == [("step_1", ("output",))]
    assert _all_template_refs("prefix ${step_1} suffix") == [("step_1", ())]
    assert _all_template_refs({"nested": ["${step_1.items[0]}"]}) == [("step_1", ("items", 0))]
    assert _all_template_refs("${step_1.items.1}") == [("step_1", ("items", 1))]
    assert _all_template_refs("${step_10.output}") == [("step_10", ("output",))]
    assert _all_template_refs("no refs here") == []


@pytest.mark.asyncio
async def test_paths_overlap() -> None:
    """Overlap means one field path is a prefix of the other."""
    from syntara.workflows.utils.template_refs import paths_overlap as _paths_overlap

    assert _paths_overlap(("token",), ("token",)) is True
    assert _paths_overlap((), ("token",)) is True
    assert _paths_overlap(("a",), ("a", "b")) is True
    assert _paths_overlap(("a", "b"), ("a",)) is True
    assert _paths_overlap(("status_code",), ("password",)) is False
    assert _paths_overlap(("items", 0), ("items", 1)) is False


@pytest.mark.asyncio
async def test_validate_restart_ignores_sanitized_unread_on_restart_path() -> None:
    """A redacted output referenced only by an already-completed node does not block."""
    execution = _make_execution(ExecutionStatus.FAILED)
    step_0 = {"id": "step_0", "type": "script", "parameters": {"input_ref": "${step_1.token}"}}
    nodes = [step_0, *NODES]
    edges = [{"from": "trigger_1", "to": "step_0"}, {"from": "step_0", "to": "step_1"}, *EDGES[1:]]
    version = _make_version(1, nodes=nodes)
    version.workflow_definition["edges"] = edges
    session = _mock_session(
        (execution, "one"),
        ([_make_activity("step_2")], "all"),
        ([_make_completed_activity("step_0"), _make_completed_activity("step_1", {"token": "[REDACTED]"})], "all"),
        (version, "one"),
    )
    verdict = await validate_restart_from_failure(session, execution.id, ["step_2"])
    assert verdict.eligible is True
    assert verdict.sanitized_node_ids == []


def _nodes_with_refs(refs: dict[str, str]) -> list:
    """NODES variant with template refs merged into step parameters."""
    out = []
    for node in NODES:
        params = dict(node.get("parameters", {}))
        if node["id"] in refs:
            params["input_ref"] = refs[node["id"]]
        out.append({**node, "parameters": params})
    return out


def _field_session(execution: Mock, nodes: list, completed: list, edges: list | None = None) -> Mock:
    """Mock session with a single retained version and given completed outputs."""
    version = _make_version(1, nodes=nodes)
    if edges is not None:
        version.workflow_definition["edges"] = edges
    return _mock_session(
        (execution, "one"),
        ([_make_activity("step_2")], "all"),
        (completed, "all"),
        (version, "one"),
    )


@pytest.mark.asyncio
async def test_validate_restart_allows_clean_field_despite_marker_elsewhere() -> None:
    """A marker on an unreferenced field does not block a clean-field reference."""
    execution = _make_execution(ExecutionStatus.FAILED)
    nodes = _nodes_with_refs({"step_2": "${step_1.status_code}"})
    outputs = [_make_completed_activity("step_1", {"status_code": 200, "password": "[REDACTED]"})]
    session = _field_session(execution, nodes, outputs)
    verdict = await validate_restart_from_failure(session, execution.id, ["step_2"])
    assert verdict.eligible is True
    assert verdict.sanitized_node_ids == []


@pytest.mark.asyncio
async def test_validate_restart_dotted_index_matches_taint() -> None:
    """Dotted list indices resolve like the runtime (regression: str/int mismatch)."""
    execution = _make_execution(ExecutionStatus.FAILED)
    nodes = _nodes_with_refs({"step_2": "${step_1.items.1}"})
    outputs = [_make_completed_activity("step_1", {"items": ["ok", "[REDACTED]"]})]
    verdict = await validate_restart_from_failure(_field_session(execution, nodes, outputs), execution.id, ["step_2"])
    assert verdict.eligible is False
    assert verdict.sanitized_node_ids == ["step_1"]


def _converge_definition() -> dict:
    branch_a = {"id": "step_a", "type": "script", "parameters": {"code": "exit 1"}}
    branch_b = {"id": "step_b", "type": "script", "parameters": {"code": "echo ok"}}
    conv = {"id": "conv_1", "type": "converge", "parameters": {}}
    after = {"id": "step_3", "type": "script", "parameters": {"code": "echo done"}}
    return {
        "triggers": TRIGGERS,
        "nodes": [branch_a, branch_b, conv, after],
        "edges": [
            {"from": "trigger_1", "to": "step_a"},
            {"from": "trigger_1", "to": "step_b"},
            {"from": "step_a", "to": "conv_1"},
            {"from": "step_b", "to": "conv_1"},
            {"from": "conv_1", "to": "step_3"},
        ],
    }


def _converge_session(execution: Mock, converge_status: str) -> Mock:
    snapshot = _make_version(1)
    snapshot.workflow_definition = _converge_definition()
    completed = [_make_completed_activity("step_b")]
    if converge_status == "completed":
        completed.append(_make_completed_activity("conv_1"))
        failed = [_make_activity("step_a")]
    else:
        failed = [_make_activity("step_a"), _make_activity("conv_1")]
    return _mock_session(
        (execution, "one"),
        (failed, "all"),
        (completed, "all"),
        (snapshot, "one"),
    )


@pytest.mark.asyncio
async def test_validate_restart_rejects_failure_under_completed_converge() -> None:
    execution = _make_execution(ExecutionStatus.FAILED)
    session = _converge_session(execution, "completed")
    verdict = await validate_restart_from_failure(session, execution.id, ["step_a"])
    assert verdict.eligible is False
    assert "conv_1" in (verdict.reason or "")


@pytest.mark.asyncio
async def test_validate_restart_allows_failure_under_failed_converge() -> None:
    execution = _make_execution(ExecutionStatus.FAILED)
    session = _converge_session(execution, "failed")
    verdict = await validate_restart_from_failure(session, execution.id, ["step_a"])
    assert verdict.eligible is True


def _run_session(
    execution: Mock,
    definition: dict,
    *,
    failed: list | None = None,
    completed: list | None = None,
) -> Mock:
    """Mock session serving one definition as the retained version."""
    snapshot = _make_version(1)
    snapshot.workflow_definition = definition
    return _mock_session(
        (execution, "one"),
        (failed if failed is not None else [_make_activity("step_2")], "all"),
        (completed if completed is not None else [], "all"),
        (snapshot, "one"),
    )


@pytest.mark.asyncio
async def test_validate_restart_rejects_empty_selection() -> None:
    """Empty selection is rejected with guidance (documented behavior)."""
    execution = _make_execution(ExecutionStatus.FAILED)
    verdict = await validate_restart_from_failure(_run_session(execution, _definition()), execution.id, [])
    assert verdict.eligible is False
    assert "no failure points selected" in (verdict.reason or "")


@pytest.mark.asyncio
async def test_validate_restart_rejects_iteration_suffixed_selection() -> None:
    """Loop-iteration ids are rejected explicitly instead of a misleading unknown-node error."""
    execution = _make_execution(ExecutionStatus.FAILED)
    verdict = await validate_restart_from_failure(
        _run_session(execution, _definition()), execution.id, ["step_2#iter-1"]
    )
    assert verdict.eligible is False
    assert "base node" in (verdict.reason or "")


@pytest.mark.asyncio
async def test_validate_restart_flags_side_branch_taint() -> None:
    """A completed side branch referenced from the restart path is flagged."""
    execution = _make_execution(ExecutionStatus.FAILED)
    side = {"id": "side", "type": "script", "parameters": {"code": "echo side"}}
    step_3 = {"id": "step_3", "type": "script", "parameters": {"input_ref": "${side.token}"}}
    nodes = [side, *NODES[:-1], step_3]
    edges = [
        {"from": "trigger_1", "to": "side"},
        {"from": "trigger_1", "to": "step_1"},
        {"from": "step_1", "to": "step_2"},
        {"from": "step_2", "to": "step_3"},
    ]
    completed = [_make_completed_activity("side", {"token": "[REDACTED]"})]
    verdict = await validate_restart_from_failure(
        _field_session(execution, nodes, completed, edges), execution.id, ["step_2"]
    )
    assert verdict.eligible is False
    assert verdict.sanitized_node_ids == ["side"]


@pytest.mark.asyncio
async def test_validate_restart_rejects_whole_namespace_taint() -> None:
    """A bare ${node} reference taints on any marker under that node."""
    execution = _make_execution(ExecutionStatus.FAILED)
    nodes = _nodes_with_refs({"step_2": "prefix ${step_1} suffix"})
    completed = [_make_completed_activity("step_1", {"nested": {"deep": "[REDACTED]"}})]
    verdict = await validate_restart_from_failure(_field_session(execution, nodes, completed), execution.id, ["step_2"])
    assert verdict.eligible is False
    assert verdict.sanitized_node_ids == ["step_1"]


@pytest.mark.asyncio
async def test_validate_restart_indexed_reference_intersection() -> None:
    """Indexed refs intersect indexed taint; sibling indices do not."""
    execution = _make_execution(ExecutionStatus.FAILED)
    nodes = _nodes_with_refs({"step_2": "${step_1.items[1]}"})
    outputs = [_make_completed_activity("step_1", {"items": ["ok", "[REDACTED]"]})]
    verdict = await validate_restart_from_failure(_field_session(execution, nodes, outputs), execution.id, ["step_2"])
    assert verdict.eligible is False
    assert verdict.sanitized_node_ids == ["step_1"]

    sibling_nodes = _nodes_with_refs({"step_2": "${step_1.items[0]}"})
    clean = await validate_restart_from_failure(
        _field_session(execution, sibling_nodes, outputs), execution.id, ["step_2"]
    )
    assert clean.eligible is True


@pytest.mark.asyncio
async def test_validate_restart_rejects_missing_version() -> None:
    """A gone retained version yields a reason, not a crash."""
    execution = _make_execution(ExecutionStatus.FAILED)
    session = _mock_session(
        (execution, "one"),
        ([_make_activity("step_2")], "all"),
        ([], "all"),
        (None, "one"),
    )
    verdict = await validate_restart_from_failure(session, execution.id, ["step_2"])
    assert verdict.eligible is False
    assert "original workflow version" in (verdict.reason or "")


@pytest.mark.asyncio
async def test_validate_restart_mixed_converge_tier_allows() -> None:
    """A failed converge at the nearest tier keeps candidates even with a completed one beside it."""
    execution = _make_execution(ExecutionStatus.FAILED)
    conv_ok = {"id": "conv_ok", "type": "converge", "parameters": {}}
    conv_bad = {"id": "conv_bad", "type": "converge", "parameters": {}}
    after = {"id": "step_3", "type": "script", "parameters": {"code": "echo done"}}
    definition = {
        "triggers": TRIGGERS,
        "nodes": [
            {"id": "step_a", "type": "script", "parameters": {"code": "exit 1"}},
            conv_ok,
            conv_bad,
            after,
        ],
        "edges": [
            {"from": "trigger_1", "to": "step_a"},
            {"from": "step_a", "to": "conv_ok"},
            {"from": "step_a", "to": "conv_bad"},
            {"from": "conv_ok", "to": "step_3"},
            {"from": "conv_bad", "to": "step_3"},
        ],
    }
    snapshot = _make_version(1)
    snapshot.workflow_definition = definition
    completed = [_make_completed_activity("conv_ok")]
    failed = [_make_activity("step_a"), _make_activity("conv_bad")]
    session = _mock_session((execution, "one"), (failed, "all"), (completed, "all"), (snapshot, "one"))
    verdict = await validate_restart_from_failure(session, execution.id, ["step_a"])
    assert verdict.eligible is True


@pytest.mark.asyncio
async def test_validate_restart_multi_iteration_taint_flags_node() -> None:
    """Any tainted iteration taints the node (no last-write-wins)."""
    execution = _make_execution(ExecutionStatus.FAILED)
    iter_clean = _make_completed_activity("step_1#iter-0", {"token": "abc"})
    iter_tainted = _make_completed_activity("step_1#iter-1", {"token": "[REDACTED]"})
    nodes = _nodes_with_refs({"step_2": "${step_1.token}"})
    version = _make_version(1, nodes=nodes)
    session = _mock_session(
        (execution, "one"),
        ([_make_activity("step_2")], "all"),
        ([iter_clean, iter_tainted], "all"),
        (version, "one"),
    )
    verdict = await validate_restart_from_failure(session, execution.id, ["step_2"])
    assert verdict.eligible is False
    assert verdict.sanitized_node_ids == ["step_1"]


@pytest.mark.asyncio
async def test_validate_restart_ignores_none_output() -> None:
    """Completed activities with null outputs cannot carry taint."""
    execution = _make_execution(ExecutionStatus.FAILED)
    null_out = _make_completed_activity("step_1")
    null_out.output_data = None
    nodes = _nodes_with_refs({"step_2": "${step_1.token}"})
    verdict = await validate_restart_from_failure(
        _field_session(execution, nodes, [null_out]), execution.id, ["step_2"]
    )
    assert verdict.eligible is True


@pytest.mark.asyncio
async def test_validate_restart_normalizes_and_dedupes_selection() -> None:
    """Selections dedupe and strip whitespace."""
    execution = _make_execution(ExecutionStatus.FAILED)
    session = _mock_session(
        (execution, "one"),
        ([_make_activity("step_2")], "all"),
        ([], "all"),
        (_make_version(1), "one"),
    )
    verdict = await validate_restart_from_failure(session, execution.id, [" step_2 ", "step_2"])
    assert verdict.eligible is True
    assert verdict.failure_point_ids == ["step_2"]


@pytest.mark.asyncio
async def test_validate_restart_ignores_self_reference() -> None:
    """A node referencing only itself does not flag anything."""
    execution = _make_execution(ExecutionStatus.FAILED)
    nodes = _nodes_with_refs({"step_1": "${step_1.token}"})
    outputs = [_make_completed_activity("step_1", {"token": "[REDACTED]"})]
    verdict = await validate_restart_from_failure(_field_session(execution, nodes, outputs), execution.id, ["step_2"])
    assert verdict.eligible is True
    assert verdict.sanitized_node_ids == []


def _parallel_definition() -> dict:
    """Two independent branches converging back into a shared tail."""
    branch_a = {"id": "step_a", "type": "script", "parameters": {"code": "exit 1"}}
    branch_b = {"id": "step_b", "type": "script", "parameters": {"code": "exit 1"}}
    conv = {"id": "conv_1", "type": "converge", "parameters": {}}
    after = {"id": "step_3", "type": "script", "parameters": {"code": "echo done"}}
    return {
        "triggers": TRIGGERS,
        "nodes": [branch_a, branch_b, conv, after],
        "edges": [
            {"from": "trigger_1", "to": "step_a"},
            {"from": "trigger_1", "to": "step_b"},
            {"from": "step_a", "to": "conv_1"},
            {"from": "step_b", "to": "conv_1"},
            {"from": "conv_1", "to": "step_3"},
        ],
    }


@pytest.mark.asyncio
async def test_validate_restart_step_count_single_point() -> None:
    """SDP R11a: step count is the total steps that will execute, not just the failed one."""
    execution = _make_execution(ExecutionStatus.FAILED)
    session = _mock_session(
        (execution, "one"),
        ([_make_activity("step_1")], "all"),
        ([], "all"),
        (_make_version(1), "one"),
    )
    verdict = await validate_restart_from_failure(session, execution.id, ["step_1"])
    assert verdict.eligible is True
    assert verdict.step_count_by_failure_point == {"step_1": 3}
    assert verdict.total_step_count == 3


@pytest.mark.asyncio
async def test_validate_restart_step_count_dedupes_shared_tail() -> None:
    """Per-point counts are independent; the total dedupes the shared converge/tail (SDP R11a/AC-2)."""
    execution = _make_execution(ExecutionStatus.FAILED)
    snapshot = _make_version(1)
    snapshot.workflow_definition = _parallel_definition()
    session = _mock_session(
        (execution, "one"),
        ([_make_activity("step_a"), _make_activity("step_b")], "all"),
        ([], "all"),
        (snapshot, "one"),
    )
    verdict = await validate_restart_from_failure(session, execution.id, ["step_a", "step_b"])
    assert verdict.eligible is True
    assert verdict.step_count_by_failure_point == {"step_a": 3, "step_b": 3}
    assert verdict.total_step_count == 4
