from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="WorkflowLaunchRejectedStep")


@_attrs_define
class WorkflowLaunchRejectedStep:
    """A saved workflow step that caused launch authorization to fail.

    Attributes:
        denied_by (str):
        kind (str):
        node_id (str):
    """

    denied_by: str
    kind: str
    node_id: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        denied_by = self.denied_by

        kind = self.kind

        node_id = self.node_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "denied_by": denied_by,
                "kind": kind,
                "node_id": node_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        denied_by = d.pop("denied_by")

        kind = d.pop("kind")

        node_id = d.pop("node_id")

        workflow_launch_rejected_step = cls(
            denied_by=denied_by,
            kind=kind,
            node_id=node_id,
        )

        workflow_launch_rejected_step.additional_properties = d
        return workflow_launch_rejected_step

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
