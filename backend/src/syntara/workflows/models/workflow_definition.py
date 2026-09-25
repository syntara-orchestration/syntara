"""Workflow definition schema models for v2 workflows.

This module provides the Pydantic model for workflow definitions that conform to
the Orchestrator Workflow Engine v2 schema.
"""

from typing import Annotated, Any, Literal

from pydantic import Discriminator, Field, field_validator
from sqlmodel import SQLModel

from syntara.core.constants import JsonbLimits
from syntara.workflows.workflow_engine.models.tfe_types import (
    TFEAddRunCommentParameters,
    TFEAddVariableParameters,
    TFEAssignTeamPermissionsParameters,
    TFECreateProjectParameters,
    TFECreateWorkspaceParameters,
    TFEDeleteProjectParameters,
    TFEDeleteVariableParameters,
    TFEDeleteWorkspaceParameters,
    TFEFetchStateOutputsParameters,
    TFEGetGitHubInstallationParameters,
    TFEGetProjectParameters,
    TFEGetRunStatusParameters,
    TFELinkVCSParameters,
    TFEListGitHubInstallationsParameters,
    TFEListProjectsParameters,
    TFEListRunsParameters,
    TFEListVariablesParameters,
    TFEListWorkspacesParameters,
    TFEMoveWorkspaceToProjectParameters,
    TFERunActionParameters,
    TFETriggerRunParameters,
    TFEUpdateProjectParameters,
    TFEUpdateVariableParameters,
    TFEUpdateWorkspaceParameters,
    TFEUploadConfigurationVersionParameters,
)
from syntara.workflows.workflow_engine.models.workflow_definition import (
    AAPJobTemplateExecutorParameters,
    AAPWorkflowJobTemplateExecutorParameters,
    AgenticExecutorParameters,
    APIExecutorParameters,
    ApprovalNodeParameters,
    ConditionNodeParameters,
    ConvergeNodeParameters,
    DoWhileLoopParameters,
    ForEachLoopParameters,
    NodeSettingsBase,
    NodeSettingsCof,
    NodeSettingsCofDisabled,
    NodeSettingsFull,
    NodeSettingsNoRetry,
    ScriptExecutorParameters,
    SwitchNodeParameters,
    WaitNodeParameters,
)


class NodePosition(SQLModel):
    """UI position hint for a workflow node."""

    x: float
    y: float


class WorkflowNodeBase(SQLModel):
    """Base properties shared by all workflow node types."""

    model_config = {"extra": "allow"}

    id: str = Field(
        ...,
        pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$",
        description="Unique identifier for the node within the workflow",
    )
    name: str | None = Field(None, min_length=1, description="Human-readable name for the node")
    description: str | None = Field(None, min_length=1, description="Human-readable description of the node purpose")
    outputs: dict[str, str] | None = Field(None, description="Output extraction mapping")
    position: NodePosition | None = Field(None, description="Optional UI position hint")


class AAPJobTemplateNode(WorkflowNodeBase):
    """Ansible Automation Platform job template executor node."""

    type: Literal["aap_job_template"]
    parameters: AAPJobTemplateExecutorParameters
    settings: NodeSettingsFull | None = None


class AAPWorkflowJobTemplateNode(WorkflowNodeBase):
    """Ansible Automation Platform workflow job template executor node."""

    type: Literal["aap_workflow_job_template"]
    parameters: AAPWorkflowJobTemplateExecutorParameters
    settings: NodeSettingsFull | None = None


class HTTPRequestNode(WorkflowNodeBase):
    """HTTP request executor node."""

    type: Literal["http_request"]
    parameters: APIExecutorParameters
    settings: NodeSettingsFull | None = None


class AgenticNode(WorkflowNodeBase):
    """Agentic executor node."""

    type: Literal["agentic"]
    parameters: AgenticExecutorParameters
    settings: NodeSettingsNoRetry | None = None


