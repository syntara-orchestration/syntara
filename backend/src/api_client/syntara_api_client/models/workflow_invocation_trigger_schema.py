from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.workflow_invocation_trigger_schema_input_schema import WorkflowInvocationTriggerSchemaInputSchema


T = TypeVar("T", bound="WorkflowInvocationTriggerSchema")


@_attrs_define
class WorkflowInvocationTriggerSchema:
    """One dedicated Subworkflow Trigger available for Reference mode.

    Attributes:
        trigger_node_id (str):
        name (None | str | Unset):
        input_schema (WorkflowInvocationTriggerSchemaInputSchema | Unset):
    """

    trigger_node_id: str
    name: None | str | Unset = UNSET
    input_schema: WorkflowInvocationTriggerSchemaInputSchema | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        trigger_node_id = self.trigger_node_id

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        input_schema: dict[str, Any] | Unset = UNSET
        if not isinstance(self.input_schema, Unset):
            input_schema = self.input_schema.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "trigger_node_id": trigger_node_id,
            }
        )
        if name is not UNSET:
            field_dict["name"] = name
        if input_schema is not UNSET:
            field_dict["input_schema"] = input_schema

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.workflow_invocation_trigger_schema_input_schema import WorkflowInvocationTriggerSchemaInputSchema

        d = dict(src_dict)
        trigger_node_id = d.pop("trigger_node_id")

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        _input_schema = d.pop("input_schema", UNSET)
        input_schema: WorkflowInvocationTriggerSchemaInputSchema | Unset
        if isinstance(_input_schema, Unset):
            input_schema = UNSET
        else:
            input_schema = WorkflowInvocationTriggerSchemaInputSchema.from_dict(_input_schema)

        workflow_invocation_trigger_schema = cls(
            trigger_node_id=trigger_node_id,
            name=name,
            input_schema=input_schema,
        )

        workflow_invocation_trigger_schema.additional_properties = d
        return workflow_invocation_trigger_schema

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
