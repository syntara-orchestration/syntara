"""Stable mapping of saved Syntara step types to independently versioned SDK nodes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from syntara.workflows.workflow_engine.models import tfe_types as models

if TYPE_CHECKING:
    from syntara.workflows.workflow_engine.models.workflow_definition import NodeOutput


@dataclass(frozen=True)
class TFEStepBinding:
    """One workflow contract paired with its SDK operation."""

    operation: str
    parameters: type[models.TFEIntegrationMixin]
    output: type[NodeOutput]

    @property
    def node_name(self) -> str:
        """Return the manifest metadata.name."""
        return "tfe_" + self.operation


TFE_STEP_BINDINGS: dict[str, TFEStepBinding] = {
    "tfe_create_workspace": TFEStepBinding(
        "create_workspace", models.TFECreateWorkspaceParameters, models.TFECreateWorkspaceOutput
    ),
    "tfe_list_workspaces": TFEStepBinding(
        "list_workspaces", models.TFEListWorkspacesParameters, models.TFEListWorkspacesOutput
    ),
    "tfe_update_workspace": TFEStepBinding(
        "update_workspace_settings", models.TFEUpdateWorkspaceParameters, models.TFEUpdateWorkspaceOutput
    ),
    "tfe_delete_workspace": TFEStepBinding(
        "delete_workspace", models.TFEDeleteWorkspaceParameters, models.TFEDeleteWorkspaceOutput
    ),
    "tfe_fetch_state_outputs": TFEStepBinding(
        "fetch_state_and_outputs", models.TFEFetchStateOutputsParameters, models.TFEFetchStateOutputsOutput
    ),
    "tfe_add_variable": TFEStepBinding("add_variable", models.TFEAddVariableParameters, models.TFEAddVariableOutput),
    "tfe_list_variables": TFEStepBinding(
        "list_variables", models.TFEListVariablesParameters, models.TFEListVariablesOutput
    ),
    "tfe_update_variable": TFEStepBinding(
        "update_variable", models.TFEUpdateVariableParameters, models.TFEUpdateVariableOutput
    ),
    "tfe_delete_variable": TFEStepBinding(
        "delete_variable", models.TFEDeleteVariableParameters, models.TFEDeleteVariableOutput
    ),
    "tfe_upload_configuration_version": TFEStepBinding(
        "upload_configuration_version",
        models.TFEUploadConfigurationVersionParameters,
        models.TFEUploadConfigurationVersionOutput,
    ),
    "tfe_trigger_run": TFEStepBinding("trigger_run", models.TFETriggerRunParameters, models.TFETriggerRunOutput),
    "tfe_get_run_status": TFEStepBinding(
        "get_run_status", models.TFEGetRunStatusParameters, models.TFEGetRunStatusOutput
    ),
    "tfe_list_runs": TFEStepBinding("list_runs_for_workspace", models.TFEListRunsParameters, models.TFEListRunsOutput),
    "tfe_add_run_comment": TFEStepBinding(
        "add_run_comment", models.TFEAddRunCommentParameters, models.TFEAddRunCommentOutput
    ),
    "tfe_list_github_installations": TFEStepBinding(
        "list_github_installations",
        models.TFEListGitHubInstallationsParameters,
        models.TFEListGitHubInstallationsOutput,
    ),
    "tfe_get_github_installation": TFEStepBinding(
        "get_installation_details", models.TFEGetGitHubInstallationParameters, models.TFEGetGitHubInstallationOutput
    ),
    "tfe_link_vcs": TFEStepBinding("link_vcs_to_workspace", models.TFELinkVCSParameters, models.TFELinkVCSOutput),
    "tfe_create_project": TFEStepBinding(
        "create_project", models.TFECreateProjectParameters, models.TFECreateProjectOutput
    ),
    "tfe_list_projects": TFEStepBinding(
        "list_projects", models.TFEListProjectsParameters, models.TFEListProjectsOutput
    ),
    "tfe_get_project": TFEStepBinding(
        "get_project_details", models.TFEGetProjectParameters, models.TFEGetProjectOutput
    ),
    "tfe_update_project": TFEStepBinding(
        "update_project_settings", models.TFEUpdateProjectParameters, models.TFEUpdateProjectOutput
    ),
    "tfe_delete_project": TFEStepBinding(
        "delete_project", models.TFEDeleteProjectParameters, models.TFEDeleteProjectOutput
    ),
    "tfe_move_workspace_to_project": TFEStepBinding(
        "move_workspace_to_project", models.TFEMoveWorkspaceToProjectParameters, models.TFEMoveWorkspaceToProjectOutput
    ),
    "tfe_assign_team_permissions": TFEStepBinding(
        "assign_team_permissions", models.TFEAssignTeamPermissionsParameters, models.TFEAssignTeamPermissionsOutput
    ),
    **{
        f"tfe_{action}_run": TFEStepBinding(f"{action}_run", models.TFERunActionParameters, models.TFERunActionOutput)
        for action in ("apply", "discard", "cancel", "force_cancel")
    },
}