class ScriptNode(WorkflowNodeBase):
    """Script executor node."""

    type: Literal["script"]
    parameters: ScriptExecutorParameters
    settings: NodeSettingsNoRetry | None = None


class ApprovalNode(WorkflowNodeBase):
    """Approval gate node."""

    type: Literal["approval"]
    parameters: ApprovalNodeParameters
    settings: NodeSettingsNoRetry | None = None


class ConditionNode(WorkflowNodeBase):
    """Binary conditional branching node."""

    type: Literal["condition"]
    parameters: ConditionNodeParameters
    settings: NodeSettingsBase | None = None


class SwitchNode(WorkflowNodeBase):
    """Multi-case branching control node."""

    type: Literal["switch"]
    parameters: SwitchNodeParameters
    settings: NodeSettingsBase | None = None


class LoopNode(WorkflowNodeBase):
    """Loop (for_each/do_while) control node."""

    type: Literal["loop"]
    parameters: Annotated[ForEachLoopParameters | DoWhileLoopParameters, Field(discriminator="type")]
    settings: NodeSettingsCof | None = None


class ConvergeNode(WorkflowNodeBase):
    """Convergence/synchronization control node."""

    type: Literal["converge"]
    parameters: ConvergeNodeParameters
    settings: NodeSettingsCof | None = None


class TFECreateWorkspaceNode(WorkflowNodeBase):
    """TFE Create Workspace executor node."""

    type: Literal["tfe_create_workspace"]
    parameters: TFECreateWorkspaceParameters
    settings: NodeSettingsNoRetry | None = None


class TFEListWorkspacesNode(WorkflowNodeBase):
    """TFE List Workspaces executor node."""

    type: Literal["tfe_list_workspaces"]
    parameters: TFEListWorkspacesParameters
    settings: NodeSettingsFull | None = None


class TFEUpdateWorkspaceNode(WorkflowNodeBase):
    """TFE Update Workspace executor node."""

    type: Literal["tfe_update_workspace"]
    parameters: TFEUpdateWorkspaceParameters
    settings: NodeSettingsNoRetry | None = None


class TFEDeleteWorkspaceNode(WorkflowNodeBase):
    """TFE Delete Workspace executor node."""

    type: Literal["tfe_delete_workspace"]
    parameters: TFEDeleteWorkspaceParameters
    settings: NodeSettingsNoRetry | None = None


class TFEFetchStateOutputsNode(WorkflowNodeBase):
    """TFE Fetch State Outputs executor node."""

    type: Literal["tfe_fetch_state_outputs"]
    parameters: TFEFetchStateOutputsParameters
    settings: NodeSettingsFull | None = None


class TFEAddVariableNode(WorkflowNodeBase):
    """TFE Add Variable executor node."""

    type: Literal["tfe_add_variable"]
    parameters: TFEAddVariableParameters
    settings: NodeSettingsNoRetry | None = None


class TFEListVariablesNode(WorkflowNodeBase):
    """TFE List Variables executor node."""

    type: Literal["tfe_list_variables"]
    parameters: TFEListVariablesParameters
    settings: NodeSettingsFull | None = None


class TFEUpdateVariableNode(WorkflowNodeBase):
    """TFE Update Variable executor node."""

    type: Literal["tfe_update_variable"]
    parameters: TFEUpdateVariableParameters
    settings: NodeSettingsNoRetry | None = None


class TFEDeleteVariableNode(WorkflowNodeBase):
    """TFE Delete Variable executor node."""

    type: Literal["tfe_delete_variable"]
    parameters: TFEDeleteVariableParameters
    settings: NodeSettingsNoRetry | None = None


class TFEUploadConfigurationVersionNode(WorkflowNodeBase):
    """TFE Upload Configuration Version executor node."""

    type: Literal["tfe_upload_configuration_version"]
    parameters: TFEUploadConfigurationVersionParameters
    settings: NodeSettingsNoRetry | None = None


