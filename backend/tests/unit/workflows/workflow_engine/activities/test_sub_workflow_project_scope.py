"""Unit tests for the same-project isolation gate on sub-workflow setup.

Scope: project isolation ONLY (ANSTRAT-2347 same-project v1). Execute-permission
(RBAC, AC-3) is intentionally out of scope here and tracked under AAP-91266.

These exercise ``SubWorkflowSetupActivity._assert_child_in_parent_project`` directly
against a fake session, so they need no database and run in the unit suite. End-to-end
coverage (no child inserted on rejection, idempotent/resume path, nested invocations)
lives in the DB-backed integration suite.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine.activities.sub_workflow_setup_activity import (
    SubWorkflowSetupActivity,
)

_SCOPE_ERROR = "SubWorkflowProjectScopeError"


@dataclass
class _FakeParent:
    project_id: UUID


class _FakeSession:
    """Minimal async-session stub: records get() calls, returns a preset parent."""

    def __init__(self, parent: _FakeParent | None) -> None:
        self._parent = parent
        self.get_calls: list[tuple[type, object]] = []

    async def get(self, model: type, pk: object) -> _FakeParent | None:
        self.get_calls.append((model, pk))
        return self._parent


def _activity() -> SubWorkflowSetupActivity:
    # session_factory / task_queue are unused by the gate helper under test.
    return SubWorkflowSetupActivity(session_factory=MagicMock(), task_queue="unit-tq")


async def test_same_project_passes() -> None:
    """A child in the parent's project is allowed; one parent lookup occurs."""
    project = uuid4()
    session: Any = _FakeSession(_FakeParent(project_id=project))

    await _activity()._assert_child_in_parent_project(
        session,
        parent_execution_id=str(uuid4()),
        child_workflow_id=uuid4(),
        child_project_id=project,
        child_execution_id_str="child-1",
    )

    assert len(session.get_calls) == 1


async def test_cross_project_rejected_non_retryable() -> None:
    """A child in a different project is rejected with a non-retryable scope error."""
    session: Any = _FakeSession(_FakeParent(project_id=uuid4()))

    with pytest.raises(ApplicationError) as exc:
        await _activity()._assert_child_in_parent_project(
            session,
            parent_execution_id=str(uuid4()),
            child_workflow_id=uuid4(),
            child_project_id=uuid4(),  # != parent's project
            child_execution_id_str="child-2",
        )

    assert exc.value.type == _SCOPE_ERROR
    assert exc.value.non_retryable is True


async def test_missing_parent_rejected_non_retryable() -> None:
    """A parent execution that cannot be loaded is rejected, not bypassed."""
    session: Any = _FakeSession(None)

    with pytest.raises(ApplicationError) as exc:
        await _activity()._assert_child_in_parent_project(
            session,
            parent_execution_id=str(uuid4()),
            child_workflow_id=uuid4(),
            child_project_id=uuid4(),
            child_execution_id_str="child-3",
        )

    assert exc.value.type == _SCOPE_ERROR
    assert exc.value.non_retryable is True


async def test_invalid_parent_id_rejected_before_db_lookup() -> None:
    """A malformed parent id fails closed before any DB access."""
    session: Any = _FakeSession(_FakeParent(project_id=uuid4()))

    with pytest.raises(ApplicationError) as exc:
        await _activity()._assert_child_in_parent_project(
            session,
            parent_execution_id="not-a-uuid",
            child_workflow_id=uuid4(),
            child_project_id=uuid4(),
            child_execution_id_str="child-4",
        )

    assert exc.value.type == _SCOPE_ERROR
    assert exc.value.non_retryable is True
    assert session.get_calls == []  # fail-closed, no lookup attempted


# ---------------------------------------------------------------------------
# Wiring tests: drive the two real code paths with a mocked session to prove the
# gate runs BEFORE the insert (new path) and on the idempotent resume path. Still
# no database. Full end-to-end coverage lives in the integration suite.
# ---------------------------------------------------------------------------


