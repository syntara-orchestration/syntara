"""Tests for E2E helper diagnostics."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from _pytest.outcomes import Failed
from orchestrator_test_sdk.e2e import helpers


def test_poll_execution_timeout_includes_activity_state(monkeypatch):
    activity = SimpleNamespace(
        activity_id="loop_body",
        status=SimpleNamespace(value="running"),
        output_data={"return_code": None},
        error_details="work item not delivered",
    )
    execution = SimpleNamespace(
        status=helpers.ExecutionStatus.RUNNING,
        error_details=None,
        activities=[activity],
    )
    response = SimpleNamespace(assert_and_get=lambda: execution)
    api = SimpleNamespace(executions=SimpleNamespace(get=lambda **_kwargs: response))

    monkeypatch.setattr(helpers, "_retry_api_call", lambda fn: fn())
    monkeypatch.setattr(helpers.time, "sleep", lambda _seconds: None)

    with pytest.raises(Failed, match=r"loop_body.*running.*work item not delivered"):
        helpers.poll_execution(api, "00000000-0000-0000-0000-000000000001", timeout=1, interval=1)


def test_retry_api_call_retries_timeouts_and_server_errors(monkeypatch):
    responses: list[SimpleNamespace | Exception] = [
        httpx.ReadTimeout("read timed out"),
        httpx.RemoteProtocolError("server disconnected"),
        SimpleNamespace(status_code=502),
        SimpleNamespace(status_code=200),
    ]
    sleeps = []
    monkeypatch.setattr(helpers.time, "sleep", sleeps.append)

    def next_response() -> SimpleNamespace:
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    result = helpers._retry_api_call(next_response)

    assert result.status_code == 200
    assert sleeps == [helpers.API_RETRY_DELAY] * 3