class TFETriggerRunNode(WorkflowNodeBase):
    """TFE Trigger Run executor node."""

    type: Literal["tfe_trigger_run"]
    parameters: TFETriggerRunParameters
    settings: NodeSettingsNoRetry | None = None


class TFEGetRunStatusNode(WorkflowNodeBase):
    """TFE Get Run Status executor node."""

    type: Literal["tfe_get_run_status"]
    parameters: TFEGetRunStatusParameters
    settings: NodeSettingsFull | None = None


class TFEApplyRunNode(WorkflowNodeBase):
    """TFE Apply Run executor node."""

    type: Literal["tfe_apply_run"]
    parameters: TFERunActionParameters
    settings: NodeSettingsNoRetry | None = None


class TFEDiscardRunNode(WorkflowNodeBase):
    """TFE Discard Run executor node."""

    type: Literal["tfe_discard_run"]
    parameters: TFERunActionParameters
    settings: NodeSettingsNoRetry | None = None


class TFECancelRunNode(WorkflowNodeBase):
    """TFE Cancel Run executor node."""

    type: Literal["tfe_cancel_run"]
    parameters: TFERunActionParameters
    settings: NodeSettingsNoRetry | None = None


class TFEForceCancelRunNode(WorkflowNodeBase):
    """TFE Force Cancel Run executor node."""

    type: Literal["tfe_force_cancel_run"]
    parameters: TFERunActionParameters
    settings: NodeSettingsNoRetry | None = None


class TFEListRunsNode(WorkflowNodeBase):
    """TFE List Runs executor node."""

    type: Literal["tfe_list_runs"]
    parameters: TFEListRunsParameters
    settings: NodeSettingsFull | None = None


class TFEAddRunCommentNode(WorkflowNodeBase):
    """TFE Add Run Comment executor node."""

    type: Literal["tfe_add_run_comment"]
    parameters: TFEAddRunCommentParameters
    settings: NodeSettingsNoRetry | None = None


class TFEListGitHubInstallationsNode(WorkflowNodeBase):
    """TFE List Git Hub Installations executor node."""

    type: Literal["tfe_list_github_installations"]
    parameters: TFEListGitHubInstallationsParameters
    settings: NodeSettingsFull | None = None


class TFEGetGitHubInstallationNode(WorkflowNodeBase):
    """TFE Get Git Hub Installation executor node."""

    type: Literal["tfe_get_github_installation"]
    parameters: TFEGetGitHubInstallationParameters
    settings: NodeSettingsFull | None = None


class TFELinkVCSNode(WorkflowNodeBase):
    """TFE Link V C S executor node."""

    type: Literal["tfe_link_vcs"]
    parameters: TFELinkVCSParameters
    settings: NodeSettingsNoRetry | None = None


class TFECreateProjectNode(WorkflowNodeBase):
    """TFE Create Project executor node."""

    type: Literal["tfe_create_project"]
    parameters: TFECreateProjectParameters
    settings: NodeSettingsNoRetry | None = None


class TFEListProjectsNode(WorkflowNodeBase):
    """TFE List Projects executor node."""

    type: Literal["tfe_list_projects"]
    parameters: TFEListProjectsParameters
    settings: NodeSettingsFull | None = None


class TFEGetProjectNode(WorkflowNodeBase):
    """TFE Get Project executor node."""

    type: Literal["tfe_get_project"]
    parameters: TFEGetProjectParameters
    settings: NodeSettingsFull | None = None


class TFEUpdateProjectNode(WorkflowNodeBase):
    """TFE Update Project executor node."""

    type: Literal["tfe_update_project"]
    parameters: TFEUpdateProjectParameters
    settings: NodeSettingsNoRetry | None = None


class TFEDeleteProjectNode(WorkflowNodeBase):
    """TFE Delete Project executor node."""

    type: Literal["tfe_delete_project"]
    parameters: TFEDeleteProjectParameters
    settings: NodeSettingsNoRetry | None = None


