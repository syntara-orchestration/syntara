from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ListUsersDirectoryEmail")


@_attrs_define
class ListUsersDirectoryEmail:
    """
    Attributes:
        eq (str | Unset):
        in_ (str | Unset):
        isnull (bool | Unset):
    """

    eq: str | Unset = UNSET
    in_: str | Unset = UNSET
    isnull: bool | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        eq = self.eq

        in_ = self.in_

        isnull = self.isnull

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if eq is not UNSET:
            field_dict["eq"] = eq
        if in_ is not UNSET:
            field_dict["in"] = in_
        if isnull is not UNSET:
            field_dict["isnull"] = isnull

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        eq = d.pop("eq", UNSET)

        in_ = d.pop("in", UNSET)

        isnull = d.pop("isnull", UNSET)

        list_users_directory_email = cls(
            eq=eq,
            in_=in_,
            isnull=isnull,
        )

        list_users_directory_email.additional_properties = d
        return list_users_directory_email

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
