"""Integration test for Sub-workflow Reference Mode parent→child→parent lifecycle.

Proves the full Temporal lifecycle through a real WorkflowEnvironment:
parent starts, dispatches a sub_workflow node, which calls the setup activity
(with mocked DB), starts a child OrchestratorWorkflow via execute_child_workflow,
the child runs subworkflow_trigger → script, completes, and the parent receives
the child result and completes.

Also proves downstream parent nodes can consume SubWorkflowOutput fields via
the normal template resolver (AAP-91263 output contract).

Story: AAP-94069 — Sub-workflow Reference Mode POC
"""

from __future__ import annotations

import asyncio
import contextlib
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from uuid import uuid4, uuid5

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Sequence

import pytest
from temporalio.api.enums.v1 import EventType
from temporalio.worker import Worker

from syntara.workflows.workflow_engine.activities.loop import loop
from syntara.workflows.workflow_engine.activities.manual_trigger import manual_trigger
from syntara.workflows.workflow_engine.activities.runtime_settings_activity import (
    fetch_workflow_runtime_settings,
)
from syntara.workflows.workflow_engine.activities.script_activity import (
    execute_script_activity,
)
from syntara.workflows.workflow_engine.activities.sub_workflow_setup_activity import (
    _SUB_WORKFLOW_NAMESPACE,
    SubWorkflowSetupActivity,
)
from syntara.workflows.workflow_engine.activities.subworkflow_trigger import (
    subworkflow_trigger,
)
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.models.workflow_definition import SubWorkflowOutput
from syntara.workflows.workflow_engine.services.temporal_execution_service import (
    TemporalExecutionService,
)

_CHILD_WF_ID = uuid4()
_CHILD_VERSION_ID = uuid4()
_CHILD_PROJECT_ID = uuid4()
_CHILD_CREATED_BY = uuid4()
_PARENT_EXECUTION_ID = str(uuid4())
_PARENT_USER_ID = str(uuid4())

_TASK_QUEUE = "sub-wf-integration"
_WORKFLOW_RESULT_TIMEOUT = 30

_CHILD_WORKFLOW_DEF: dict[str, Any] = {
    "schema_version": "2.0.0",
    "triggers": [
        {"id": "child_trigger", "type": "subworkflow_trigger", "parameters": {}},
    ],
    "nodes": [
        {
            "id": "child_script",
            "type": "script",
            "parameters": {"language": "bash", "code": "echo child_executed"},
        },
    ],
    "edges": [
        {"from": "child_trigger", "to": "child_script"},
    ],
}

_FAILING_CHILD_WORKFLOW_DEF: dict[str, Any] = {
    "schema_version": "2.0.0",
    "triggers": [
        {"id": "child_trigger", "type": "subworkflow_trigger", "parameters": {}},
    ],
    "nodes": [
        {
            "id": "child_script",
            "type": "script",
            "parameters": {"language": "bash", "code": "exit 1"},
        },
    ],
    "edges": [
        {"from": "child_trigger", "to": "child_script"},
    ],
}


def _parent_workflow_def() -> dict[str, Any]:
    """Build the parent workflow definition with a sub_workflow node."""
    return {
        "schema_version": "2.0.0",
        "triggers": [
            {"id": "trigger", "type": "manual_trigger", "parameters": {}},
        ],
        "nodes": [
            {
                "id": "sub_wf_node",
                "type": "sub_workflow",
                "parameters": {
                    "workflow_id": str(_CHILD_WF_ID),
                    "trigger_node_id": "child_trigger",
                    "input_mapping": {"greeting": "hello from parent"},
                },
            },
        ],
        "edges": [
            {"from": "trigger", "to": "sub_wf_node"},
        ],
    }


class _MockExecResult:
    """Mock for SQLModel exec() return value."""

    def __init__(self, value: object) -> None:
        self._value = value

    def first(self) -> object:
        """Return the stored value."""
        return self._value


