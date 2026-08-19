from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ListWorkflowVersionsVersion")


@_attrs_define
class ListWorkflowVersionsVersion:
    """
    Attributes:
        eq (int | Unset):
        gt (int | Unset):
        gte (int | Unset):
        in_ (str | Unset):
        lt (int | Unset):
        lte (int | Unset):
    """

    eq: int | Unset = UNSET
    gt: int | Unset = UNSET
    gte: int | Unset = UNSET
    in_: str | Unset = UNSET
    lt: int | Unset = UNSET
    lte: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        eq = self.eq

        gt = self.gt

        gte = self.gte

        in_ = self.in_

        lt = self.lt

        lte = self.lte

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if eq is not UNSET:
            field_dict["eq"] = eq
        if gt is not UNSET:
            field_dict["gt"] = gt
        if gte is not UNSET:
            field_dict["gte"] = gte
        if in_ is not UNSET:
            field_dict["in"] = in_
        if lt is not UNSET:
            field_dict["lt"] = lt
        if lte is not UNSET:
            field_dict["lte"] = lte

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        eq = d.pop("eq", UNSET)

        gt = d.pop("gt", UNSET)

        gte = d.pop("gte", UNSET)

        in_ = d.pop("in", UNSET)

        lt = d.pop("lt", UNSET)

        lte = d.pop("lte", UNSET)

        list_workflow_versions_version = cls(
            eq=eq,
            gt=gt,
            gte=gte,
            in_=in_,
            lt=lt,
            lte=lte,
        )

        list_workflow_versions_version.additional_properties = d
        return list_workflow_versions_version

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
