"""Shared helpers for asserting events captured by the mock Segment service."""

from __future__ import annotations

import os
import time
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import httpx
import pytest

if TYPE_CHECKING:
    from uuid import UUID

SEGMENT_EVENT_TIMEOUT_SECONDS = 30


def require_segment_server_url() -> str:
    """Require the mock Segment URL configured by the full-stack E2E runner."""
    segment_server_url = os.environ.get("SEGMENT_SERVER_URL")
    if not segment_server_url:
        pytest.skip(
            "SEGMENT_SERVER_URL not set — telemetry E2E requires the mock Segment server",
            allow_module_level=True,
        )
    return segment_server_url


def get_segment_events(segment_server_url: str, **params: str) -> list[dict[str, Any]]:
    """Fetch captured Segment events and validate the mock server response."""
    response = httpx.get(
        f"{segment_server_url.rstrip('/')}/captured-events",
        params=params,
        timeout=5,
    )
    assert response.status_code == HTTPStatus.OK, (
        f"Segment /captured-events returned {response.status_code}: {response.text}"
    )
    events = response.json()
    assert isinstance(events, list), f"Expected Segment events list, got {events!r}"
    assert all(isinstance(event, dict) for event in events), f"Expected event objects, got {events!r}"
    return events


def wait_for_segment_event(
    segment_server_url: str,
    event_type: str,
    execution_id: UUID,
    *,
    timeout: int = SEGMENT_EVENT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Poll until Segment captures exactly one event of this type for an execution."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        events = get_segment_events(
            segment_server_url,
            event_type=event_type,
            execution_id=str(execution_id),
        )
        if events:
            assert len(events) == 1, f"Expected one {event_type} event for {execution_id}, got {events!r}"
            return events[0]
        time.sleep(0.25)

    pytest.fail(f"Segment did not receive {event_type} for execution {execution_id} within {timeout}s")