@dataclass
class _FakeWorkflow:
    project_id: UUID
    is_enabled: bool = True
    name: str = "child-wf"


@dataclass
class _FakeExisting:
    workflow_id: UUID
    workflow_version_id: UUID
    temporal_workflow_id: str = "child-temporal"
    input_data: dict[str, Any] | None = None
    created_at: object = None


class _Result:
    def __init__(self, row: object) -> None:
        self._row = row

    def first(self) -> object:
        return self._row


class _WiringSession:
    """Async-session stub that dispatches get() by model + pk, records add()/commit()."""

    def __init__(
        self,
        *,
        child_execution_id: UUID,
        parent_project: UUID,
        existing: _FakeExisting | None,
        child_workflow: _FakeWorkflow,
        child_version: object,
        pinned_version: object,
    ) -> None:
        self.child_execution_id = child_execution_id
        self.parent_project = parent_project
        self.existing = existing
        self.child_workflow = child_workflow
        self.child_version = child_version
        self.pinned_version = pinned_version
        self.added: list[object] = []
        self.committed = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> bool:
        return False

    async def get(self, model: type, pk: object) -> object:
        name = model.__name__
        if name == "Execution":
            if pk == self.child_execution_id:
                return self.existing
            return _FakeParent(project_id=self.parent_project)  # parent lookup in the gate
        if name == "WorkflowVersion":
            return self.pinned_version
        if name == "Workflow":
            return self.child_workflow
        return None

    async def exec(self, _statement: object) -> _Result:
        return _Result((self.child_workflow, self.child_version))

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.committed = True


def _prepare_kwargs(child_execution_id: UUID, child_workflow_id: UUID) -> dict[str, Any]:
    return {
        "child_workflow_id": child_workflow_id,
        "child_execution_id": child_execution_id,
        "child_execution_id_str": str(child_execution_id),
        "trigger_node_id": "child_trigger",
        "input_mapping": {},
        "parent_execution_id": str(uuid4()),
        "parent_node_id": "sub_wf_node",
        "created_by_user_id": str(uuid4()),
        "created_by_uuid": uuid4(),
        "current_depth": 0,
    }


async def test_new_invocation_cross_project_rejects_before_insert() -> None:
    """New-invocation path: cross-project is rejected and no child Execution is added."""
    child_execution_id = uuid4()
    child_workflow_id = uuid4()
    session: Any = _WiringSession(
        child_execution_id=child_execution_id,
        parent_project=uuid4(),  # parent project
        existing=None,  # -> new-invocation path
        child_workflow=_FakeWorkflow(project_id=uuid4()),  # different project
        child_version=object(),
        pinned_version=object(),
    )
    activity = SubWorkflowSetupActivity(session_factory=lambda: session, task_queue="unit-tq")

    with pytest.raises(ApplicationError) as exc:
        await activity._prepare_child_execution(**_prepare_kwargs(child_execution_id, child_workflow_id))

    assert exc.value.type == _SCOPE_ERROR
    assert exc.value.non_retryable is True
    assert session.added == []  # fail-closed: no child Execution inserted
    assert session.committed is False


async def test_resume_path_cross_project_cannot_bypass() -> None:
    """Idempotent resume path: an existing child is still project-validated, not bypassed."""
    child_execution_id = uuid4()
    child_workflow_id = uuid4()
    session: Any = _WiringSession(
        child_execution_id=child_execution_id,
        parent_project=uuid4(),
        existing=_FakeExisting(workflow_id=child_workflow_id, workflow_version_id=uuid4()),
        child_workflow=_FakeWorkflow(project_id=uuid4()),  # different project from parent
        child_version=object(),
        pinned_version=object(),  # pinned version exists
    )
    activity = SubWorkflowSetupActivity(session_factory=lambda: session, task_queue="unit-tq")

    with pytest.raises(ApplicationError) as exc:
        await activity._prepare_child_execution(**_prepare_kwargs(child_execution_id, child_workflow_id))

    assert exc.value.type == _SCOPE_ERROR
    assert exc.value.non_retryable is True
    assert session.added == []
