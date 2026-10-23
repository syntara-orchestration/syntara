from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.sub_workflow_executor_parameters_input_mapping import SubWorkflowExecutorParametersInputMapping


T = TypeVar("T", bound="SubWorkflowExecutorParameters")


@_attrs_define
class SubWorkflowExecutorParameters:
    """Parameters for Sub-workflow executor.

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

        Attributes:
            workflow_id (UUID): UUID of the selected child workflow in the same Project (latest published version).
            trigger_node_id (str): Graph node ID of the Subworkflow Trigger to invoke in the child workflow
            input_mapping (SubWorkflowExecutorParametersInputMapping | Unset): Mapping of child workflow input field names
                to static values or template expressions. Keys are child workflow input field names; values can be static types
                (string, int, bool, dict, list) or template expression strings (${step_id.field.path}). Max 100 entries.
    """

    workflow_id: UUID
    trigger_node_id: str
    input_mapping: SubWorkflowExecutorParametersInputMapping | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        workflow_id = str(self.workflow_id)

        trigger_node_id = self.trigger_node_id

        input_mapping: dict[str, Any] | Unset = UNSET
        if not isinstance(self.input_mapping, Unset):
            input_mapping = self.input_mapping.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "workflow_id": workflow_id,
                "trigger_node_id": trigger_node_id,
            }
        )
        if input_mapping is not UNSET:
            field_dict["input_mapping"] = input_mapping

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.sub_workflow_executor_parameters_input_mapping import SubWorkflowExecutorParametersInputMapping

        d = dict(src_dict)
        workflow_id = UUID(d.pop("workflow_id"))

        trigger_node_id = d.pop("trigger_node_id")

        _input_mapping = d.pop("input_mapping", UNSET)
        input_mapping: SubWorkflowExecutorParametersInputMapping | Unset
        if isinstance(_input_mapping, Unset):
            input_mapping = UNSET
        else:
            input_mapping = SubWorkflowExecutorParametersInputMapping.from_dict(_input_mapping)

        sub_workflow_executor_parameters = cls(
            workflow_id=workflow_id,
            trigger_node_id=trigger_node_id,
            input_mapping=input_mapping,
        )

        sub_workflow_executor_parameters.additional_properties = d
        return sub_workflow_executor_parameters

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
