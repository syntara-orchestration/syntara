from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ListGroupsName")


@_attrs_define
class ListGroupsName:
    """
    Attributes:
        contains (str | Unset): Substring to match within the name (case-insensitive). ?name[contains]=<substring>
        starts_with (str | Unset): Prefix to match at the start of the name (case-insensitive).
            ?name[starts_with]=<prefix>
        eq (str | Unset): Exact match of the name (case-insensitive). ?name[eq]=<name>
        gt (str | Unset): Greater than comparison (lexicographical). ?name[gt]=<name>
        gte (str | Unset): Greater than or equal comparison (lexicographical). ?name[gte]=<name>
        lt (str | Unset): Less than comparison (lexicographical). ?name[lt]=<name>
        in_ (str | Unset):
        lte (str | Unset): Less than or equal comparison (lexicographical). ?name[lte]=<name>
    """

    contains: str | Unset = UNSET
    starts_with: str | Unset = UNSET
    eq: str | Unset = UNSET
    gt: str | Unset = UNSET
    gte: str | Unset = UNSET
    lt: str | Unset = UNSET
    in_: str | Unset = UNSET
    lte: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        contains = self.contains

        starts_with = self.starts_with

        eq = self.eq

        gt = self.gt

        gte = self.gte

        lt = self.lt

        in_ = self.in_

        lte = self.lte

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if contains is not UNSET:
            field_dict["contains"] = contains
        if starts_with is not UNSET:
            field_dict["starts_with"] = starts_with
        if eq is not UNSET:
            field_dict["eq"] = eq
        if gt is not UNSET:
            field_dict["gt"] = gt
        if gte is not UNSET:
            field_dict["gte"] = gte
        if lt is not UNSET:
            field_dict["lt"] = lt
        if in_ is not UNSET:
            field_dict["in"] = in_
        if lte is not UNSET:
            field_dict["lte"] = lte

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        contains = d.pop("contains", UNSET)

        starts_with = d.pop("starts_with", UNSET)

        eq = d.pop("eq", UNSET)

        gt = d.pop("gt", UNSET)

        gte = d.pop("gte", UNSET)

        lt = d.pop("lt", UNSET)

        in_ = d.pop("in", UNSET)

        lte = d.pop("lte", UNSET)

        list_groups_name = cls(
            contains=contains,
            starts_with=starts_with,
            eq=eq,
            gt=gt,
            gte=gte,
            lt=lt,
            in_=in_,
            lte=lte,
        )

        list_groups_name.additional_properties = d
        return list_groups_name

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
