from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="WhatCanIRequest")


@_attrs_define
class WhatCanIRequest:
    """Request body for the What can I? endpoint.

    Attributes:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
    """

    limit: int | Unset = 20
    cursor: None | str | Unset = UNSET
    sort: None | str | Unset = UNSET
    include_total: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        limit = self.limit

        cursor: None | str | Unset
        if isinstance(self.cursor, Unset):
            cursor = UNSET
        else:
            cursor = self.cursor

        sort: None | str | Unset
        if isinstance(self.sort, Unset):
            sort = UNSET
        else:
            sort = self.sort

        include_total = self.include_total

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if limit is not UNSET:
            field_dict["limit"] = limit
        if cursor is not UNSET:
            field_dict["cursor"] = cursor
        if sort is not UNSET:
            field_dict["sort"] = sort
        if include_total is not UNSET:
            field_dict["include_total"] = include_total

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        limit = d.pop("limit", UNSET)

        def _parse_cursor(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cursor = _parse_cursor(d.pop("cursor", UNSET))

        def _parse_sort(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        sort = _parse_sort(d.pop("sort", UNSET))

        include_total = d.pop("include_total", UNSET)

        what_can_i_request = cls(
            limit=limit,
            cursor=cursor,
            sort=sort,
            include_total=include_total,
        )

        return what_can_i_request
