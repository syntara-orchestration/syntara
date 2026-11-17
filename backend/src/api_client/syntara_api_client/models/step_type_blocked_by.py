from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="StepTypeBlockedBy")


@_attrs_define
class StepTypeBlockedBy:
    """The Blocked step type shape shared with the P5 save denial.
    It names the step type only: policy names and scopes are recorded
    in audit events, never shown to the caller (AC-3.g, R11).

    Attributes:
        kind: The step type identifier.
        label: Human-readable step type label.

        Attributes:
            kind (str):
            label (str):
    """

    kind: str
    label: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        kind = self.kind

        label = self.label

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "kind": kind,
                "label": label,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        kind = d.pop("kind")

        label = d.pop("label")

        step_type_blocked_by = cls(
            kind=kind,
            label=label,
        )

        step_type_blocked_by.additional_properties = d
        return step_type_blocked_by

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