class _MockSession:
    """Mock async DB session supporting exec/get/add/commit."""

    def __init__(
        self,
        exec_results: list[object] | None = None,
    ) -> None:
        self._exec_results = list(exec_results or [])
        self._exec_idx = 0

    async def exec(self, _query: object) -> _MockExecResult:
        """Return next pre-configured result."""
        if self._exec_idx < len(self._exec_results):
            val = self._exec_results[self._exec_idx]
            self._exec_idx += 1
            return _MockExecResult(val)
        return _MockExecResult(None)

    async def get(self, _model: type, _id: object) -> None:
        """Always return None (no existing record)."""
        return

    def add(self, _obj: object) -> None:
        """No-op."""

    async def commit(self) -> None:
        """No-op."""


def _parent_workflow_metadata() -> dict[str, Any]:
    """Build workflow_metadata so the parent populates _created_by_user_id."""
    return {
        "workflow_context": {
            "workflow": {
                "name": "parent-wf",
                "id": str(uuid4()),
                "version": 1,
                "published": True,
                "author": "test-author",
                "project_id": str(_CHILD_PROJECT_ID),
            },
            "execution": {
                "id": _PARENT_EXECUTION_ID,
                "mode": "manual",
                "created_by": _PARENT_USER_ID,
                "created_by_user_id": _PARENT_USER_ID,
                "created_at": "2026-01-01T00:00:00Z",
                "workflow_version_id": str(uuid4()),
            },
        },
    }


def _mock_session_factory() -> Callable[..., contextlib.AbstractAsyncContextManager[_MockSession]]:
    """Build a session factory that returns mock sessions for the setup activity.

    Each call produces fresh sessions so Temporal retries don't exhaust the iterator.
    Odd calls: session for Workflow/Version query + User query.
    Even calls: session for Execution idempotency check + create.
    """
    mock_workflow = SimpleNamespace(
        id=_CHILD_WF_ID,
        name="test-child-workflow",
        project_id=_CHILD_PROJECT_ID,
        created_by=_CHILD_CREATED_BY,
        published_version_id=_CHILD_VERSION_ID,
        is_enabled=True,
    )
    mock_version = SimpleNamespace(
        id=_CHILD_VERSION_ID,
        version=1,
        workflow_definition=_CHILD_WORKFLOW_DEF,
    )

    call_count = 0

    @contextlib.asynccontextmanager
    async def factory() -> AsyncIterator[_MockSession]:
        nonlocal call_count
        call_count += 1
        if call_count % 2 == 1:
            yield _MockSession(exec_results=[(mock_workflow, mock_version), None])
        else:
            yield _MockSession()

    return factory


def _mock_session_factory_for_def(
    child_def: dict[str, Any],
) -> Callable[..., contextlib.AbstractAsyncContextManager[_MockSession]]:
    """Like _mock_session_factory but uses a custom child workflow definition."""
    mock_workflow = SimpleNamespace(
        id=_CHILD_WF_ID,
        name="test-child-workflow",
        project_id=_CHILD_PROJECT_ID,
        created_by=_CHILD_CREATED_BY,
        published_version_id=_CHILD_VERSION_ID,
        is_enabled=True,
    )
    mock_version = SimpleNamespace(
        id=_CHILD_VERSION_ID,
        version=1,
        workflow_definition=child_def,
    )

    call_count = 0

    @contextlib.asynccontextmanager
    async def factory() -> AsyncIterator[_MockSession]:
        nonlocal call_count
        call_count += 1
        if call_count % 2 == 1:
            yield _MockSession(exec_results=[(mock_workflow, mock_version), None])
        else:
            yield _MockSession()

    return factory


def _build_activities(child_def: dict[str, Any] | None = None) -> Sequence[Callable[..., Any]]:
    """Create all activities needed for the parent→child lifecycle."""
    factory = _mock_session_factory_for_def(child_def) if child_def is not None else _mock_session_factory()
    setup = SubWorkflowSetupActivity(
        session_factory=factory,  # type: ignore[arg-type]
        task_queue=_TASK_QUEUE,
    )
    return [
        manual_trigger,
        subworkflow_trigger,
        execute_script_activity,
        fetch_workflow_runtime_settings,
        setup.run,
    ]


