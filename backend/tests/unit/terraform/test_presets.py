"""Workspace preset mapping."""

import pytest

from syntara.terraform.errors import TFEError, TFEErrorCode
from syntara.terraform.presets import workspace_preset_parts


def test_remote_no_vcs_sets_remote_execution() -> None:
    attrs, relationships = workspace_preset_parts("remote_no_vcs")
    assert attrs == {"execution-mode": "remote"}
    assert relationships == {}


def test_remote_no_vcs_update_clears_vcs_repo() -> None:
    attrs, _relationships = workspace_preset_parts("remote_no_vcs", disconnect_vcs=True)
    assert attrs["vcs-repo"] is None


def test_agent_execution_requires_pool_and_sets_relationship() -> None:
    attrs, relationships = workspace_preset_parts("agent", agent_pool_id="apool-1")
    assert attrs == {"execution-mode": "agent"}
    assert relationships["agent-pool"]["data"]["id"] == "apool-1"


def test_agent_execution_missing_pool_is_validation() -> None:
    with pytest.raises(TFEError) as exc:
        workspace_preset_parts("agent")
    assert exc.value.error_code == TFEErrorCode.VALIDATION


def test_remote_oauth_vcs() -> None:
    attrs, relationships = workspace_preset_parts(
        "remote_oauth_vcs",
        repository="acme/app",
        branch="main",
        oauth_token_id="ot-1",  # noqa: S106
    )
    assert relationships == {}
    assert attrs["execution-mode"] == "remote"
    assert attrs["vcs-repo"] == {
        "identifier": "acme/app",
        "oauth-token-id": "ot-1",
        "branch": "main",
    }


def test_remote_github() -> None:
    attrs, _relationships = workspace_preset_parts(
        "remote_github",
        repository="acme/app",
        github_app_installation_id="ghain-1",
    )
    assert attrs["vcs-repo"]["github-app-installation-id"] == "ghain-1"
    assert attrs["execution-mode"] == "remote"
