"""TFE workflow node parameter and output models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, ValidationInfo, field_validator

from syntara.workflows.workflow_engine.models.workflow_definition import (
    NodeOutput,
    TemplateAwareBaseModel,
    validate_uuid_or_template,
)


class TFEIntegrationMixin(TemplateAwareBaseModel):
    """Shared integration/credential fields for all TFE steps."""

    integration_id: str = Field(description="UUID of the Terraform Enterprise integration")
    credential_id: str = Field(description="UUID of the HTTP Bearer Token credential")
    organization: str | None = Field(
        default=None,
        description="Optional organization override; defaults to the integration organization",
    )

    @field_validator("integration_id", "credential_id")
    @classmethod
    def validate_uuid_fields(cls, v: str, info: ValidationInfo) -> str:
        """Validate UUID or template expression."""
        validate_uuid_or_template(v, info.field_name or "unknown")
        return v


# ── Workspace ──────────────────────────────────────────────────────────────


WorkspacePresetName = Literal["remote_no_vcs", "agent", "remote_oauth_vcs", "remote_github"]


class TFEWorkspacePresetMixin(TemplateAwareBaseModel):
    """Preset plus the fields each preset needs."""

    preset: WorkspacePresetName | None = Field(
        default=None,
        description="Workspace preset: remote_no_vcs, agent, remote_oauth_vcs, or remote_github",
    )
    agent_pool_id: str | None = Field(default=None, description="Agent pool ID for agent execution")
    repository: str | None = Field(default=None, description="VCS repository identifier (org/name)")
    branch: str | None = Field(default=None, description="VCS branch")
    oauth_token_id: str | None = Field(default=None, description="OAuth token ID for remote OAuth VCS")
    github_app_installation_id: str | None = Field(
        default=None,
        description="GitHub App installation ID for remote GitHub VCS",
    )


class TFECreateWorkspaceParameters(TFEIntegrationMixin, TFEWorkspacePresetMixin):
    """Parameters for Create Workspace."""

    name: str = Field(description="Workspace name")
    auto_apply: bool | None = Field(default=None, description="Enable auto-apply")
    execution_mode: Literal["remote", "local", "agent"] | None = Field(
        default=None,
        description="Execution mode pass-through when no preset is set (local is HCP-only)",
    )
    terraform_version: str | None = Field(default=None, description="Terraform version")
    description: str | None = Field(default=None, description="Workspace description")
    working_directory: str | None = Field(default=None, description="Working directory")
    project_id: str | None = Field(default=None, description="Project ID to place the workspace in")


class TFEListWorkspacesParameters(TFEIntegrationMixin):
    """Parameters for List Workspaces."""

    search: str | None = Field(default=None, description="Optional name search filter")
    project_id: str | None = Field(default=None, description="Optional project filter")


class TFEUpdateWorkspaceParameters(TFEIntegrationMixin, TFEWorkspacePresetMixin):
    """Parameters for Update Workspace Settings."""

    workspace_id: str = Field(description="Workspace ID (ws-...)")
    auto_apply: bool | None = None
    description: str | None = None
    working_directory: str | None = None
    terraform_version: str | None = None
    execution_mode: Literal["remote", "local", "agent"] | None = None


class TFEDeleteWorkspaceParameters(TFEIntegrationMixin):
    """Parameters for Delete Workspace."""

    workspace_id: str = Field(description="Workspace ID (ws-...)")
    force: bool = Field(default=False, description="Force delete even when workspace has state")


class TFEFetchStateOutputsParameters(TFEIntegrationMixin):
    """Parameters for Fetch State and Outputs."""

    workspace_id: str = Field(description="Workspace ID (ws-...)")


class TFECreateWorkspaceOutput(NodeOutput):
    """Output for Create Workspace."""

    workspace_id: str | None = None
    workspace_name: str | None = None
    organization: str | None = None


class TFEListWorkspacesOutput(NodeOutput):
    """Output for List Workspaces."""

    workspaces: list[dict[str, Any]] | None = None
    count: int | None = None


class TFEUpdateWorkspaceOutput(NodeOutput):
    """Output for Update Workspace."""

    workspace_id: str | None = None


class TFEDeleteWorkspaceOutput(NodeOutput):
    """Output for Delete Workspace."""

    deleted: bool | None = None


class TFEFetchStateOutputsOutput(NodeOutput):
    """Output for Fetch State and Outputs."""

    has_state: bool | None = None
    state_version_id: str | None = None
    outputs: dict[str, Any] | None = None


# ── Variables ──────────────────────────────────────────────────────────────


class TFEAddVariableParameters(TFEIntegrationMixin):
    """Parameters for Add Variable."""

    workspace_id: str
    key: str
    value: str
    category: Literal["terraform", "env"] = "terraform"
    sensitive: bool = False
    hcl: bool = False


class TFEListVariablesParameters(TFEIntegrationMixin):
    """Parameters for List Variables."""

    workspace_id: str
    key: str | None = None


class TFEUpdateVariableParameters(TFEIntegrationMixin):
    """Parameters for Update Variable."""

    variable_id: str
    value: str | None = None
    hcl: bool | None = None
    category: Literal["terraform", "env"] | None = None


class TFEDeleteVariableParameters(TFEIntegrationMixin):
    """Parameters for Delete Variable."""

    variable_id: str


class TFEAddVariableOutput(NodeOutput):
    """Output for Add Variable."""

    variable_id: str | None = None


class TFEListVariablesOutput(NodeOutput):
    """Output for List Variables (values never included)."""

    variables: list[dict[str, Any]] | None = None
    count: int | None = None


class TFEUpdateVariableOutput(NodeOutput):
    """Output for Update Variable."""

    variable_id: str | None = None


class TFEDeleteVariableOutput(NodeOutput):
    """Output for Delete Variable."""

    deleted: bool | None = None


# ── Configuration ──────────────────────────────────────────────────────────


class TFEUploadConfigurationVersionParameters(TFEIntegrationMixin):
    """Parameters for Upload Configuration Version."""

    workspace_id: str
    artifact: str = Field(description="Base64-encoded .tar.gz of the Terraform directory, or artifact reference")
    auto_queue_runs: bool = False


class TFEUploadConfigurationVersionOutput(NodeOutput):
    """Output for Upload Configuration Version."""

    configuration_version_id: str | None = None


# ── Runs ───────────────────────────────────────────────────────────────────


class TFETriggerRunParameters(TFEIntegrationMixin):
    """Parameters for Trigger Run."""

    workspace_id: str
    mode: str = Field(description="Run mode (plan-and-apply, plan-only, destroy, ...)")
    configuration_version_id: str | None = None
    target_resources: list[str] | None = None
    replace_resources: list[str] | None = None
    message: str | None = None


class TFEGetRunStatusParameters(TFEIntegrationMixin):
    """Parameters for Get Run Status."""

    run_id: str
    wait_for_completion: bool = False
    poll_interval_seconds: int = 15
    timeout_seconds: int = 3600


class TFERunActionParameters(TFEIntegrationMixin):
    """Parameters for Apply / Discard / Cancel / Force Cancel."""

    run_id: str
    comment: str | None = None


class TFEListRunsParameters(TFEIntegrationMixin):
    """Parameters for List Runs."""

    workspace_id: str
    status: str | None = None


class TFEAddRunCommentParameters(TFEIntegrationMixin):
    """Parameters for Add Run Comment."""

    run_id: str
    comment: str


class TFETriggerRunOutput(NodeOutput):
    """Output for Trigger Run."""

    run_id: str | None = None
    mode: str | None = None
    status: str | None = None


class TFEGetRunStatusOutput(NodeOutput):
    """Output for Get Run Status."""

    run_id: str | None = None
    status: str | None = None
    phase: str | None = None
    plan_exit_code: int | None = None
    has_changes: bool | None = None
    resource_changes: dict[str, Any] | None = None
    is_confirmable: bool | None = None
    is_cancelable: bool | None = None
    is_force_cancelable: bool | None = None


class TFERunActionOutput(NodeOutput):
    """Output for run control actions."""

    run_id: str | None = None
    action_queued: bool | None = None


class TFEListRunsOutput(NodeOutput):
    """Output for List Runs."""

    runs: list[dict[str, Any]] | None = None
    count: int | None = None


class TFEAddRunCommentOutput(NodeOutput):
    """Output for Add Run Comment."""

    comment_id: str | None = None


# ── VCS ────────────────────────────────────────────────────────────────────


class TFEListGitHubInstallationsParameters(TFEIntegrationMixin):
    """Parameters for List GitHub Installations."""


class TFEGetGitHubInstallationParameters(TFEIntegrationMixin):
    """Parameters for Get Installation Details."""

    installation_id: str


class TFELinkVCSParameters(TFEIntegrationMixin):
    """Parameters for Link VCS to Workspace."""

    workspace_id: str
    installation_id: str
    repository: str
    branch: str


class TFEListGitHubInstallationsOutput(NodeOutput):
    """Output for List GitHub Installations."""

    installations: list[dict[str, Any]] | None = None
    count: int | None = None


class TFEGetGitHubInstallationOutput(NodeOutput):
    """Output for Get Installation Details."""

    installation_id: str | None = None
    owner: str | None = None
    display_name: str | None = None
    repositories: list[str] | None = None


class TFELinkVCSOutput(NodeOutput):
    """Output for Link VCS."""

    linked: bool | None = None
    identifier: str | None = None
    branch: str | None = None


# ── Projects ───────────────────────────────────────────────────────────────


class TFECreateProjectParameters(TFEIntegrationMixin):
    """Parameters for Create Project."""

    name: str
    description: str | None = None


class TFEListProjectsParameters(TFEIntegrationMixin):
    """Parameters for List Projects."""


class TFEGetProjectParameters(TFEIntegrationMixin):
    """Parameters for Get Project Details."""

    project_id: str


class TFEUpdateProjectParameters(TFEIntegrationMixin):
    """Parameters for Update Project Settings."""

    project_id: str
    name: str | None = None
    description: str | None = None


class TFEDeleteProjectParameters(TFEIntegrationMixin):
    """Parameters for Delete Project."""

    project_id: str


class TFEMoveWorkspaceToProjectParameters(TFEIntegrationMixin):
    """Parameters for Move Workspace to Project."""

    workspace_id: str
    project_id: str | None = None


class TFEAssignTeamPermissionsParameters(TFEIntegrationMixin):
    """Parameters for Assign Team Permissions."""

    project_id: str
    team_id: str
    access: Literal["read", "write", "maintain", "admin", "custom"] = "read"


class TFECreateProjectOutput(NodeOutput):
    """Output for Create Project."""

    project_id: str | None = None


class TFEListProjectsOutput(NodeOutput):
    """Output for List Projects."""

    projects: list[dict[str, Any]] | None = None
    count: int | None = None


class TFEGetProjectOutput(NodeOutput):
    """Output for Get Project Details."""

    project_id: str | None = None
    name: str | None = None
    description: str | None = None
    teams: list[dict[str, Any]] | None = None


class TFEUpdateProjectOutput(NodeOutput):
    """Output for Update Project."""

    project_id: str | None = None


class TFEDeleteProjectOutput(NodeOutput):
    """Output for Delete Project."""

    deleted: bool | None = None


class TFEMoveWorkspaceToProjectOutput(NodeOutput):
    """Output for Move Workspace to Project."""

    workspace_id: str | None = None
    project_id: str | None = None


class TFEAssignTeamPermissionsOutput(NodeOutput):
    """Output for Assign Team Permissions."""

    project_id: str | None = None
    team_id: str | None = None
    access: str | None = None
