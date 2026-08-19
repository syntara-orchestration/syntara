from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="ListExecutionsUpdatedAt")


@_attrs_define
class ListExecutionsUpdatedAt:
    """
    Attributes:
        eq (datetime.datetime | Unset): Exact match of last update timestamp. ?updated_at[eq]=<timestamp>
        gt (datetime.datetime | Unset): Greater than comparison. ?updated_at[gt]=<timestamp>
        gte (datetime.datetime | Unset): Greater than or equal comparison. ?updated_at[gte]=<timestamp>
        lt (datetime.datetime | Unset): Less than comparison. ?updated_at[lt]=<timestamp>
        in_ (str | Unset):
        lte (datetime.datetime | Unset): Less than or equal comparison. ?updated_at[lte]=<timestamp>
    """

    eq: datetime.datetime | Unset = UNSET
    gt: datetime.datetime | Unset = UNSET
    gte: datetime.datetime | Unset = UNSET
    lt: datetime.datetime | Unset = UNSET
    in_: str | Unset = UNSET
    lte: datetime.datetime | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        eq: str | Unset = UNSET
        if not isinstance(self.eq, Unset):
            eq = self.eq.isoformat()

        gt: str | Unset = UNSET
        if not isinstance(self.gt, Unset):
            gt = self.gt.isoformat()

        gte: str | Unset = UNSET
        if not isinstance(self.gte, Unset):
            gte = self.gte.isoformat()

        lt: str | Unset = UNSET
        if not isinstance(self.lt, Unset):
            lt = self.lt.isoformat()

        in_ = self.in_

        lte: str | Unset = UNSET
        if not isinstance(self.lte, Unset):
            lte = self.lte.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
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
        _eq = d.pop("eq", UNSET)
        eq: datetime.datetime | Unset
        if isinstance(_eq, Unset):
            eq = UNSET
        else:
            eq = isoparse(_eq)

        _gt = d.pop("gt", UNSET)
        gt: datetime.datetime | Unset
        if isinstance(_gt, Unset):
            gt = UNSET
        else:
            gt = isoparse(_gt)

        _gte = d.pop("gte", UNSET)
        gte: datetime.datetime | Unset
        if isinstance(_gte, Unset):
            gte = UNSET
        else:
            gte = isoparse(_gte)

        _lt = d.pop("lt", UNSET)
        lt: datetime.datetime | Unset
        if isinstance(_lt, Unset):
            lt = UNSET
        else:
            lt = isoparse(_lt)

        in_ = d.pop("in", UNSET)

        _lte = d.pop("lte", UNSET)
        lte: datetime.datetime | Unset
        if isinstance(_lte, Unset):
            lte = UNSET
        else:
            lte = isoparse(_lte)

        list_executions_updated_at = cls(
            eq=eq,
            gt=gt,
            gte=gte,
            lt=lt,
            in_=in_,
            lte=lte,
        )

        list_executions_updated_at.additional_properties = d
        return list_executions_updated_at

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
