"""Regression coverage for variable scope and run polling deadlines."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from temporalio.exceptions import ApplicationError, CancelledError

from syntara.workflows.workflow_engine.activities.tfe_activities import (
    execute_tfe_add_variable_activity,
    execute_tfe_delete_variable_activity,
    execute_tfe_fetch_state_outputs_activity,
    execute_tfe_get_run_status_activity,
    execute_tfe_update_variable_activity,
)
from syntara.workflows.workflow_engine.utils.credential_scrubber import REDACTED

INPUT = {
    "integration_id": "11111111-1111-1111-1111-111111111111",
    "credential_id": "22222222-2222-2222-2222-222222222222",
}
CLIENT_PATH = "syntara.workflows.workflow_engine.activities.tfe_activities._client_from_input"
HEARTBEAT_PATH = "syntara.workflows.workflow_engine.activities.tfe_common.activity.heartbeat"
IS_CANCELLED_PATH = "syntara.workflows.workflow_engine.activities.tfe_activities.activity.is_cancelled"


@pytest.mark.asyncio
async def test_variable_activities_pass_workspace_id() -> None:
    client = MagicMock(update_variable=AsyncMock(), delete_variable=AsyncMock())
    params = {**INPUT, "workspace_id": "ws-1", "variable_id": "var-1", "value": "updated"}
    with patch(CLIENT_PATH, return_value=client):
        await execute_tfe_update_variable_activity(params)
        await execute_tfe_delete_variable_activity(params)
    client.update_variable.assert_awaited_once_with("ws-1", "var-1", {"value": "updated"})
    client.delete_variable.assert_awaited_once_with("ws-1", "var-1")


@pytest.mark.asyncio
async def test_add_sensitive_variable_uses_value_credential() -> None:
    client = MagicMock(create_variable=AsyncMock(return_value={"data": {"id": "var-9"}}))
    params = {
        **INPUT,
        "workspace_id": "ws-1",
        "key": "DB_PASSWORD",
        "sensitive": True,
        "value_credential_id": "33333333-3333-3333-3333-333333333333",
        "_resolved_value_credentials": {
            "extra_vars": {"auth_type": "secret", "secret_value": "from-credential"},
        },
    }
    with patch(CLIENT_PATH, return_value=client):
        result = await execute_tfe_add_variable_activity(params)
    client.create_variable.assert_awaited_once_with(
        "ws-1",
        {
            "key": "DB_PASSWORD",
            "value": "from-credential",
            "category": "terraform",
            "sensitive": True,
            "hcl": False,
        },
    )
    assert result["variable_id"] == "var-9"


@pytest.mark.asyncio
async def test_fetch_state_outputs_redacts_sensitive_values() -> None:
    client = MagicMock(
        get_current_state_version=AsyncMock(
            return_value={"data": {"id": "sv-1", "attributes": {}}},
        ),
        get_state_version_outputs=AsyncMock(
            return_value={
                "data": [
                    {
                        "id": "wsout-1",
                        "attributes": {"name": "public_ip", "value": "1.2.3.4", "sensitive": False},
                    },
                    {
                        "id": "wsout-2",
                        "attributes": {"name": "db_password", "value": "super-secret", "sensitive": True},
                    },
                ]
            }
        ),
    )
    with patch(CLIENT_PATH, return_value=client):
        result = await execute_tfe_fetch_state_outputs_activity({**INPUT, "workspace_id": "ws-1"})
    assert result["outputs"]["public_ip"] == "1.2.3.4"
    assert result["outputs"]["db_password"] == REDACTED
    assert "super-secret" not in str(result)


@pytest.mark.asyncio
async def test_polling_deadline_interrupts_a_stalled_request() -> None:
    async def stalled_request(_run_id: str) -> None:
        await asyncio.sleep(60)

    client = MagicMock(get_run=AsyncMock(side_effect=stalled_request))
    with (
        patch(CLIENT_PATH, return_value=client),
        patch(HEARTBEAT_PATH),
        patch(IS_CANCELLED_PATH, return_value=False),
        pytest.raises(ApplicationError) as error,
    ):
        await execute_tfe_get_run_status_activity(
            {**INPUT, "run_id": "run-1", "wait_for_completion": True, "timeout_seconds": 1}
        )
    assert error.value.type == "TRANSIENT"
    assert error.value.non_retryable


@pytest.mark.asyncio
async def test_wait_for_completion_starts_heartbeat_loop() -> None:
    """wait_for_completion must start the background heartbeat task used for cancel delivery."""
    payloads = [
        {"data": {"attributes": {"status": "planning", "actions": {}}}},
        {"data": {"attributes": {"status": "applied", "actions": {}, "has-changes": False}}},
    ]
    client = MagicMock(get_run=AsyncMock(side_effect=payloads))
    with (
        patch(CLIENT_PATH, return_value=client),
        patch(
            "syntara.workflows.workflow_engine.activities.tfe_activities.heartbeat_until_cancelled",
            new_callable=AsyncMock,
        ) as mock_heartbeat_loop,
        patch(IS_CANCELLED_PATH, return_value=False),
        patch("syntara.workflows.workflow_engine.activities.tfe_activities.asyncio.sleep", new_callable=AsyncMock),
    ):
        result = await execute_tfe_get_run_status_activity(
            {
                **INPUT,
                "run_id": "run-1",
                "wait_for_completion": True,
                "poll_interval_seconds": 1,
                "timeout_seconds": 30,
            }
        )
    assert result["status"] == "applied"
    assert mock_heartbeat_loop.call_count == 1


@pytest.mark.asyncio
async def test_one_shot_status_does_not_start_heartbeat_loop() -> None:
    """A non-waiting status check must not start the heartbeat loop."""
    client = MagicMock(
        get_run=AsyncMock(
            return_value={"data": {"attributes": {"status": "applied", "actions": {}, "has-changes": False}}},
        )
    )
    with (
        patch(CLIENT_PATH, return_value=client),
        patch(
            "syntara.workflows.workflow_engine.activities.tfe_activities.heartbeat_until_cancelled",
            new_callable=AsyncMock,
        ) as mock_heartbeat_loop,
    ):
        result = await execute_tfe_get_run_status_activity({**INPUT, "run_id": "run-1"})
    assert result["status"] == "applied"
    mock_heartbeat_loop.assert_not_called()


@pytest.mark.asyncio
async def test_heartbeat_until_cancelled_beats_before_first_sleep() -> None:
    """Cancel is undeliverable for one interval if the loop sleeps before beating."""
    from syntara.workflows.workflow_engine.activities.tfe_common import heartbeat_until_cancelled

    with (
        patch(
            "syntara.workflows.workflow_engine.activities.tfe_common.INTERNAL_ACTIVITY_HEARTBEAT_INTERVAL_SECONDS",
            600.0,
        ),
        patch(HEARTBEAT_PATH) as mock_heartbeat,
    ):
        task = asyncio.create_task(heartbeat_until_cancelled())
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert mock_heartbeat.call_count == 1


@pytest.mark.asyncio
async def test_wait_for_completion_raises_when_cancelled() -> None:
    client = MagicMock(
        get_run=AsyncMock(
            return_value={"data": {"attributes": {"status": "planning", "actions": {}}}},
        )
    )
    with (
        patch(CLIENT_PATH, return_value=client),
        patch(HEARTBEAT_PATH),
        patch(IS_CANCELLED_PATH, return_value=True),
        pytest.raises(CancelledError),
    ):
        await execute_tfe_get_run_status_activity(
            {**INPUT, "run_id": "run-1", "wait_for_completion": True, "timeout_seconds": 30}
        )
