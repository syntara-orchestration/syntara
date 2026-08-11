"""Workflow definition schema models for v2 workflows.

This module provides the Pydantic model for workflow definitions that conform to
the Nexus Workflow Engine v2 schema.
"""

from typing import Annotated, Any, Literal

from pydantic import Discriminator, Field, field_validator
from sqlmodel import SQLModel

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
)

WorkflowNode = Annotated[_AllNodeTypes, Discriminator("type")]


class WorkflowDefinition(SQLModel):
    """JSON Schema for graph-based workflow definitions in the Nexus Workflow Engine v2.

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
        description="Execution and control nodes in the workflow graph",
    )
    edges: list[dict[str, Any]] = Field(
        ...,
        description="List of directed edges connecting triggers and nodes in the workflow graph",
    )
