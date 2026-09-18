from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.batch_form_prompt_status import BatchFormPromptStatus
from ..types import UNSET, Unset

T = TypeVar("T", bound="BatchFormPromptUpdate")


@_attrs_define
class BatchFormPromptUpdate:
    """Single update within a batch form prompt request.

    Attributes:
        prompt_id (UUID): ID of the form prompt
        status (BatchFormPromptStatus): Status values that can be submitted in batch form prompt updates.

            This is a system-actionable subset of FormPromptStatus.
        notes (None | str | Unset): Optional notes explaining the status change
    """

    prompt_id: UUID
    status: BatchFormPromptStatus
    notes: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        prompt_id = str(self.prompt_id)

        status = self.status.value

        notes: None | str | Unset
        if isinstance(self.notes, Unset):
            notes = UNSET
        else:
            notes = self.notes

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "prompt_id": prompt_id,
                "status": status,
            }
        )
        if notes is not UNSET:
            field_dict["notes"] = notes

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        prompt_id = UUID(d.pop("prompt_id"))

        status = BatchFormPromptStatus(d.pop("status"))

        def _parse_notes(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        notes = _parse_notes(d.pop("notes", UNSET))

        batch_form_prompt_update = cls(
            prompt_id=prompt_id,
            status=status,
            notes=notes,
        )

        batch_form_prompt_update.additional_properties = d
        return batch_form_prompt_update

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
