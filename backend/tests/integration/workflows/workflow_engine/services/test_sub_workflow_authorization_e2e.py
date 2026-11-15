"""Temporal-backed end-to-end authorization tests for Sub-workflow Reference Mode (AAP-91266).

Unlike ``test_sub_workflow_authorization.py`` (which drives the setup activity directly against
the real DB) and ``test_sub_workflow_integration.py`` (which runs the full parent orchestrator with
a *mocked* session), these tests run the **full parent ``OrchestratorWorkflow`` through a real
``WorkflowEnvironment``** while the setup activity is wired to the **real integration DB** and a
stubbed authorization evaluator. They prove the complete runtime path end to end:

    parent orchestrator -> sub_workflow node -> setup activity -> real authz engine (stubbed decision)
    -> real DB side effects.

What they validate, as *persisted application-level state* rather than mere Temporal completion:

* Authorized invocation: the parent completes, the sub_workflow node succeeds, and a child
  ``Execution`` row is created in the DB and linked to the parent execution (lineage metadata).
* Unauthorized invocation: the parent run fails -- run status ``failed`` and the sub_workflow node
  in ``failed_activities`` -- and **no child ``Execution`` row exists** in the DB after the denial.
  Note on what is asserted: the parent-node failure is read from the orchestrator *result*
  (``_build_result``), i.e. the Temporal workflow result, not a DB-persisted parent activity row --
  this harness seeds the parent as RUNNING and does not run the parent-node status finalizer (that
  path is covered directly in ``test_finalize_sub_workflow_status.py``). The *persisted*
  application-level assertion here is specifically the **absence of the child Execution row**, which
  is the authoritative DB side effect a denial must prevent.

Scope: these require the integration DB harness **and** a Temporal test server, so they do not run
in the plain unit venv or without Docker; they execute in CI / on a machine with both available.
The evaluator decision is stubbed so the test does not depend on seeded role assignments; the
missing/disabled-principal and generic-deny ordering are covered at the activity level in
``test_sub_workflow_authorization.py``.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4, uuid5

import pytest
from temporalio.worker import Worker

from syntara.workflows.models.execution import Execution
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.workflow_engine.activities.manual_trigger import manual_trigger
from syntara.workflows.workflow_engine.activities.runtime_settings_activity import (
    fetch_workflow_runtime_settings,
)
from syntara.workflows.workflow_engine.activities.script_activity import execute_script_activity
from syntara.workflows.workflow_engine.activities.sub_workflow_setup_activity import (
    _SUB_WORKFLOW_NAMESPACE,
    SubWorkflowSetupActivity,
)
from syntara.workflows.workflow_engine.activities.subworkflow_trigger import subworkflow_trigger
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.services.temporal_execution_service import (
    TemporalExecutionService,
)
from tests.integration.helpers.subworkflow import seed_parent_execution

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession
    from temporalio.testing import WorkflowEnvironment

    from syntara.core.models import User

_TASK_QUEUE = "sub-wf-authz-e2e"
_NODE_ID = "sub_wf_node"
_WORKFLOW_RESULT_TIMEOUT = 30


class _StubEvaluator:
    """Minimal AuthzEvaluator stand-in that forces a fixed allow/deny decision."""

    def __init__(self, *, allow: bool) -> None:
        self._allow = allow

    def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def health(self) -> bool:
        return True

    def evaluate(self, authz_input: dict[str, Any]) -> dict[str, Any]:
        if self._allow:
            return {"allow": True, "deny": False, "matched_policy": "test-allow"}
        return {"allow": False, "deny": True, "denied_by": "test-deny", "denial_reason": "policy_deny"}


def _child_def() -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "triggers": [{"id": "child_trigger", "type": "subworkflow_trigger", "parameters": {}}],
        "nodes": [{"id": "child_script", "type": "script", "parameters": {"language": "bash", "code": "echo ok"}}],
        "edges": [{"from": "child_trigger", "to": "child_script"}],
    }


async def _create_published_child(session: AsyncSession, *, created_by: UUID, project_id: UUID) -> UUID:
    workflow_id = uuid4()
    session.add(
        Workflow(id=workflow_id, name=f"child-{workflow_id.hex[:8]}", created_by=created_by, project_id=project_id)
    )
    await session.flush()
    version_id = uuid4()
    session.add(
        WorkflowVersion(
            id=version_id,
            workflow_id=workflow_id,
            version=1,
            schema_version="2.0.0",
            workflow_definition=_child_def(),
            created_by=created_by,
        )
    )
    await session.flush()
    workflow = await session.get(Workflow, workflow_id)
    assert workflow is not None
    workflow.is_enabled = True
    workflow.published_version_id = version_id
    await session.commit()
    return workflow_id


def _parent_def(child_wf_id: UUID) -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {
                "id": _NODE_ID,
                "type": "sub_workflow",
                "parameters": {
                    "workflow_id": str(child_wf_id),
                    "trigger_node_id": "child_trigger",
                    "input_mapping": {},
                },
            },
        ],
        "edges": [{"from": "trigger", "to": _NODE_ID}],
    }


def _parent_metadata(*, parent_exec: str, user_id: str, project_id: UUID) -> dict[str, Any]:
    """Build workflow_metadata so the parent propagates ``created_by_user_id`` to the setup activity.

    ``execution.id`` must equal the seeded parent Execution row id (the setup activity's same-project
    gate loads it by that id), and ``created_by_user_id`` is the propagated runtime initiator the
    authorization check authorizes.
    """
    return {
        "workflow_context": {
            "workflow": {
                "name": "parent-wf",
                "id": str(uuid4()),
                "version": 1,
                "published": True,
                "author": "test-author",
                "project_id": str(project_id),
            },
            "execution": {
                "id": parent_exec,
                "mode": "manual",
                "created_by": user_id,
                "created_by_user_id": user_id,
                "created_at": "2026-01-01T00:00:00Z",
                "workflow_version_id": str(uuid4()),
            },
        },
    }


def _child_execution_id(parent_exec: str) -> UUID:
    return uuid5(_SUB_WORKFLOW_NAMESPACE, f"{parent_exec}:{_NODE_ID}")


async def _run_parent(
    temporal_env: WorkflowEnvironment,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    evaluator: _StubEvaluator,
    child_wf_id: UUID,
    parent_exec: str,
    user_id: str,
    project_id: UUID,
    workflow_name: str,
) -> dict[str, Any]:
    """Run the full parent orchestrator against the real DB and return its raw result."""
    setup = SubWorkflowSetupActivity(
        session_factory=session_factory,
        task_queue=_TASK_QUEUE,
        evaluator=evaluator,
    )
    activities: list[Callable[..., Any]] = [
        manual_trigger,
        subworkflow_trigger,
        execute_script_activity,
        fetch_workflow_runtime_settings,
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
            workflow_def=_parent_def(child_wf_id),
            workflow_name=workflow_name,
            trigger_node_id="trigger",
            include_node_results=True,
            execution_id=parent_exec,
            workflow_metadata=_parent_metadata(parent_exec=parent_exec, user_id=user_id, project_id=project_id),
        )
        handle = temporal_env.client.get_workflow_handle(start.temporal_workflow_id)
        raw: dict[str, Any] = await asyncio.wait_for(handle.result(), timeout=_WORKFLOW_RESULT_TIMEOUT)
        return raw


@pytest.mark.integration
@pytest.mark.asyncio
async def test_authorized_invocation_creates_and_links_child_e2e(
    temporal_env: WorkflowEnvironment,
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """Authorized E2E: parent completes and a linked child Execution row is persisted."""
    child_wf_id = await _create_published_child(test_db_session, created_by=test_user.id, project_id=test_project_id)
    parent_exec = str(await seed_parent_execution(test_db_session, created_by=test_user.id, project_id=test_project_id))

    result = await _run_parent(
        temporal_env,
        session_factory=test_db_session_factory,
        evaluator=_StubEvaluator(allow=True),
        child_wf_id=child_wf_id,
        parent_exec=parent_exec,
        user_id=str(test_user.id),
        project_id=test_project_id,
        workflow_name="sub-wf-authz-e2e-allow",
    )

    assert result["status"] == "completed"
    assert _NODE_ID in result["completed_nodes"]
    assert result["failed_activities"] == {}

    # Persisted application-level state: the child Execution row exists and is linked to the parent.
    async with test_db_session_factory() as session:
        child = await session.get(Execution, _child_execution_id(parent_exec))
    assert child is not None, "authorized invocation must persist a child Execution row"
    metadata = child.execution_metadata
    assert metadata is not None
    assert metadata["parent_execution_id"] == parent_exec
    assert metadata["parent_node_id"] == _NODE_ID
    assert str(child.created_by) == str(test_user.id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unauthorized_invocation_fails_parent_and_creates_no_child_e2e(
    temporal_env: WorkflowEnvironment,
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """Unauthorized E2E: the parent run fails and no child Execution row is created.

    Drives the full parent orchestrator through a real Temporal environment with a deny evaluator.
    The non-retryable authorization error raised by the setup activity propagates to the node
    framework, so the parent run status is ``failed`` and the sub_workflow node is recorded in
    ``failed_activities``.

    What this asserts, precisely: the parent-node failure (``status`` / ``failed_activities``) is read
    from the orchestrator *result* -- the Temporal workflow result produced by ``_build_result`` -- and
    is NOT a DB-persisted parent activity-execution row. This harness seeds the parent as RUNNING and
    does not run the parent-node status finalizer, so it does not claim persisted parent-node status;
    DB persistence of the sub_workflow node status is covered separately in
    ``test_finalize_sub_workflow_status.py``. The *persisted* application-level state verified here is
    the **absence of a child Execution row** after denial, asserted directly against the real database.
    """
    child_wf_id = await _create_published_child(test_db_session, created_by=test_user.id, project_id=test_project_id)
    parent_exec = str(await seed_parent_execution(test_db_session, created_by=test_user.id, project_id=test_project_id))

    result = await _run_parent(
        temporal_env,
        session_factory=test_db_session_factory,
        evaluator=_StubEvaluator(allow=False),
        child_wf_id=child_wf_id,
        parent_exec=parent_exec,
        user_id=str(test_user.id),
        project_id=test_project_id,
        workflow_name="sub-wf-authz-e2e-deny",
    )

    # Orchestrator RESULT (Temporal workflow result, not a persisted parent-node row): node failed.
    assert result["status"] == "failed"
    assert _NODE_ID in result["failed_activities"]
    assert _NODE_ID not in result["completed_nodes"]

    # Persisted application-level state: authorization denial creates NO child Execution row.
    async with test_db_session_factory() as session:
        assert await session.get(Execution, _child_execution_id(parent_exec)) is None
