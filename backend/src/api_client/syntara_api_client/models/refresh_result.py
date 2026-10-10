from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="RefreshResult")


@_attrs_define
class RefreshResult:
    """Result returned by POST /integrations/{id}/refresh.

    Covers both MCP tool and LLM model refreshes. ``missing_count``
    reflects resources no longer offered by the provider: MCP tools are
    marked MISSING and LLM models are counted as missing. Rows are
    preserved and ``enabled`` is never changed by discovery (it is
    admin-controlled).

        Attributes:
            synced_count (int): Number of new resource records created
            updated_count (int): Number of existing resource records updated
            missing_count (int): Number of resources no longer offered by the provider
            refreshed_at (datetime.datetime | None | Unset): Timestamp when the refresh completed
    """

    synced_count: int
    updated_count: int
    missing_count: int
    refreshed_at: datetime.datetime | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        synced_count = self.synced_count

        updated_count = self.updated_count

        missing_count = self.missing_count

        refreshed_at: None | str | Unset
        if isinstance(self.refreshed_at, Unset):
            refreshed_at = UNSET
        elif isinstance(self.refreshed_at, datetime.datetime):
            refreshed_at = self.refreshed_at.isoformat()
        else:
            refreshed_at = self.refreshed_at

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "synced_count": synced_count,
                "updated_count": updated_count,
                "missing_count": missing_count,
            }
        )
        if refreshed_at is not UNSET:
            field_dict["refreshed_at"] = refreshed_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        synced_count = d.pop("synced_count")

        updated_count = d.pop("updated_count")

        missing_count = d.pop("missing_count")

        def _parse_refreshed_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                refreshed_at_type_0 = isoparse(data)

                return refreshed_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        refreshed_at = _parse_refreshed_at(d.pop("refreshed_at", UNSET))

        refresh_result = cls(
            synced_count=synced_count,
            updated_count=updated_count,
            missing_count=missing_count,
            refreshed_at=refreshed_at,
        )

        return refresh_result
