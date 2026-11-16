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
from structlog.testing import capture_logs
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_authorized_actor_links_child_to_parent(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """An allowed actor's child Execution carries parent lineage metadata (AC: authorized invocation links child)."""
    child_wf_id = await _create_published_child(test_db_session, created_by=test_user.id, project_id=test_project_id)
    parent_exec = str(await seed_parent_execution(test_db_session, created_by=test_user.id, project_id=test_project_id))
    setup = SubWorkflowSetupActivity(
        session_factory=test_db_session_factory, task_queue=_TASK_QUEUE, evaluator=_StubEvaluator(allow=True)
    )

    result = await setup.run(_params(child_wf_id), parent_exec, _NODE_ID, str(test_user.id), 0)

    async with test_db_session_factory() as session:
        child = await session.get(Execution, UUID(result["execution_id"]))
    assert child is not None
    # Lineage points back at the authoritative parent execution + canvas node id.
    metadata = child.execution_metadata
    assert metadata is not None
    assert metadata["parent_execution_id"] == parent_exec
    assert metadata["parent_node_id"] == _NODE_ID
    # DB ownership is the propagated top-level initiator (the authorized actor).
    assert str(child.created_by) == str(test_user.id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unauthorized_actor_denied_before_trigger_validation_detail(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """Security-ordering regression: an unauthorized caller gets a generic authz denial, not trigger detail.

    The child is published and enabled, but the invocation targets a trigger node that does not exist. If
    trigger validation ran before authorization, the caller would receive ``TriggerNotFoundError`` naming
    the missing trigger. Authorization is enforced first (in the create path authz precedes
    ``_validate_trigger`` / ``_validate_input``), so the caller must receive the sanitized
    ``SubWorkflowAuthorizationError`` and learn nothing child-specific (AAP-91266 decision #3).

    Note: a "published but disabled" child cannot exist -- the
    ``ck_workflows_is_enabled_published_version_id`` constraint ties ``is_enabled`` to having a published
    version, and the setup activity's resolution joins on ``published_version_id`` (an unpublished/disabled
    child fails earlier with ``WorkflowNotPublishedError``). The reachable child-detail disclosures after
    authorization are therefore trigger and input validation.
    """
    child_wf_id = await _create_published_child(test_db_session, created_by=test_user.id, project_id=test_project_id)
    parent_exec = str(await seed_parent_execution(test_db_session, created_by=test_user.id, project_id=test_project_id))
    setup = SubWorkflowSetupActivity(
        session_factory=test_db_session_factory, task_queue=_TASK_QUEUE, evaluator=_StubEvaluator(allow=False)
    )
    # Target a trigger that does not exist: trigger validation would raise TriggerNotFoundError naming it.
    missing_trigger = "nonexistent_trigger"
    bad_params: dict[str, Any] = {
        "workflow_id": str(child_wf_id),
        "trigger_node_id": missing_trigger,
        "input_mapping": {},
    }

    with pytest.raises(ApplicationError) as exc:
        await setup.run(bad_params, parent_exec, _NODE_ID, str(test_user.id), 0)

    # Authorization denial wins over the trigger-not-found detail: the caller cannot learn whether the
    # trigger exists, nor the child workflow id.
    assert exc.value.type == _AUTHZ_ERROR
    assert exc.value.type != "TriggerNotFoundError"
    assert exc.value.non_retryable is True
    message = str(exc.value)
    assert missing_trigger not in message
    assert str(child_wf_id) not in message
    # Nothing is persisted for an unauthorized caller.
    async with test_db_session_factory() as session:
        assert await session.get(Execution, _child_id(parent_exec)) is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_denied_message_is_sanitized_and_logs_diagnostics(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """AAP-95043 (real DB): policy deny gives a sanitized message with diagnostics in the protected log.

    The raised (and persisted) message discloses no child metadata in the message or on the error
    details -- it is read by principals who may lack workflow:read on the child (SDP R5) -- while the
    protected structured diagnostics (child id/name, project_id, normalized denial_reason) are emitted
    to the authorization-denial log.
    """
    child_wf_id = await _create_published_child(test_db_session, created_by=test_user.id, project_id=test_project_id)
    parent_exec = str(await seed_parent_execution(test_db_session, created_by=test_user.id, project_id=test_project_id))
    async with test_db_session_factory() as session:
        child = await session.get(Workflow, child_wf_id)
    assert child is not None
    setup = SubWorkflowSetupActivity(
        session_factory=test_db_session_factory, task_queue=_TASK_QUEUE, evaluator=_StubEvaluator(allow=False)
    )

    with capture_logs() as logs, pytest.raises(ApplicationError) as exc:
        await setup.run(_params(child_wf_id), parent_exec, _NODE_ID, str(test_user.id), 0)

    # Sanitized, viewer-independent message (persisted into the parent result; read by principals who
    # may lack workflow:read on the child, so it must not disclose child metadata -- SDP R5).
    assert exc.value.type == _AUTHZ_ERROR
    assert exc.value.message == "Not authorized to run child workflow."
    message = exc.value.message or ""
    assert child.name not in message
    assert str(child_wf_id) not in message
    assert str(child.project_id) not in message
    # Sensitive child metadata must not ride on the Temporal error details either.
    details_text = str(exc.value.details)
    assert child.name not in details_text
    assert str(child.project_id) not in details_text

    # Protected structured diagnostics are emitted (internal sink only).
    entry = next(log for log in logs if log["event"] == "Sub-workflow invocation authorization denied")
    assert entry["child_workflow_id"] == str(child_wf_id)
    assert entry["child_workflow_name"] == child.name
    assert entry["project_id"] == str(child.project_id)
    assert entry["denial_reason"] == "policy_deny"