class TFEMoveWorkspaceToProjectNode(WorkflowNodeBase):
    """TFE Move Workspace To Project executor node."""

    type: Literal["tfe_move_workspace_to_project"]
    parameters: TFEMoveWorkspaceToProjectParameters
    settings: NodeSettingsNoRetry | None = None


class TFEAssignTeamPermissionsNode(WorkflowNodeBase):
    """TFE Assign Team Permissions executor node."""

    type: Literal["tfe_assign_team_permissions"]
    parameters: TFEAssignTeamPermissionsParameters
    settings: NodeSettingsNoRetry | None = None


class WaitNode(WorkflowNodeBase):
    """Wait (delay) control node."""

    type: Literal["wait"]
    parameters: WaitNodeParameters
    settings: NodeSettingsCofDisabled | None = None


_AllNodeTypes = (
    AAPJobTemplateNode
    | AAPWorkflowJobTemplateNode
    | HTTPRequestNode
    | AgenticNode
    | ScriptNode
    | ApprovalNode
    | ConditionNode
    | SwitchNode
    | LoopNode
    | ConvergeNode
    | WaitNode
    | TFECreateWorkspaceNode
    | TFEListWorkspacesNode
    | TFEUpdateWorkspaceNode
    | TFEDeleteWorkspaceNode
    | TFEFetchStateOutputsNode
    | TFEAddVariableNode
    | TFEListVariablesNode
    | TFEUpdateVariableNode
    | TFEDeleteVariableNode
    | TFEUploadConfigurationVersionNode
    | TFETriggerRunNode
    | TFEGetRunStatusNode
    | TFEApplyRunNode
    | TFEDiscardRunNode
    | TFECancelRunNode
    | TFEForceCancelRunNode
    | TFEListRunsNode
    | TFEAddRunCommentNode
    | TFEListGitHubInstallationsNode
    | TFEGetGitHubInstallationNode
    | TFELinkVCSNode
    | TFECreateProjectNode
    | TFEListProjectsNode
    | TFEGetProjectNode
    | TFEUpdateProjectNode
    | TFEDeleteProjectNode
    | TFEMoveWorkspaceToProjectNode
    | TFEAssignTeamPermissionsNode
)

WorkflowNode = Annotated[_AllNodeTypes, Discriminator("type")]


class WorkflowDefinition(SQLModel):
    """JSON Schema for graph-based workflow definitions in the Orchestrator Workflow Engine v2.

    Attributes:
        schema_version: Schema version that this workflow definition conforms to
        name: Workflow name
        description: Human-readable description of the workflow's purpose
        triggers: Trigger nodes that define how the workflow is initiated
        nodes: Execution and control nodes in the workflow graph
        edges: Directed edges connecting triggers and nodes in the workflow graph

    """

    model_config = {"extra": "forbid"}

    schema_version: Literal["2.0.0"] = Field(
        ...,
        description="Schema version that this workflow definition conforms to",
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Workflow name",
    )
    description: str | None = Field(
        None,
        min_length=1,
        max_length=1000,
        description="Human-readable description of the workflow's purpose",
    )

    @field_validator("description", mode="before")
    @classmethod
    def _empty_description_to_none(cls, v: str | None) -> str | None:
        if v == "":
            return None
        return v

    triggers: list[dict[str, Any]] = Field(
        ...,
        min_length=1,
        description="Trigger nodes that define how the workflow is initiated. "
        "Must contain at least one trigger. "
        "Trigger nodes must be graph entry points (no incoming edges) — "
        "enforced by application-level validation.",
    )
    nodes: list[WorkflowNode] = Field(
        ...,
        max_length=JsonbLimits.MAX_WORKFLOW_NODES,
        description="Execution and control nodes in the workflow graph",
    )
    edges: list[dict[str, Any]] = Field(
        ...,
        max_length=JsonbLimits.MAX_WORKFLOW_EDGES,
        description="List of directed edges connecting triggers and nodes in the workflow graph",
    )
