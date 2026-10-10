from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="SettingBulkUpdateItem")


@_attrs_define
class SettingBulkUpdateItem:
    """A single setting update within a bulk request.

    Attributes:
        key (str):
        value (Any):
        expected_version (int | None | Unset):
    """

    key: str
    value: Any
    expected_version: int | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        key = self.key

        value = self.value

        expected_version: int | None | Unset
        if isinstance(self.expected_version, Unset):
            expected_version = UNSET
        else:
            expected_version = self.expected_version

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "key": key,
                "value": value,
            }
        )
        if expected_version is not UNSET:
            field_dict["expected_version"] = expected_version

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        key = d.pop("key")

        value = d.pop("value")

        def _parse_expected_version(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        expected_version = _parse_expected_version(d.pop("expected_version", UNSET))

        setting_bulk_update_item = cls(
            key=key,
            value=value,
            expected_version=expected_version,
        )

        return setting_bulk_update_item
