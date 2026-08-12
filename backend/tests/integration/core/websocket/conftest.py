"""Shared fixtures for core WebSocket integration tests.

These tests exercise message handling, validation, and channel behavior using
the example component. Auth guards are bypassed since auth is tested separately
in tests/integration/websocket/test_websocket_auth.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

from syntara.core.models import User

_FAKE_USER = User(
    id=uuid4(),
    username="ws-test-bypass",
    email="ws-test-bypass@example.com",
    first_name="Test",
    is_enabled=True,
)


@pytest.fixture(autouse=True)
def _bypass_websocket_auth() -> Generator[None, None, None]:
    """Bypass WebSocket auth and authz guards for example-component tests."""
    with (
        patch(
            "syntara.core.websocket.endpoint_factory._authenticate_websocket",
            AsyncMock(return_value=_FAKE_USER),
        ),
        patch(
            "syntara.core.websocket.endpoint_factory._check_websocket_authorization",
            AsyncMock(return_value=True),
        ),
    ):
        yield
