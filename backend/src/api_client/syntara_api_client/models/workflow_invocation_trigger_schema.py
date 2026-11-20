from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.workflow_invocation_trigger_schema_input_schema import WorkflowInvocationTriggerSchemaInputSchema
    from ..models.workflow_invocation_trigger_schema_output_schema_type_0 import (
        WorkflowInvocationTriggerSchemaOutputSchemaType0,
    )


T = TypeVar("T", bound="WorkflowInvocationTriggerSchema")


@_attrs_define
class WorkflowInvocationTriggerSchema:
    """One dedicated Subworkflow Trigger available for Reference mode.

    Attributes:
        trigger_node_id (str):
        name (None | str | Unset):
        input_schema (WorkflowInvocationTriggerSchemaInputSchema | Unset):
        output_schema (None | Unset | WorkflowInvocationTriggerSchemaOutputSchemaType0): JSON Schema defining the
            outputs exposed to parent workflows. Provides encapsulation—parent sees only declared fields, not internal child
            step structure.
    """

    trigger_node_id: str
    name: None | str | Unset = UNSET
    input_schema: WorkflowInvocationTriggerSchemaInputSchema | Unset = UNSET
    output_schema: None | Unset | WorkflowInvocationTriggerSchemaOutputSchemaType0 = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.workflow_invocation_trigger_schema_output_schema_type_0 import (
            WorkflowInvocationTriggerSchemaOutputSchemaType0,
        )

        trigger_node_id = self.trigger_node_id

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        input_schema: dict[str, Any] | Unset = UNSET
        if not isinstance(self.input_schema, Unset):
            input_schema = self.input_schema.to_dict()

        output_schema: dict[str, Any] | None | Unset
        if isinstance(self.output_schema, Unset):
            output_schema = UNSET
        elif isinstance(self.output_schema, WorkflowInvocationTriggerSchemaOutputSchemaType0):
            output_schema = self.output_schema.to_dict()
        else:
            output_schema = self.output_schema

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
        if output_schema is not UNSET:
            field_dict["output_schema"] = output_schema

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.workflow_invocation_trigger_schema_input_schema import WorkflowInvocationTriggerSchemaInputSchema
        from ..models.workflow_invocation_trigger_schema_output_schema_type_0 import (
            WorkflowInvocationTriggerSchemaOutputSchemaType0,
        )

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

        def _parse_output_schema(data: object) -> None | Unset | WorkflowInvocationTriggerSchemaOutputSchemaType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                output_schema_type_0 = WorkflowInvocationTriggerSchemaOutputSchemaType0.from_dict(data)

                return output_schema_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | WorkflowInvocationTriggerSchemaOutputSchemaType0, data)

        output_schema = _parse_output_schema(d.pop("output_schema", UNSET))

        workflow_invocation_trigger_schema = cls(
            trigger_node_id=trigger_node_id,
            name=name,
            input_schema=input_schema,
            output_schema=output_schema,
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
