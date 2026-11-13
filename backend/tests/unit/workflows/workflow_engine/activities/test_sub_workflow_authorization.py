"""Unit tests for sub-workflow child-invocation authorization (AAP-95036).

Exercises ``authorize_child_invocation`` in isolation with a mocked session and a
patched authorization engine. These prove request construction, deny/transient
classification, and fail-closed behavior; they do NOT prove PostgreSQL persistence
or real Temporal activity execution (see the integration tier for that).
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from temporalio.exceptions import ApplicationError

from syntara.authz.engine import AuthzResult
from syntara.workflows.workflow_engine.activities.sub_workflow_setup_activity import (
    authorize_child_invocation,
)

_AUTHORIZE = "syntara.authz.engine.authorize"


def _allow() -> AuthzResult:
    return AuthzResult(
        allowed=True, denied=False, matched_policy="p", denial_reason="", denied_by="", effective_policies=[]
    )


def _deny() -> AuthzResult:
    return AuthzResult(
        allowed=False, denied=True, matched_policy="", denial_reason="policy_deny", denied_by="p", effective_policies=[]
    )


def _user() -> MagicMock:
    user = MagicMock()
    user.labels = {}
    user.authz_metadata = {}
    user.is_enabled = True
    return user


def _child_workflow() -> MagicMock:
    wf = MagicMock()
    wf.id = uuid4()
    wf.project_id = uuid4()
    return wf


def _session(*, project_name: str = "child-project", user: object | None = None) -> MagicMock:
    session = MagicMock()
    exec_result = MagicMock()
    exec_result.first.return_value = project_name
    session.exec = AsyncMock(return_value=exec_result)
    session.get = AsyncMock(return_value=user)
    return session


@pytest.mark.asyncio
async def test_allows_when_engine_allows() -> None:
    session = _session(user=_user())
    with patch(_AUTHORIZE, AsyncMock(return_value=_allow())):
        await authorize_child_invocation(session, MagicMock(), actor_id=uuid4(), child_workflow=_child_workflow())


@pytest.mark.asyncio
async def test_deny_raises_non_retryable() -> None:
    session = _session(user=_user())
    with patch(_AUTHORIZE, AsyncMock(return_value=_deny())), pytest.raises(ApplicationError) as exc:
        await authorize_child_invocation(session, MagicMock(), actor_id=uuid4(), child_workflow=_child_workflow())
    assert exc.value.non_retryable is True
    assert exc.value.type == "SubWorkflowAuthorizationError"


@pytest.mark.asyncio
async def test_unknown_principal_fails_closed_without_calling_engine() -> None:
    session = _session(user=None)  # session.get(User, ...) -> None
    engine = AsyncMock(return_value=_allow())
    with patch(_AUTHORIZE, engine), pytest.raises(ApplicationError) as exc:
        await authorize_child_invocation(session, MagicMock(), actor_id=uuid4(), child_workflow=_child_workflow())
    assert exc.value.non_retryable is True
    assert exc.value.type == "SubWorkflowAuthorizationError"
    engine.assert_not_awaited()


@pytest.mark.asyncio
async def test_authorizes_actor_against_child_project() -> None:
    captured: dict[str, object] = {}

    async def _fake_authorize(session: object, evaluator: object, request: object) -> AuthzResult:
        captured["request"] = request
        return _allow()

    actor = uuid4()
    with patch(_AUTHORIZE, _fake_authorize):
        await authorize_child_invocation(
            _session(project_name="child-project", user=_user()),
            MagicMock(),
            actor_id=actor,
            child_workflow=_child_workflow(),
        )
    request = captured["request"]
    assert request.user_id == actor
    assert request.action == "run"
    assert request.resource_type == "execution"
    # Project comes from the authoritative workflow record, never caller input.
    assert request.resource_project == "child-project"


@pytest.mark.asyncio
async def test_transient_engine_error_propagates_and_is_not_swallowed() -> None:
    async def _boom(*_args: object, **_kwargs: object) -> AuthzResult:
        msg = "authorization evaluator unavailable"
        raise RuntimeError(msg)

    session = _session(user=_user())
    with patch(_AUTHORIZE, _boom), pytest.raises(RuntimeError):
        await authorize_child_invocation(session, MagicMock(), actor_id=uuid4(), child_workflow=_child_workflow())


@pytest.mark.asyncio
async def test_disabled_principal_fails_closed_without_calling_engine() -> None:
    disabled = _user()
    disabled.is_enabled = False  # deactivated user: sessions revoked, role assignments remain
    session = _session(user=disabled)
    engine = AsyncMock(return_value=_allow())
    with patch(_AUTHORIZE, engine), pytest.raises(ApplicationError) as exc:
        await authorize_child_invocation(session, MagicMock(), actor_id=uuid4(), child_workflow=_child_workflow())
    assert exc.value.non_retryable is True
    assert exc.value.type == "SubWorkflowAuthorizationError"
    engine.assert_not_awaited()
