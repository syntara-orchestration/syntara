"""Execute-permission enforcement for sub-workflow invocation (DB-backed, AAP-95036).

Exercises ``SubWorkflowSetupActivity.run`` with an injected authorization evaluator
against the real alembic-built schema and verifies the actual database state: an
allowed actor creates and persists the child Execution; a denied actor is rejected
with a non-retryable error and NO child Execution row is created.

Scope: execute-permission (RBAC) only. These require the integration DB harness and
do not run in the plain unit venv. The evaluator decision is stubbed so the test
does not depend on seeded role assignments; project isolation is covered separately
in test_sub_workflow_project_scope.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4, uuid5

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.workflow_engine.activities.sub_workflow_setup_activity import (
    _SUB_WORKFLOW_NAMESPACE,
    SubWorkflowSetupActivity,
)
from tests.integration.helpers.subworkflow import seed_parent_execution

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User

_TASK_QUEUE = "sub-wf-authz"
_NODE_ID = "sub_wf_node"
_AUTHZ_ERROR = "SubWorkflowAuthorizationError"


class _StubEvaluator:
    """Minimal AuthzEvaluator stand-in that forces a fixed allow/deny decision."""

    def __init__(self, *, allow: bool) -> None:
        self._allow = allow

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


def _params(workflow_id: UUID) -> dict[str, Any]:
    return {"workflow_id": str(workflow_id), "trigger_node_id": "child_trigger", "input_mapping": {}}


def _child_id(parent_execution_id: str, invocation_id: str = _NODE_ID) -> UUID:
    return uuid5(_SUB_WORKFLOW_NAMESPACE, f"{parent_execution_id}:{invocation_id}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_authorized_actor_creates_child(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """An allowed actor creates and persists the child Execution."""
    child_wf_id = await _create_published_child(test_db_session, created_by=test_user.id, project_id=test_project_id)
    parent_exec = str(await seed_parent_execution(test_db_session, created_by=test_user.id, project_id=test_project_id))
    setup = SubWorkflowSetupActivity(
        session_factory=test_db_session_factory, task_queue=_TASK_QUEUE, evaluator=_StubEvaluator(allow=True)
    )

    result = await setup.run(_params(child_wf_id), parent_exec, _NODE_ID, str(test_user.id), 0)

    async with test_db_session_factory() as session:
        child = await session.get(Execution, UUID(result["execution_id"]))
    assert child is not None
    assert child.status == ExecutionStatus.PENDING


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unauthorized_actor_denied_before_child_creation(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """A denied actor is rejected with a non-retryable error and no child row is written."""
    child_wf_id = await _create_published_child(test_db_session, created_by=test_user.id, project_id=test_project_id)
    parent_exec = str(await seed_parent_execution(test_db_session, created_by=test_user.id, project_id=test_project_id))
    setup = SubWorkflowSetupActivity(
        session_factory=test_db_session_factory, task_queue=_TASK_QUEUE, evaluator=_StubEvaluator(allow=False)
    )

    with pytest.raises(ApplicationError) as exc:
        await setup.run(_params(child_wf_id), parent_exec, _NODE_ID, str(test_user.id), 0)

    assert exc.value.type == _AUTHZ_ERROR
    assert exc.value.non_retryable is True
    async with test_db_session_factory() as session:
        assert await session.get(Execution, _child_id(parent_exec)) is None
