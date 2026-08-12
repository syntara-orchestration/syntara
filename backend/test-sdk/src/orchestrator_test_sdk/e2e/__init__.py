"""Syntara E2E test fixtures and helpers."""

from __future__ import annotations

import asyncio
import secrets
import string
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from syntara_api_client.models.workflow_definition import WorkflowDefinition

if TYPE_CHECKING:
    from collections.abc import Callable

_MIN_TEST_PASSWORD_LENGTH = 14
_SAFE_TEST_PASSWORD_PUNCTUATION = "!@#$%^&*(),.?-_"  # noqa: S105

MINIMAL_WORKFLOW_DEFINITION: WorkflowDefinition = WorkflowDefinition.from_dict(
    {
        "schema_version": "2.0.0",
        "name": "e2e-rbac-minimal",
        "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
        "nodes": [],
        "edges": [],
    }
)


def unique_name(base: str) -> str:
    """Generate a unique resource name to avoid conflicts across E2E test runs."""
    return f"{base}-{uuid4().hex[:8]}"


async def async_poll_for(
    condition: Callable[[], bool],
    *,
    timeout: float = 2.0,  # noqa: ASYNC109 — deliberate poll-with-timeout test helper
    interval: float = 0.01,
    description: str = "",
) -> None:
    """Poll until *condition()* returns True, or fail the test.

    Use this instead of bare ``asyncio.sleep`` in tests that wait for
    asynchronous state changes (e.g. a callback counter reaching a
    threshold, a background task finishing, or a connection being removed).
    """
    deadline = asyncio.get_event_loop().time() + timeout
    while not condition():
        if asyncio.get_event_loop().time() >= deadline:
            msg = f"Condition not met within {timeout}s"
            if description:
                msg += f": {description}"
            pytest.fail(msg)
        await asyncio.sleep(interval)


def generate_test_password() -> str:
    """Return a random password that satisfies server complexity rules for E2E tests."""
    password_chars = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice(_SAFE_TEST_PASSWORD_PUNCTUATION),
    ]
    all_chars = string.ascii_letters + string.digits + _SAFE_TEST_PASSWORD_PUNCTUATION
    extra_count = _MIN_TEST_PASSWORD_LENGTH - len(password_chars)
    password_chars.extend(secrets.choice(all_chars) for _ in range(extra_count))
    password_list = list(password_chars)
    secrets.SystemRandom().shuffle(password_list)
    return "".join(password_list)
