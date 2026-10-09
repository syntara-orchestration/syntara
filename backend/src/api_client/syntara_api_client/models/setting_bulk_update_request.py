from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.setting_bulk_update_item import SettingBulkUpdateItem


T = TypeVar("T", bound="SettingBulkUpdateRequest")


@_attrs_define
class SettingBulkUpdateRequest:
    """Request body for PATCH /settings (bulk update).

    Attributes:
        updates (list[SettingBulkUpdateItem]):
    """

    updates: list[SettingBulkUpdateItem]

    def to_dict(self) -> dict[str, Any]:
        updates = []
        for updates_item_data in self.updates:
            updates_item = updates_item_data.to_dict()
            updates.append(updates_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "updates": updates,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.setting_bulk_update_item import SettingBulkUpdateItem

        d = dict(src_dict)
        updates = []
        _updates = d.pop("updates")
        for updates_item_data in _updates:
            updates_item = SettingBulkUpdateItem.from_dict(updates_item_data)

            updates.append(updates_item)

        setting_bulk_update_request = cls(
            updates=updates,
        )

        return setting_bulk_update_request
