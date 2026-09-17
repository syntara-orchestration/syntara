from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.aap_job_template_node import AAPJobTemplateNode
    from ..models.aap_workflow_job_template_node import AAPWorkflowJobTemplateNode
    from ..models.agentic_node import AgenticNode
    from ..models.approval_node import ApprovalNode
    from ..models.condition_node import ConditionNode
    from ..models.converge_node import ConvergeNode
    from ..models.http_request_node import HTTPRequestNode
    from ..models.loop_node import LoopNode
    from ..models.script_node import ScriptNode
    from ..models.switch_node import SwitchNode
    from ..models.wait_node import WaitNode
    from ..models.workflow_definition_edges_item import WorkflowDefinitionEdgesItem
    from ..models.workflow_definition_triggers_item import WorkflowDefinitionTriggersItem


T = TypeVar("T", bound="WorkflowDefinition")


@_attrs_define
class WorkflowDefinition:
    """JSON Schema for graph-based workflow definitions in the Syntara Workflow Engine v2.

    Attributes:
        schema_version: Schema version that this workflow definition conforms to
        name: Workflow name
        description: Human-readable description of the workflow's purpose
        triggers: Trigger nodes that define how the workflow is initiated
        nodes: Execution and control nodes in the workflow graph
        edges: Directed edges connecting triggers and nodes in the workflow graph

        Attributes:
            schema_version (Literal['2.0.0']): Schema version that this workflow definition conforms to
            name (str): Workflow name
            triggers (list[WorkflowDefinitionTriggersItem]): Trigger nodes that define how the workflow is initiated. Must
                contain at least one trigger. Trigger nodes must be graph entry points (no incoming edges) — enforced by
                application-level validation.
            nodes (list[AAPJobTemplateNode | AAPWorkflowJobTemplateNode | AgenticNode | ApprovalNode | ConditionNode |
                ConvergeNode | HTTPRequestNode | LoopNode | ScriptNode | SwitchNode | WaitNode]): Execution and control nodes in
                the workflow graph
            edges (list[WorkflowDefinitionEdgesItem]): List of directed edges connecting triggers and nodes in the workflow
                graph
            description (None | str | Unset): Human-readable description of the workflow's purpose
    """

    schema_version: Literal["2.0.0"]
    name: str
    triggers: list[WorkflowDefinitionTriggersItem]
    nodes: list[
        AAPJobTemplateNode
        | AAPWorkflowJobTemplateNode
        | AgenticNode
        | ApprovalNode
        | ConditionNode
        | ConvergeNode
        | HTTPRequestNode
        | LoopNode
        | ScriptNode
        | SwitchNode
        | WaitNode
    ]
    edges: list[WorkflowDefinitionEdgesItem]
    description: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.aap_job_template_node import AAPJobTemplateNode
        from ..models.aap_workflow_job_template_node import AAPWorkflowJobTemplateNode
        from ..models.agentic_node import AgenticNode
        from ..models.approval_node import ApprovalNode
        from ..models.condition_node import ConditionNode
        from ..models.converge_node import ConvergeNode
        from ..models.http_request_node import HTTPRequestNode
        from ..models.loop_node import LoopNode
        from ..models.script_node import ScriptNode
        from ..models.switch_node import SwitchNode

        schema_version = self.schema_version

        name = self.name

        triggers = []
        for triggers_item_data in self.triggers:
            triggers_item = triggers_item_data.to_dict()
            triggers.append(triggers_item)

        nodes = []
        for nodes_item_data in self.nodes:
            nodes_item: dict[str, Any]
            if isinstance(nodes_item_data, AAPJobTemplateNode):
                nodes_item = nodes_item_data.to_dict()
            elif isinstance(nodes_item_data, AAPWorkflowJobTemplateNode):
                nodes_item = nodes_item_data.to_dict()
            elif isinstance(nodes_item_data, HTTPRequestNode):
                nodes_item = nodes_item_data.to_dict()
            elif isinstance(nodes_item_data, AgenticNode):
                nodes_item = nodes_item_data.to_dict()
            elif isinstance(nodes_item_data, ScriptNode):
                nodes_item = nodes_item_data.to_dict()
            elif isinstance(nodes_item_data, ApprovalNode):
                nodes_item = nodes_item_data.to_dict()
            elif isinstance(nodes_item_data, ConditionNode):
                nodes_item = nodes_item_data.to_dict()
            elif isinstance(nodes_item_data, SwitchNode):
                nodes_item = nodes_item_data.to_dict()
            elif isinstance(nodes_item_data, LoopNode):
                nodes_item = nodes_item_data.to_dict()
            elif isinstance(nodes_item_data, ConvergeNode):
                nodes_item = nodes_item_data.to_dict()
            else:
                nodes_item = nodes_item_data.to_dict()

            nodes.append(nodes_item)

        edges = []
        for edges_item_data in self.edges:
            edges_item = edges_item_data.to_dict()
            edges.append(edges_item)

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "schema_version": schema_version,
                "name": name,
                "triggers": triggers,
                "nodes": nodes,
                "edges": edges,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.aap_job_template_node import AAPJobTemplateNode
        from ..models.aap_workflow_job_template_node import AAPWorkflowJobTemplateNode
        from ..models.agentic_node import AgenticNode
        from ..models.approval_node import ApprovalNode
        from ..models.condition_node import ConditionNode
        from ..models.converge_node import ConvergeNode
        from ..models.http_request_node import HTTPRequestNode
        from ..models.loop_node import LoopNode
        from ..models.script_node import ScriptNode
        from ..models.switch_node import SwitchNode
        from ..models.wait_node import WaitNode
        from ..models.workflow_definition_edges_item import WorkflowDefinitionEdgesItem
        from ..models.workflow_definition_triggers_item import WorkflowDefinitionTriggersItem

        d = dict(src_dict)
        schema_version = cast(Literal["2.0.0"], d.pop("schema_version"))
        if schema_version != "2.0.0":
            raise ValueError(f"schema_version must match const '2.0.0', got '{schema_version}'")

        name = d.pop("name")

        triggers = []
        _triggers = d.pop("triggers")
        for triggers_item_data in _triggers:
            triggers_item = WorkflowDefinitionTriggersItem.from_dict(triggers_item_data)

            triggers.append(triggers_item)

        nodes = []
        _nodes = d.pop("nodes")
        for nodes_item_data in _nodes:

            def _parse_nodes_item(
                data: object,
            ) -> (
                AAPJobTemplateNode
                | AAPWorkflowJobTemplateNode
                | AgenticNode
                | ApprovalNode
                | ConditionNode
                | ConvergeNode
                | HTTPRequestNode
                | LoopNode
                | ScriptNode
                | SwitchNode
                | WaitNode
            ):
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    nodes_item_type_0 = AAPJobTemplateNode.from_dict(data)

                    return nodes_item_type_0
                except (TypeError, ValueError, AttributeError, KeyError):
                    pass
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    nodes_item_type_1 = AAPWorkflowJobTemplateNode.from_dict(data)

                    return nodes_item_type_1
                except (TypeError, ValueError, AttributeError, KeyError):
                    pass
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    nodes_item_type_2 = HTTPRequestNode.from_dict(data)

                    return nodes_item_type_2
                except (TypeError, ValueError, AttributeError, KeyError):
                    pass
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    nodes_item_type_3 = AgenticNode.from_dict(data)

                    return nodes_item_type_3
                except (TypeError, ValueError, AttributeError, KeyError):
                    pass
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    nodes_item_type_4 = ScriptNode.from_dict(data)

                    return nodes_item_type_4
                except (TypeError, ValueError, AttributeError, KeyError):
                    pass
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    nodes_item_type_5 = ApprovalNode.from_dict(data)

                    return nodes_item_type_5
                except (TypeError, ValueError, AttributeError, KeyError):
                    pass
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    nodes_item_type_6 = ConditionNode.from_dict(data)

                    return nodes_item_type_6
                except (TypeError, ValueError, AttributeError, KeyError):
                    pass
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    nodes_item_type_7 = SwitchNode.from_dict(data)

                    return nodes_item_type_7
                except (TypeError, ValueError, AttributeError, KeyError):
                    pass
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    nodes_item_type_8 = LoopNode.from_dict(data)

                    return nodes_item_type_8
                except (TypeError, ValueError, AttributeError, KeyError):
                    pass
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    nodes_item_type_9 = ConvergeNode.from_dict(data)

                    return nodes_item_type_9
                except (TypeError, ValueError, AttributeError, KeyError):
                    pass
                if not isinstance(data, dict):
                    raise TypeError()
                nodes_item_type_10 = WaitNode.from_dict(data)

                return nodes_item_type_10

            nodes_item = _parse_nodes_item(nodes_item_data)

            nodes.append(nodes_item)

        edges = []
        _edges = d.pop("edges")
        for edges_item_data in _edges:
            edges_item = WorkflowDefinitionEdgesItem.from_dict(edges_item_data)

            edges.append(edges_item)

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        workflow_definition = cls(
            schema_version=schema_version,
            name=name,
            triggers=triggers,
            nodes=nodes,
            edges=edges,
            description=description,
        )

        return workflow_definition
