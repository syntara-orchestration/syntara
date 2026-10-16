from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="SubWorkflowExecutorParametersInputMapping")


@_attrs_define
class SubWorkflowExecutorParametersInputMapping:
    """Mapping of child workflow input field names to static values or template expressions. Keys are child workflow input
    field names; values can be static types (string, int, bool, dict, list) or template expression strings
    (${step_id.field.path}). Max 100 entries.

    """

    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        sub_workflow_executor_parameters_input_mapping = cls()

        sub_workflow_executor_parameters_input_mapping.additional_properties = d
        return sub_workflow_executor_parameters_input_mapping

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
