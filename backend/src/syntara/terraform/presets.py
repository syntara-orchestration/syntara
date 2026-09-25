"""Workspace creation presets: execution mode combined with config source."""

from __future__ import annotations

from typing import Any, Literal

from syntara.terraform.errors import TFEError, TFEErrorCode

WorkspacePreset = Literal["remote_no_vcs", "agent", "remote_oauth_vcs", "remote_github"]

_AGENT_POOL_REQUIRED = "agent_pool_id is required for the agent execution preset"
_OAUTH_REQUIRED = "repository and oauth_token_id are required for the remote OAuth VCS preset"
_GITHUB_REQUIRED = "repository and github_app_installation_id are required for the remote GitHub preset"


def _validation(message: str) -> TFEError:
    return TFEError(message, error_code=TFEErrorCode.VALIDATION)


def _vcs_repo(identifier: str, branch: str | None, extra: dict[str, str]) -> dict[str, Any]:
    repo: dict[str, Any] = {"identifier": identifier, **extra}
    if branch:
        repo["branch"] = branch
    return {"execution-mode": "remote", "vcs-repo": repo}


def workspace_preset_parts(
    preset: WorkspacePreset | None,
    *,
    agent_pool_id: str | None = None,
    repository: str | None = None,
    branch: str | None = None,
    oauth_token_id: str | None = None,
    github_app_installation_id: str | None = None,
    disconnect_vcs: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Map a workspace preset to TFE attributes and relationships.

    ``relationships`` is empty when the preset does not need one. On update,
    ``disconnect_vcs`` clears ``vcs-repo`` for the remote-without-VCS preset.
    """
    if preset is None:
        return {}, {}

    if preset == "remote_no_vcs":
        attrs: dict[str, Any] = {"execution-mode": "remote"}
        if disconnect_vcs:
            attrs["vcs-repo"] = None
        return attrs, {}

    if preset == "agent":
        if not agent_pool_id:
            raise _validation(_AGENT_POOL_REQUIRED)
        relationship = {"agent-pool": {"data": {"type": "agent-pools", "id": agent_pool_id}}}
        return {"execution-mode": "agent"}, relationship

    if preset == "remote_oauth_vcs":
        if not repository or not oauth_token_id:
            raise _validation(_OAUTH_REQUIRED)
        return _vcs_repo(repository, branch, {"oauth-token-id": oauth_token_id}), {}

    if preset == "remote_github":
        if not repository or not github_app_installation_id:
            raise _validation(_GITHUB_REQUIRED)
        return _vcs_repo(repository, branch, {"github-app-installation-id": github_app_installation_id}), {}

    message = f"Unknown workspace preset '{preset}'"
    raise _validation(message)