def _parent_workflow_def_with_downstream() -> dict[str, Any]:
    """Parent workflow with a downstream script that consumes sub-workflow output."""
    return {
        "schema_version": "2.0.0",
        "triggers": [
            {"id": "trigger", "type": "manual_trigger", "parameters": {}},
        ],
        "nodes": [
            {
                "id": "sub_wf_node",
                "type": "sub_workflow",
                "parameters": {
                    "workflow_id": str(_CHILD_WF_ID),
                    "trigger_node_id": "child_trigger",
                    "input_mapping": {"greeting": "hello from parent"},
                },
            },
            {
                "id": "downstream_script",
                "type": "script",
                "parameters": {
                    "language": "python",
                    "code": (
                        "import json, sys\n"
                        'sys.stdout.write(json.dumps({"child_id": "${sub_wf_node.Result.child_execution_id}",'
                        ' "child_status": "${sub_wf_node.Result.child_status}",'
                        ' "child_wf_name": "${sub_wf_node.Result.child_workflow_name}",'
                        ' "status_code": "${sub_wf_node.StatusCode}"}))'
                    ),
                },
            },
        ],
        "edges": [
            {"from": "trigger", "to": "sub_wf_node"},
            {"from": "sub_wf_node", "to": "downstream_script"},
        ],
    }


