from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="BreakingChange")


@_attrs_define
class BreakingChange:
    """A single breaking change detected in an output schema.

    Attributes:
        change_type: Category of output contract change.
        field_path: Dotted path to the affected public output field.
        old_type: Previous JSON Schema type, when applicable.
        new_type: Candidate JSON Schema type, when applicable.
        description: Human-readable description

        Attributes:
            change_type (str): Change category, such as removed_output, type_change, new_required_output, added_output,
                required_output, optional_output, constraint_change, mapping_changed, or removed_trigger.
            field_path (str): Dotted path to the affected public output field, or the trigger ID when a trigger is removed.
            description (str): Human-readable explanation of the contract change.
            old_type (None | str | Unset): Previous JSON Schema type, when applicable.
            new_type (None | str | Unset): Candidate JSON Schema type, when applicable.
            is_breaking (bool | Unset): Whether this change can break consumers of the published output contract. Default:
                True.
    """

    change_type: str
    field_path: str
    description: str
    old_type: None | str | Unset = UNSET
    new_type: None | str | Unset = UNSET
    is_breaking: bool | Unset = True

    def to_dict(self) -> dict[str, Any]:
        change_type = self.change_type

        field_path = self.field_path

        description = self.description

        old_type: None | str | Unset
        if isinstance(self.old_type, Unset):
            old_type = UNSET
        else:
            old_type = self.old_type

        new_type: None | str | Unset
        if isinstance(self.new_type, Unset):
            new_type = UNSET
        else:
            new_type = self.new_type

        is_breaking = self.is_breaking

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "change_type": change_type,
                "field_path": field_path,
                "description": description,
            }
        )
        if old_type is not UNSET:
            field_dict["old_type"] = old_type
        if new_type is not UNSET:
            field_dict["new_type"] = new_type
        if is_breaking is not UNSET:
            field_dict["is_breaking"] = is_breaking

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        change_type = d.pop("change_type")

        field_path = d.pop("field_path")

        description = d.pop("description")

        def _parse_old_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        old_type = _parse_old_type(d.pop("old_type", UNSET))

        def _parse_new_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        new_type = _parse_new_type(d.pop("new_type", UNSET))

        is_breaking = d.pop("is_breaking", UNSET)

        breaking_change = cls(
            change_type=change_type,
            field_path=field_path,
            description=description,
            old_type=old_type,
            new_type=new_type,
            is_breaking=is_breaking,
        )

        return breaking_change
