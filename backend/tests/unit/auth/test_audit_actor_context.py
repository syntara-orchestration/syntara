"""Tests for verified actor context propagation from auth dependencies.

Verifies that auth dependency helpers write to both ``actor_context_var``
(for in-request use) and ``request.state`` via ``VERIFIED_ACTOR_STATE_KEY``
(to survive the ``BaseHTTPMiddleware`` task boundary).
"""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from syntara.audit.emitter import VERIFIED_ACTOR_STATE_KEY, AuditActorContext, actor_context_var
from syntara.auth.dependencies import (
    _set_verified_actor_context_from_payload,
    _set_verified_actor_context_from_user,
)
from syntara.auth.services.token_service import TokenPayload
from syntara.core.models.principal import PrincipalType
from syntara.core.models.user import User


def _make_request() -> MagicMock:
    """Create a mock Request with a real state namespace."""
    request = MagicMock()
    request.state = MagicMock()
    delattr(request.state, VERIFIED_ACTOR_STATE_KEY)
    return request


class TestSetVerifiedActorContextFromUser:
    """_set_verified_actor_context_from_user sets both ContextVar and request.state."""

    def setup_method(self) -> None:
        self.token = actor_context_var.set(None)

    def teardown_method(self) -> None:
        actor_context_var.reset(self.token)

    def test_sets_context_var(self) -> None:
        user = User(id=uuid4(), username="testuser", email="t@t.com", first_name="T", is_enabled=True)
        request = _make_request()

        _set_verified_actor_context_from_user(request, user)

        ctx = actor_context_var.get()
        assert ctx is not None
        assert ctx.actor_id == user.id
        assert ctx.actor_username == user.username

    def test_sets_request_state(self) -> None:
        user = User(id=uuid4(), username="testuser", email="t@t.com", first_name="T", is_enabled=True)
        request = _make_request()

        _set_verified_actor_context_from_user(request, user)

        state_ctx = getattr(request.state, VERIFIED_ACTOR_STATE_KEY)
        assert isinstance(state_ctx, AuditActorContext)
        assert state_ctx.actor_id == user.id
        assert state_ctx.actor_username == user.username

    def test_context_var_and_state_are_same_object(self) -> None:
        """Both paths receive the identical AuditActorContext instance."""
        user = User(id=uuid4(), username="testuser", email="t@t.com", first_name="T", is_enabled=True)
        request = _make_request()

        _set_verified_actor_context_from_user(request, user)

        assert actor_context_var.get() is getattr(request.state, VERIFIED_ACTOR_STATE_KEY)

    def test_user_actor_type(self) -> None:
        user = User(id=uuid4(), username="regular", email="r@r.com", first_name="R", is_enabled=True)
        request = _make_request()

        _set_verified_actor_context_from_user(request, user)

        ctx = actor_context_var.get()
        assert ctx is not None
        assert ctx.actor_type == PrincipalType.USER

    def test_service_account_actor_type(self) -> None:
        user = User(id=uuid4(), username="sa-user", email="s@s.com", first_name="S", is_enabled=True)
        object.__setattr__(user, "__principal_type__", PrincipalType.SERVICE_ACCOUNT)
        request = _make_request()

        _set_verified_actor_context_from_user(request, user)

        ctx = actor_context_var.get()
        assert ctx is not None
        assert ctx.actor_type == PrincipalType.SERVICE_ACCOUNT


class TestSetVerifiedActorContextFromPayload:
    """_set_verified_actor_context_from_payload sets both ContextVar and request.state."""

    def setup_method(self) -> None:
        self.token = actor_context_var.set(None)

    def teardown_method(self) -> None:
        actor_context_var.reset(self.token)

    @staticmethod
    def _make_payload(
        *,
        sub: str | None = None,
        preferred_username: str | None = None,
        token_type: str = "access",  # noqa: S107
    ) -> TokenPayload:
        from datetime import UTC, datetime

        return TokenPayload(
            sub=sub or str(uuid4()),
            iss="https://test.example.com",
            iat=datetime.now(UTC),
            exp=datetime.now(UTC),
            token_type=token_type,
            preferred_username=preferred_username,
        )

    def test_sets_context_var(self) -> None:
        user_id = str(uuid4())
        payload = self._make_payload(sub=user_id, preferred_username="payload-user")
        request = _make_request()

        _set_verified_actor_context_from_payload(request, payload)

        ctx = actor_context_var.get()
        assert ctx is not None
        assert str(ctx.actor_id) == user_id
        assert ctx.actor_username == "payload-user"

    def test_sets_request_state(self) -> None:
        payload = self._make_payload(preferred_username="payload-user")
        request = _make_request()

        _set_verified_actor_context_from_payload(request, payload)

        state_ctx = getattr(request.state, VERIFIED_ACTOR_STATE_KEY)
        assert isinstance(state_ctx, AuditActorContext)
        assert state_ctx.actor_username == "payload-user"

    def test_context_var_and_state_are_same_object(self) -> None:
        payload = self._make_payload()
        request = _make_request()

        _set_verified_actor_context_from_payload(request, payload)

        assert actor_context_var.get() is getattr(request.state, VERIFIED_ACTOR_STATE_KEY)

    def test_user_token_type(self) -> None:
        payload = self._make_payload(token_type="access")  # noqa: S106
        request = _make_request()

        _set_verified_actor_context_from_payload(request, payload)

        ctx = actor_context_var.get()
        assert ctx is not None
        assert ctx.actor_type == PrincipalType.USER

    @pytest.mark.parametrize("token_type", ["service_account"])
    def test_service_account_token_type(self, token_type: str) -> None:
        payload = self._make_payload(token_type=token_type)
        request = _make_request()

        _set_verified_actor_context_from_payload(request, payload)

        ctx = actor_context_var.get()
        assert ctx is not None
        assert ctx.actor_type == PrincipalType.SERVICE_ACCOUNT
