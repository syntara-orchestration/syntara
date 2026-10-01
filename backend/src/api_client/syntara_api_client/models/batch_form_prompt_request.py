from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.batch_form_prompt_update import BatchFormPromptUpdate


T = TypeVar("T", bound="BatchFormPromptRequest")


@_attrs_define
class BatchFormPromptRequest:
    """Request payload for batch updating form prompt statuses.

    Attributes:
        updates (list[BatchFormPromptUpdate]): List of form prompt status updates to apply
    """

    updates: list[BatchFormPromptUpdate]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        updates = []
        for updates_item_data in self.updates:
            updates_item = updates_item_data.to_dict()
            updates.append(updates_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "updates": updates,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.batch_form_prompt_update import BatchFormPromptUpdate

        d = dict(src_dict)
        updates = []
        _updates = d.pop("updates")
        for updates_item_data in _updates:
            updates_item = BatchFormPromptUpdate.from_dict(updates_item_data)

            updates.append(updates_item)

        batch_form_prompt_request = cls(
            updates=updates,
        )

        batch_form_prompt_request.additional_properties = d
        return batch_form_prompt_request

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
