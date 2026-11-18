"""Unit tests for sub-workflow child-invocation authorization (AAP-95036).

Exercises ``authorize_child_invocation`` in isolation with a mocked session and a
patched authorization engine. These prove request construction, deny/transient
classification, and fail-closed behavior; they do NOT prove PostgreSQL persistence
or real Temporal activity execution (see the integration tier for that).
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from structlog.testing import capture_logs
from temporalio.exceptions import ApplicationError

from syntara.authz.engine import AuthzRequest, AuthzResult
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
    wf.name = "secret-child-workflow"
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
    captured: dict[str, AuthzRequest] = {}

    async def _fake_authorize(session: object, evaluator: object, request: AuthzRequest) -> AuthzResult:
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


# ---------------------------------------------------------------------------
# Authorization denial: sanitized message, child details only in diagnostics
# ---------------------------------------------------------------------------

_SANITIZED_DENY = "Not authorized to run child workflow."
_DENIAL_EVENT = "Sub-workflow invocation authorization denied"


def _assert_message_hides_child_metadata(exc: ApplicationError, child: MagicMock) -> None:
    """The raised message must not disclose child metadata to the caller."""
    message = exc.message or ""
    assert child.name not in message
    assert str(child.id) not in message
    assert str(child.project_id) not in message
    # Child metadata must not ride on the error details either.
    details_text = str(exc.details)
    assert child.name not in details_text
    assert str(child.project_id) not in details_text


@pytest.mark.asyncio
async def test_policy_deny_sanitized_message_and_structured_diagnostics() -> None:
    """Explicit policy deny: sanitized message, metadata only in the structured log, denial_reason=policy_deny."""
    child = _child_workflow()
    session = _session(user=_user())
    with capture_logs() as logs, patch(_AUTHORIZE, AsyncMock(return_value=_deny())):
        with pytest.raises(ApplicationError) as exc:
            await authorize_child_invocation(session, MagicMock(), actor_id=uuid4(), child_workflow=child)

    assert exc.value.type == "SubWorkflowAuthorizationError"
    assert exc.value.non_retryable is True
    assert exc.value.message == _SANITIZED_DENY
    _assert_message_hides_child_metadata(exc.value, child)

    entry = next(log for log in logs if log["event"] == _DENIAL_EVENT)
    assert entry["child_workflow_id"] == str(child.id)
    assert entry["child_workflow_name"] == child.name
    assert entry["project_id"] == str(child.project_id)
    assert entry["denial_reason"] == "policy_deny"


@pytest.mark.asyncio
async def test_missing_principal_denial_reason_and_sanitized_message() -> None:
    """Missing principal: denial_reason=principal_missing; message sanitized and viewer-independent."""
    child = _child_workflow()
    session = _session(user=None)
    with capture_logs() as logs:
        with pytest.raises(ApplicationError) as exc:
            await authorize_child_invocation(session, MagicMock(), actor_id=uuid4(), child_workflow=child)

    assert exc.value.type == "SubWorkflowAuthorizationError"
    assert exc.value.non_retryable is True
    _assert_message_hides_child_metadata(exc.value, child)

    entry = next(log for log in logs if log["event"] == _DENIAL_EVENT)
    assert entry["denial_reason"] == "principal_missing"
    assert entry["child_workflow_id"] == str(child.id)
    assert entry["child_workflow_name"] == child.name
    assert entry["project_id"] == str(child.project_id)


@pytest.mark.asyncio
async def test_disabled_principal_denial_reason_and_sanitized_message() -> None:
    """Disabled principal: denial_reason=principal_disabled; message sanitized and viewer-independent."""
    child = _child_workflow()
    disabled = _user()
    disabled.is_enabled = False
    session = _session(user=disabled)
    with capture_logs() as logs:
        with pytest.raises(ApplicationError) as exc:
            await authorize_child_invocation(session, MagicMock(), actor_id=uuid4(), child_workflow=child)

    assert exc.value.type == "SubWorkflowAuthorizationError"
    _assert_message_hides_child_metadata(exc.value, child)

    entry = next(log for log in logs if log["event"] == _DENIAL_EVENT)
    assert entry["denial_reason"] == "principal_disabled"
    assert entry["child_workflow_name"] == child.name
