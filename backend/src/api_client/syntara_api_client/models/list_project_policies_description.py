from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ListProjectPoliciesDescription")


@_attrs_define
class ListProjectPoliciesDescription:
    """
    Attributes:
        contains (str | Unset):
        eq (str | Unset):
        gt (str | Unset):
        gte (str | Unset):
        in_ (str | Unset):
        isnull (bool | Unset):
        lt (str | Unset):
        lte (str | Unset):
        starts_with (str | Unset):
    """

    contains: str | Unset = UNSET
    eq: str | Unset = UNSET
    gt: str | Unset = UNSET
    gte: str | Unset = UNSET
    in_: str | Unset = UNSET
    isnull: bool | Unset = UNSET
    lt: str | Unset = UNSET
    lte: str | Unset = UNSET
    starts_with: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        contains = self.contains

        eq = self.eq

        gt = self.gt

        gte = self.gte

        in_ = self.in_

        isnull = self.isnull

        lt = self.lt

        lte = self.lte

        starts_with = self.starts_with

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if contains is not UNSET:
            field_dict["contains"] = contains
        if eq is not UNSET:
            field_dict["eq"] = eq
        if gt is not UNSET:
            field_dict["gt"] = gt
        if gte is not UNSET:
            field_dict["gte"] = gte
        if in_ is not UNSET:
            field_dict["in"] = in_
        if isnull is not UNSET:
            field_dict["isnull"] = isnull
        if lt is not UNSET:
            field_dict["lt"] = lt
        if lte is not UNSET:
            field_dict["lte"] = lte
        if starts_with is not UNSET:
            field_dict["starts_with"] = starts_with

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        contains = d.pop("contains", UNSET)

        eq = d.pop("eq", UNSET)

        gt = d.pop("gt", UNSET)

        gte = d.pop("gte", UNSET)

        in_ = d.pop("in", UNSET)

        isnull = d.pop("isnull", UNSET)

        lt = d.pop("lt", UNSET)

        lte = d.pop("lte", UNSET)

        starts_with = d.pop("starts_with", UNSET)

        list_project_policies_description = cls(
            contains=contains,
            eq=eq,
            gt=gt,
            gte=gte,
            in_=in_,
            isnull=isnull,
            lt=lt,
            lte=lte,
            starts_with=starts_with,
        )

        list_project_policies_description.additional_properties = d
        return list_project_policies_description

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
