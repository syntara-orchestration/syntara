from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ListExecutionsId")


@_attrs_define
class ListExecutionsId:
    """
    Attributes:
        eq (UUID | Unset):
        in_ (str | Unset):
    """

    eq: UUID | Unset = UNSET
    in_: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        eq: str | Unset = UNSET
        if not isinstance(self.eq, Unset):
            eq = str(self.eq)

        in_ = self.in_

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if eq is not UNSET:
            field_dict["eq"] = eq
        if in_ is not UNSET:
            field_dict["in"] = in_

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        _eq = d.pop("eq", UNSET)
        eq: UUID | Unset
        if isinstance(_eq, Unset):
            eq = UNSET
        else:
            eq = UUID(_eq)

        in_ = d.pop("in", UNSET)

        list_executions_id = cls(
            eq=eq,
            in_=in_,
        )

        list_executions_id.additional_properties = d
        return list_executions_id

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
