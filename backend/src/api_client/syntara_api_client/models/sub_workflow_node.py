from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.node_position import NodePosition
    from ..models.node_settings_no_retry import NodeSettingsNoRetry
    from ..models.sub_workflow_executor_parameters import SubWorkflowExecutorParameters
    from ..models.sub_workflow_node_outputs_type_0 import SubWorkflowNodeOutputsType0


T = TypeVar("T", bound="SubWorkflowNode")


@_attrs_define
class SubWorkflowNode:
    """Sub-workflow executor node.

    Invokes another published workflow in reference mode and waits for its completion.
    The parent workflow can access child workflow outputs via template expressions.

        Attributes:
            id (str): Unique identifier for the node within the workflow
            type_ (Literal['sub_workflow']):
            parameters (SubWorkflowExecutorParameters): Parameters for Sub-workflow executor.

                Defines the design-time configuration for invoking a child workflow from
                a parent workflow. The Sub-workflow step always invokes the latest published
                version of the selected target workflow in the same Project (V1).

                When a workflow has multiple Subworkflow Triggers, the calling step must
                select a specific trigger to invoke via the trigger_node_id field.

                Attributes:
                    workflow_id: UUID of the selected child workflow to invoke.
                    trigger_node_id: Graph node ID of the Subworkflow Trigger to invoke.
                    input_mapping: Mapping of child workflow input field names to values.
                        Values can be static (string, int, bool, dict, list) or template
                        expressions (${step_id.field.path}).
            name (None | str | Unset): Human-readable name for the node
            description (None | str | Unset): Human-readable description of the node purpose
            outputs (None | SubWorkflowNodeOutputsType0 | Unset): Output extraction mapping
            position (NodePosition | None | Unset): Optional UI position hint
            settings (NodeSettingsNoRetry | None | Unset):
    """

    id: str
    type_: Literal["sub_workflow"]
    parameters: SubWorkflowExecutorParameters
    name: None | str | Unset = UNSET
    description: None | str | Unset = UNSET
    outputs: None | SubWorkflowNodeOutputsType0 | Unset = UNSET
    position: NodePosition | None | Unset = UNSET
    settings: NodeSettingsNoRetry | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.node_position import NodePosition
        from ..models.node_settings_no_retry import NodeSettingsNoRetry
        from ..models.sub_workflow_node_outputs_type_0 import SubWorkflowNodeOutputsType0

        id = self.id

        type_ = self.type_

        parameters = self.parameters.to_dict()

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        outputs: dict[str, Any] | None | Unset
        if isinstance(self.outputs, Unset):
            outputs = UNSET
        elif isinstance(self.outputs, SubWorkflowNodeOutputsType0):
            outputs = self.outputs.to_dict()
        else:
            outputs = self.outputs

        position: dict[str, Any] | None | Unset
        if isinstance(self.position, Unset):
            position = UNSET
        elif isinstance(self.position, NodePosition):
            position = self.position.to_dict()
        else:
            position = self.position

        settings: dict[str, Any] | None | Unset
        if isinstance(self.settings, Unset):
            settings = UNSET
        elif isinstance(self.settings, NodeSettingsNoRetry):
            settings = self.settings.to_dict()
        else:
            settings = self.settings

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "type": type_,
                "parameters": parameters,
            }
        )
        if name is not UNSET:
            field_dict["name"] = name
        if description is not UNSET:
            field_dict["description"] = description
        if outputs is not UNSET:
            field_dict["outputs"] = outputs
        if position is not UNSET:
            field_dict["position"] = position
        if settings is not UNSET:
            field_dict["settings"] = settings

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.node_position import NodePosition
        from ..models.node_settings_no_retry import NodeSettingsNoRetry
        from ..models.sub_workflow_executor_parameters import SubWorkflowExecutorParameters
        from ..models.sub_workflow_node_outputs_type_0 import SubWorkflowNodeOutputsType0

        d = dict(src_dict)
        id = d.pop("id")

        type_ = cast(Literal["sub_workflow"], d.pop("type"))
        if type_ != "sub_workflow":
            raise ValueError(f"type must match const 'sub_workflow', got '{type_}'")

        parameters = SubWorkflowExecutorParameters.from_dict(d.pop("parameters"))

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        def _parse_outputs(data: object) -> None | SubWorkflowNodeOutputsType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                outputs_type_0 = SubWorkflowNodeOutputsType0.from_dict(data)

                return outputs_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SubWorkflowNodeOutputsType0 | Unset, data)

        outputs = _parse_outputs(d.pop("outputs", UNSET))

        def _parse_position(data: object) -> NodePosition | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                position_type_0 = NodePosition.from_dict(data)

                return position_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(NodePosition | None | Unset, data)

        position = _parse_position(d.pop("position", UNSET))

        def _parse_settings(data: object) -> NodeSettingsNoRetry | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                settings_type_0 = NodeSettingsNoRetry.from_dict(data)

                return settings_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(NodeSettingsNoRetry | None | Unset, data)

        settings = _parse_settings(d.pop("settings", UNSET))

        sub_workflow_node = cls(
            id=id,
            type_=type_,
            parameters=parameters,
            name=name,
            description=description,
            outputs=outputs,
            position=position,
            settings=settings,
        )

        sub_workflow_node.additional_properties = d
        return sub_workflow_node

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