async def _run_parent_workflow(
    temporal_env: object,
    workflow_def: dict[str, Any] | None = None,
    workflow_name: str = "sub-wf-integration",
    child_workflow_def: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Start a parent workflow and return its raw result."""
    from temporalio.testing import WorkflowEnvironment

    assert isinstance(temporal_env, WorkflowEnvironment)
    activities = _build_activities(child_def=child_workflow_def)
    async with Worker(
        temporal_env.client,
        task_queue=_TASK_QUEUE,
        workflows=[OrchestratorWorkflow],
        activities=activities,
    ):
        svc = TemporalExecutionService(
            temporal_client=temporal_env.client,
            task_queue=_TASK_QUEUE,
        )
        start = await svc.start_workflow(
            workflow_def=workflow_def or _parent_workflow_def(),
            workflow_name=workflow_name,
            trigger_node_id="trigger",
            include_node_results=True,
            execution_id=_PARENT_EXECUTION_ID,
            workflow_metadata=_parent_workflow_metadata(),
        )
        handle = temporal_env.client.get_workflow_handle(start.temporal_workflow_id)
        raw: dict[str, Any] = await asyncio.wait_for(handle.result(), timeout=_WORKFLOW_RESULT_TIMEOUT)
        return raw


@pytest.mark.integration
@pytest.mark.asyncio
class TestSubWorkflowLifecycle:
    """Prove the parent→child→parent lifecycle through real Temporal."""

    async def test_parent_completes_after_child(self, temporal_env: object) -> None:
        """Full lifecycle: parent triggers child via sub_workflow node, child runs, parent completes."""
        result = await _run_parent_workflow(temporal_env)

        assert result["status"] == "completed"

    async def test_sub_workflow_node_in_completed_activities(self, temporal_env: object) -> None:
        """The sub_workflow node appears in parent's completed_activities list."""
        result = await _run_parent_workflow(temporal_env)

        assert "sub_wf_node" in result["completed_activities"]

    async def test_child_execution_id_is_deterministic(self, temporal_env: object) -> None:
        """Child execution ID is UUID5(namespace, parent_exec:node_id)."""
        result = await _run_parent_workflow(temporal_env)

        sub_wf_output = result["activity_outputs"]["sub_wf_node"]
        expected_child_id = str(uuid5(_SUB_WORKFLOW_NAMESPACE, f"{_PARENT_EXECUTION_ID}:sub_wf_node"))
        assert sub_wf_output["Result"]["child_execution_id"] == expected_child_id

    async def test_child_status_is_completed(self, temporal_env: object) -> None:
        """Parent reports child_status as 'completed'."""
        result = await _run_parent_workflow(temporal_env)

        sub_wf_output = result["activity_outputs"]["sub_wf_node"]
        assert sub_wf_output["Result"]["child_status"] == "completed"

    async def test_child_workflow_metadata_in_output(self, temporal_env: object) -> None:
        """Parent output includes child workflow identity fields."""
        result = await _run_parent_workflow(temporal_env)

        sub_wf_output = result["activity_outputs"]["sub_wf_node"]
        assert sub_wf_output["Result"]["child_workflow_id"] == str(_CHILD_WF_ID)
        assert sub_wf_output["Result"]["child_workflow_name"] == "test-child-workflow"
        assert sub_wf_output["Result"]["child_workflow_version"] == 1

    async def test_trigger_in_completed_activities(self, temporal_env: object) -> None:
        """The manual trigger node appears in completed_activities."""
        result = await _run_parent_workflow(temporal_env)

        assert "trigger" in result["completed_activities"]

    async def test_result_structure_matches_build_result(self, temporal_env: object) -> None:
        """Result dict has all keys produced by _build_result."""
        result = await _run_parent_workflow(temporal_env)

        assert set(result.keys()) == {
            "status",
            "execution_id",
            "activity_outputs",
            "activity_inputs",
            "completed_activities",
            "failed_activities",
        }
        assert result["failed_activities"] == {}

    async def test_sub_workflow_output_validates_against_m1_model(self, temporal_env: object) -> None:
        """Runtime output validates against PR #817's SubWorkflowOutput model."""
        result = await _run_parent_workflow(temporal_env)

        sub_wf_output = result["activity_outputs"]["sub_wf_node"]
        validated = SubWorkflowOutput.model_validate(sub_wf_output)

        expected_child_id = str(uuid5(_SUB_WORKFLOW_NAMESPACE, f"{_PARENT_EXECUTION_ID}:sub_wf_node"))
        assert validated.Result is not None
        assert validated.Result.child_execution_id == expected_child_id
        assert validated.Result.child_status == "completed"
        assert validated.Result.child_workflow_id == str(_CHILD_WF_ID)
        assert validated.Result.child_workflow_name == "test-child-workflow"
        assert validated.Result.child_workflow_version == 1
        assert validated.Result.outputs is None
        assert validated.StatusCode == 0
        assert validated.StatusMessage == "Sub-workflow completed successfully"
        assert validated.ErrorMessage is None


@pytest.mark.integration
@pytest.mark.asyncio
class TestSubWorkflowDownstreamOutputConsumption:
    """Prove downstream parent nodes consume SubWorkflowOutput via template resolution."""

    async def test_downstream_node_receives_resolved_child_execution_id(self, temporal_env: object) -> None:
        """The downstream script's parameters contain the actual UUID, not the raw template."""
        result = await _run_parent_workflow(
            temporal_env,
            workflow_def=_parent_workflow_def_with_downstream(),
            workflow_name="sub-wf-downstream-integration",
        )

        assert result["status"] == "completed"

        downstream_input = result["activity_inputs"]["downstream_script"]
        expected_child_id = str(uuid5(_SUB_WORKFLOW_NAMESPACE, f"{_PARENT_EXECUTION_ID}:sub_wf_node"))
        assert "${sub_wf_node.Result.child_execution_id}" not in downstream_input["code"]
        assert expected_child_id in downstream_input["code"]

    async def test_downstream_node_receives_resolved_child_status(self, temporal_env: object) -> None:
        """The downstream script's parameters contain 'completed', not the raw template."""
        result = await _run_parent_workflow(
            temporal_env,
            workflow_def=_parent_workflow_def_with_downstream(),
            workflow_name="sub-wf-downstream-integration",
        )

        downstream_input = result["activity_inputs"]["downstream_script"]
        assert "${sub_wf_node.Result.child_status}" not in downstream_input["code"]
        assert "completed" in downstream_input["code"]

    async def test_downstream_script_produces_structured_output(self, temporal_env: object) -> None:
        """The downstream script executes with resolved values and produces correct JSON output."""
        result = await _run_parent_workflow(
            temporal_env,
            workflow_def=_parent_workflow_def_with_downstream(),
            workflow_name="sub-wf-downstream-integration",
        )

        downstream_output = result["activity_outputs"]["downstream_script"]
        expected_child_id = str(uuid5(_SUB_WORKFLOW_NAMESPACE, f"{_PARENT_EXECUTION_ID}:sub_wf_node"))

        assert downstream_output["stdout_json"]["child_id"] == expected_child_id
        assert downstream_output["stdout_json"]["child_status"] == "completed"
        assert downstream_output["stdout_json"]["child_wf_name"] == "test-child-workflow"
        assert downstream_output["stdout_json"]["status_code"] == "0"

    async def test_both_sub_workflow_and_downstream_in_completed(self, temporal_env: object) -> None:
        """Both sub_wf_node and downstream_script appear in completed_activities."""
        result = await _run_parent_workflow(
            temporal_env,
            workflow_def=_parent_workflow_def_with_downstream(),
            workflow_name="sub-wf-downstream-integration",
        )

        assert "sub_wf_node" in result["completed_activities"]
        assert "downstream_script" in result["completed_activities"]
        assert result["failed_activities"] == {}

    async def test_parent_completes_with_downstream(self, temporal_env: object) -> None:
        """Parent workflow with a downstream node completes successfully."""
        result = await _run_parent_workflow(
            temporal_env,
            workflow_def=_parent_workflow_def_with_downstream(),
            workflow_name="sub-wf-downstream-integration",
        )

        assert result["status"] == "completed"


def _parent_workflow_def_with_failing_child() -> dict[str, Any]:
    """Parent workflow where the sub-workflow node targets a failing child."""
    return {
        "schema_version": "2.0.0",
        "triggers": [
            {"id": "trigger", "type": "manual_trigger", "parameters": {}},
        ],
        "nodes": [
            {
                "id": "sub_wf_node",
                "type": "sub_workflow",
                "parameters": {
                    "workflow_id": str(_CHILD_WF_ID),
                    "trigger_node_id": "child_trigger",
                    "input_mapping": {},
                },
            },
        ],
        "edges": [
            {"from": "trigger", "to": "sub_wf_node"},
        ],
    }


def _parent_workflow_def_child_failure_with_downstream() -> dict[str, Any]:
    """Parent with a failing sub-workflow followed by a downstream node."""
    return {
        "schema_version": "2.0.0",
        "triggers": [
            {"id": "trigger", "type": "manual_trigger", "parameters": {}},
        ],
        "nodes": [
            {
                "id": "sub_wf_node",
                "type": "sub_workflow",
                "parameters": {
                    "workflow_id": str(_CHILD_WF_ID),
                    "trigger_node_id": "child_trigger",
                    "input_mapping": {},
                },
            },
            {
                "id": "downstream_script",
                "type": "script",
                "parameters": {"language": "bash", "code": "echo should_not_run"},
            },
        ],
        "edges": [
            {"from": "trigger", "to": "sub_wf_node"},
            {"from": "sub_wf_node", "to": "downstream_script"},
        ],
    }


def _parent_workflow_def_child_failure_cof() -> dict[str, Any]:
    """Parent with a failing sub-workflow that has continue_on_failure=true."""
    return {
        "schema_version": "2.0.0",
        "triggers": [
            {"id": "trigger", "type": "manual_trigger", "parameters": {}},
        ],
        "nodes": [
            {
                "id": "sub_wf_node",
                "type": "sub_workflow",
                "parameters": {
                    "workflow_id": str(_CHILD_WF_ID),
                    "trigger_node_id": "child_trigger",
                    "input_mapping": {},
                },
                "settings": {"continue_on_failure": True},
            },
            {
                "id": "downstream_script",
                "type": "script",
                "parameters": {"language": "bash", "code": "echo ran_after_failure"},
            },
        ],
        "edges": [
            {"from": "trigger", "to": "sub_wf_node"},
            {"from": "sub_wf_node", "to": "downstream_script"},
        ],
    }


@pytest.mark.integration
@pytest.mark.asyncio
class TestSubWorkflowChildFailure:
    """Prove that child failure correctly propagates through the engine's failure path."""

    async def test_child_failure_marks_parent_as_failed(self, temporal_env: object) -> None:
        """When child fails, parent workflow status is 'failed'."""
        result = await _run_parent_workflow(
            temporal_env,
            workflow_def=_parent_workflow_def_with_failing_child(),
            workflow_name="sub-wf-child-failure",
            child_workflow_def=_FAILING_CHILD_WORKFLOW_DEF,
        )

        assert result["status"] == "failed"

    async def test_child_failure_records_sub_wf_node_as_failed(self, temporal_env: object) -> None:
        """The sub_wf_node must appear in failed_activities with a meaningful error."""
        result = await _run_parent_workflow(
            temporal_env,
            workflow_def=_parent_workflow_def_with_failing_child(),
            workflow_name="sub-wf-child-failure",
            child_workflow_def=_FAILING_CHILD_WORKFLOW_DEF,
        )

        assert "sub_wf_node" in result["failed_activities"]
        assert "Sub-workflow failed" in result["failed_activities"]["sub_wf_node"]

    async def test_child_failure_preserves_output_details(self, temporal_env: object) -> None:
        """Failed sub-workflow node's namespace still contains child execution details."""
        result = await _run_parent_workflow(
            temporal_env,
            workflow_def=_parent_workflow_def_with_failing_child(),
            workflow_name="sub-wf-child-failure",
            child_workflow_def=_FAILING_CHILD_WORKFLOW_DEF,
        )

        sub_wf_output = result["activity_outputs"]["sub_wf_node"]
        assert sub_wf_output["Result"]["child_status"] == "failed"
        assert sub_wf_output["StatusCode"] == 1
        expected_child_id = str(uuid5(_SUB_WORKFLOW_NAMESPACE, f"{_PARENT_EXECUTION_ID}:sub_wf_node"))
        assert sub_wf_output["Result"]["child_execution_id"] == expected_child_id

    async def test_child_failure_skips_downstream(self, temporal_env: object) -> None:
        """When child fails with continue_on_failure=false, downstream nodes do not execute."""
        result = await _run_parent_workflow(
            temporal_env,
            workflow_def=_parent_workflow_def_child_failure_with_downstream(),
            workflow_name="sub-wf-child-failure-downstream",
            child_workflow_def=_FAILING_CHILD_WORKFLOW_DEF,
        )

        assert result["status"] == "failed"
        assert "downstream_script" not in result["completed_activities"]
        assert "sub_wf_node" in result["failed_activities"]

    async def test_child_failure_cof_runs_downstream(self, temporal_env: object) -> None:
        """When child fails with continue_on_failure=true, downstream nodes still execute."""
        result = await _run_parent_workflow(
            temporal_env,
            workflow_def=_parent_workflow_def_child_failure_cof(),
            workflow_name="sub-wf-child-failure-cof",
            child_workflow_def=_FAILING_CHILD_WORKFLOW_DEF,
        )

        assert result["status"] == "completed_with_errors"
        assert "sub_wf_node" in result["failed_activities"]
        assert "downstream_script" in result["completed_activities"]

    async def test_child_failure_no_retry(self, temporal_env: object) -> None:
        """Sub-workflow nodes must not be retried (NodeSettingsNoRetry)."""
        result = await _run_parent_workflow(
            temporal_env,
            workflow_def=_parent_workflow_def_with_failing_child(),
            workflow_name="sub-wf-no-retry",
            child_workflow_def=_FAILING_CHILD_WORKFLOW_DEF,
        )

        assert result["status"] == "failed"
        assert "sub_wf_node" in result["failed_activities"]


def _foreach_parent_def() -> dict[str, Any]:
    """Parent: manual trigger -> for_each over two items -> sub_workflow body -> complete."""
    return {
        "schema_version": "2.0.0",
        "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {"id": "loop_node", "type": "loop", "parameters": {"type": "for_each", "items": ["a", "b"]}},
            {
                "id": "sub_wf_node",
                "type": "sub_workflow",
                "parameters": {
                    "workflow_id": str(_CHILD_WF_ID),
                    "trigger_node_id": "child_trigger",
                    "input_mapping": {},
                },
            },
            {"id": "after_loop", "type": "script", "parameters": {"language": "bash", "code": "echo done"}},
        ],
        "edges": [
            {"from": "trigger", "to": "loop_node"},
            {"from": "loop_node", "to": "sub_wf_node", "from_port": "iterate"},
            {"from": "loop_node", "to": "after_loop", "from_port": "complete"},
        ],
    }


