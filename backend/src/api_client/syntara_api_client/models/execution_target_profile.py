from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ExecutionTargetProfile")


@_attrs_define
class ExecutionTargetProfile:
    """Execution Plane profile that selects a specific Execution Target.

    Attributes:
        type_ (Literal['execution_target']):
        execution_target_id (UUID): UUID of the Execution Plane execution target selected for this workload.
    """

    type_: Literal["execution_target"]
    execution_target_id: UUID
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        execution_target_id = str(self.execution_target_id)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "type": type_,
                "execution_target_id": execution_target_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        type_ = cast(Literal["execution_target"], d.pop("type"))
        if type_ != "execution_target":
            raise ValueError(f"type must match const 'execution_target', got '{type_}'")

        execution_target_id = UUID(d.pop("execution_target_id"))

        execution_target_profile = cls(
            type_=type_,
            execution_target_id=execution_target_id,
        )

        execution_target_profile.additional_properties = d
        return execution_target_profile

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
