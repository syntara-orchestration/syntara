"""Regression coverage for variable scope and run polling deadlines."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine.activities.tfe_activities import (
    execute_tfe_delete_variable_activity,
    execute_tfe_get_run_status_activity,
    execute_tfe_update_variable_activity,
)

INPUT = {
    "integration_id": "11111111-1111-1111-1111-111111111111",
    "credential_id": "22222222-2222-2222-2222-222222222222",
}
CLIENT_PATH = "syntara.workflows.workflow_engine.activities.tfe_activities._client_from_input"


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
async def test_polling_deadline_interrupts_a_stalled_request() -> None:
    async def stalled_request(_run_id: str) -> None:
        await asyncio.sleep(60)

    client = MagicMock(get_run=AsyncMock(side_effect=stalled_request))
    with patch(CLIENT_PATH, return_value=client), pytest.raises(ApplicationError) as error:
        await execute_tfe_get_run_status_activity(
            {**INPUT, "run_id": "run-1", "wait_for_completion": True, "timeout_seconds": 1}
        )
    assert error.value.type == "TRANSIENT"
    assert error.value.non_retryable