def _recording_session_factory(
    created: list[Any],
) -> Callable[..., contextlib.AbstractAsyncContextManager[_MockSession]]:
    """Mock session factory that records every added object (child Execution rows)."""
    mock_workflow = SimpleNamespace(
        id=_CHILD_WF_ID,
        name="test-child-workflow",
        project_id=_CHILD_PROJECT_ID,
        created_by=_CHILD_CREATED_BY,
        published_version_id=_CHILD_VERSION_ID,
        is_enabled=True,
    )
    mock_version = SimpleNamespace(id=_CHILD_VERSION_ID, version=1, workflow_definition=_CHILD_WORKFLOW_DEF)

    class _RecordingMockSession(_MockSession):
        def add(self, obj: object) -> None:
            created.append(obj)

    call_count = 0

    @contextlib.asynccontextmanager
    async def factory() -> AsyncIterator[_MockSession]:
        nonlocal call_count
        call_count += 1
        if call_count % 2 == 1:
            yield _RecordingMockSession(exec_results=[(mock_workflow, mock_version), None])
        else:
            yield _RecordingMockSession()

    return factory


@pytest.mark.integration
@pytest.mark.asyncio
class TestSubWorkflowForEachLifecycle:
    """Prove the engine dispatches iteration-aware sub-workflow invocations inside a for_each."""

    async def test_for_each_dispatches_distinct_children(self, temporal_env: object) -> None:
        """Two for_each iterations each create a distinct child; lineage keeps the canvas id."""
        from temporalio.testing import WorkflowEnvironment

        assert isinstance(temporal_env, WorkflowEnvironment)

        created: list[Any] = []
        setup = SubWorkflowSetupActivity(
            session_factory=_recording_session_factory(created),  # type: ignore[arg-type]
            task_queue=_TASK_QUEUE,
        )
        activities = [
            manual_trigger,
            subworkflow_trigger,
            execute_script_activity,
            fetch_workflow_runtime_settings,
            loop,
            setup.run,
        ]

        async with Worker(
            temporal_env.client,
            task_queue=_TASK_QUEUE,
            workflows=[OrchestratorWorkflow],
            activities=activities,
        ):
            svc = TemporalExecutionService(temporal_client=temporal_env.client, task_queue=_TASK_QUEUE)
            start = await svc.start_workflow(
                workflow_def=_foreach_parent_def(),
                workflow_name="sub-wf-foreach",
                trigger_node_id="trigger",
                include_node_results=True,
                execution_id=_PARENT_EXECUTION_ID,
                workflow_metadata=_parent_workflow_metadata(),
            )
            handle = temporal_env.client.get_workflow_handle(start.temporal_workflow_id)
            result: dict[str, Any] = await asyncio.wait_for(handle.result(), timeout=_WORKFLOW_RESULT_TIMEOUT)

            setup_activity_ids: set[str] = set()
            async for event in handle.fetch_history_events():
                if event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED:
                    scheduled_id = event.activity_task_scheduled_event_attributes.activity_id
                    if scheduled_id.startswith("__internal__setup_sub_workflow_"):
                        setup_activity_ids.add(scheduled_id)

        # The parent waited for both child iterations and completed.
        assert result["status"] == "completed"

        # Each iteration scheduled a distinct setup activity (independently verified via history).
        assert len(setup_activity_ids) == 2

        child_execs = [e for e in created if getattr(e, "execution_metadata", None) is not None]
        child_ids = {e.id for e in child_execs}

        # Each iteration created a distinct child execution (no collision).
        assert len(child_execs) == 2
        assert len(child_ids) == 2

        # The child ids are iteration-aware, not the single non-loop derivation.
        non_loop_id = uuid5(_SUB_WORKFLOW_NAMESPACE, f"{_PARENT_EXECUTION_ID}:sub_wf_node")
        assert non_loop_id not in child_ids

        # Lineage metadata keeps the canvas node id, not the iteration-aware identity.
        for execution in child_execs:
            assert execution.execution_metadata["parent_node_id"] == "sub_wf_node"
