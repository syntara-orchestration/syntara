from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.blocked_step_type_reason import BlockedStepTypeReason

T = TypeVar("T", bound="BlockedStepType")


@_attrs_define
class BlockedStepType:
    """A step type the caller cannot author.

    Attributes:
        kind (str):
        label (str):
        reason (BlockedStepTypeReason):
        project (None | str):
    """

    kind: str
    label: str
    reason: BlockedStepTypeReason
    project: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        kind = self.kind

        label = self.label

        reason = self.reason.value

        project: None | str
        project = self.project

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "kind": kind,
                "label": label,
                "reason": reason,
                "project": project,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        kind = d.pop("kind")

        label = d.pop("label")

        reason = BlockedStepTypeReason(d.pop("reason"))

        def _parse_project(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        project = _parse_project(d.pop("project"))

        blocked_step_type = cls(
            kind=kind,
            label=label,
            reason=reason,
            project=project,
        )

        blocked_step_type.additional_properties = d
        return blocked_step_type

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
