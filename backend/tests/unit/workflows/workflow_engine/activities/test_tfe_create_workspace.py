"""Unit tests for TFE create workspace activity."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine.activities.tfe_activities import execute_tfe_create_workspace_activity


@pytest.mark.asyncio
async def test_create_workspace_success() -> None:
    input_config: dict[str, Any] = {
        "integration_id": "11111111-1111-1111-1111-111111111111",
        "credential_id": "22222222-2222-2222-2222-222222222222",
        "name": "demo-ws",
        "_resolved_integration": {
            "base_url": "https://app.terraform.io",
            "organization": "acme",
            "verify_ssl": True,
            "ca_certificate": None,
        },
        "_resolved_credentials": {"extra_vars": {"bearer_token": "t.ok", "auth_type": "bearer"}},
    }

    mock_client = MagicMock()
    mock_client.organization = "acme"
    mock_client.create_workspace = AsyncMock(
        return_value={
            "data": {"id": "ws-abc", "attributes": {"name": "demo-ws"}},
        }
    )

    with patch(
        "syntara.workflows.workflow_engine.activities.tfe_activities._client_from_input",
        return_value=mock_client,
    ):
        result = await execute_tfe_create_workspace_activity(input_config)

    assert result["workspace_id"] == "ws-abc"
    assert result["workspace_name"] == "demo-ws"
    assert result["organization"] == "acme"
    mock_client.create_workspace.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_workspace_remote_github_preset() -> None:
    input_config: dict[str, Any] = {
        "integration_id": "11111111-1111-1111-1111-111111111111",
        "credential_id": "22222222-2222-2222-2222-222222222222",
        "name": "demo-ws",
        "preset": "remote_github",
        "repository": "acme/app",
        "branch": "main",
        "github_app_installation_id": "ghain-9",
        "_resolved_integration": {
            "base_url": "https://app.terraform.io",
            "organization": "acme",
            "verify_ssl": True,
            "ca_certificate": None,
        },
        "_resolved_credentials": {"extra_vars": {"bearer_token": "t.ok", "auth_type": "bearer"}},
    }
    mock_client = MagicMock()
    mock_client.organization = "acme"
    mock_client.create_workspace = AsyncMock(return_value={"data": {"id": "ws-abc", "attributes": {"name": "demo-ws"}}})

    with patch(
        "syntara.workflows.workflow_engine.activities.tfe_activities._client_from_input",
        return_value=mock_client,
    ):
        await execute_tfe_create_workspace_activity(input_config)

    kwargs = mock_client.create_workspace.await_args.kwargs
    assert kwargs["attributes"]["execution-mode"] == "remote"
    assert kwargs["attributes"]["vcs-repo"]["github-app-installation-id"] == "ghain-9"


@pytest.mark.asyncio
async def test_create_workspace_missing_integration() -> None:
    with pytest.raises(ApplicationError) as exc:
        await execute_tfe_create_workspace_activity(
            {
                "integration_id": "11111111-1111-1111-1111-111111111111",
                "credential_id": "22222222-2222-2222-2222-222222222222",
                "name": "demo-ws",
            }
        )
    assert exc.value.type == "CONFIG_MISSING"
