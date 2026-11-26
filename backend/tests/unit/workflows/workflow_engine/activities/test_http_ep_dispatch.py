"""Explicit HTTP EP placement and compatibility boundaries."""

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflow_core.models import APIExecutorParameters
from syntara.workflow_runtime.engines.temporal.activities.ep import http_dispatch
from syntara.workflow_runtime.engines.temporal.constants import ENGINE_TIMEOUT_SECONDS_KEY


def _inputs() -> dict[str, Any]:
    return {
        "method": "GET",
        "url": "https://example.com",
        "execution_profile": {"type": "execution_target", "execution_target_id": str(uuid4())},
    }


def test_existing_http_has_no_execution_profile() -> None:
    assert (
        APIExecutorParameters.model_validate({"method": "GET", "url": "https://example.com"}).execution_profile is None
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields",
    [
        {"credential_id": "id"},
        {"credential_bindings": [{"credential_recipe_id": "syntara.http.bearer", "credential_ref": str(uuid4())}]},
        {"_resolved_credentials": {"token": "secret"}},
        {"headers": {"Authorization": "secret"}},
        {"url": "https://user:password@example.com"},
        {"query_params": {"count": 3}},
    ],
)
async def test_unsupported_inputs_fail_before_dispatch(fields: dict[str, Any]) -> None:
    inputs = _inputs() | fields
    with patch.object(http_dispatch, "_dispatch_to_ep", AsyncMock()) as dispatch:
        with pytest.raises(ApplicationError) as raised:
            await http_dispatch.dispatch_http_to_ep(
                inputs, None, str(uuid4()), APIExecutorParameters.model_validate(inputs)
            )
        assert raised.value.non_retryable
        dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_selected_target_and_full_outputs_reach_shared_dispatch() -> None:
    inputs = _inputs() | {ENGINE_TIMEOUT_SECONDS_KEY: 42, "_internal": "private"}
    execution_id = uuid4()
    config = APIExecutorParameters.model_validate(inputs)
    result = {"output": {"status_code": 200}}
    with patch.object(http_dispatch, "_dispatch_to_ep", AsyncMock(return_value=result)) as dispatch:
        assert await http_dispatch.dispatch_http_to_ep(inputs, None, str(execution_id), config) == result
    assert dispatch.await_args is not None
    assert config.execution_profile is not None
    args = dispatch.await_args.args
    assert args[0]["timeout_seconds"] == 42
    assert args[0]["method"] == "GET"
    assert "_internal" not in args[0]
    assert "execution_profile" not in args[0]
    assert args[1:] == (None, execution_id, config.execution_profile.execution_target_id, "http-request")


@pytest.mark.asyncio
async def test_accepted_work_waits_for_async_completion() -> None:
    inputs = _inputs()
    with (
        patch.object(http_dispatch, "_dispatch_to_ep", AsyncMock(return_value=None)),
        patch("temporalio.activity.raise_complete_async", side_effect=RuntimeError("async completion")) as complete,
    ):
        with pytest.raises(RuntimeError, match="async completion"):
            await http_dispatch.dispatch_http_to_ep(
                inputs, None, str(uuid4()), APIExecutorParameters.model_validate(inputs)
            )
        complete.assert_called_once()


@pytest.mark.asyncio
async def test_missing_seed_is_not_silently_routed_to_native_http() -> None:
    inputs = _inputs()
    with patch.object(
        http_dispatch, "_dispatch_to_ep", AsyncMock(side_effect=ApplicationError("No HTTP plugin", non_retryable=True))
    ):
        with pytest.raises(ApplicationError, match="No HTTP plugin"):
            await http_dispatch.dispatch_http_to_ep(
                inputs, None, str(uuid4()), APIExecutorParameters.model_validate(inputs)
            )


@pytest.mark.asyncio
async def test_http_activity_hands_explicit_profile_to_dispatch() -> None:
    from syntara.workflow_runtime.engines.temporal.activities import http_request_activity

    inputs = _inputs()
    execution_id = str(uuid4())
    with (
        patch("temporalio.activity.heartbeat"),
        patch.object(http_request_activity, "dispatch_http_to_ep", AsyncMock(return_value={"output": {}})) as dispatch,
    ):
        assert await http_request_activity.execute_http_request_activity(inputs, {}, execution_id) == {"output": {}}
    assert dispatch.await_args is not None
    assert dispatch.await_args.args[:3] == (inputs, {}, execution_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("outputs", [{}, {"status_code": "{{ status_code }}"}])
async def test_output_selection_is_rejected_before_http_can_run(outputs: dict[str, str]) -> None:
    inputs = _inputs()
    with patch.object(http_dispatch, "_dispatch_to_ep", AsyncMock()) as dispatch:
        with pytest.raises(ApplicationError, match="default full outputs") as raised:
            await http_dispatch.dispatch_http_to_ep(
                inputs, outputs, str(uuid4()), APIExecutorParameters.model_validate(inputs)
            )
        assert raised.value.non_retryable
        dispatch.assert_not_awaited()
