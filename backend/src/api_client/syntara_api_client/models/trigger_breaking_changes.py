from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.breaking_change import BreakingChange


T = TypeVar("T", bound="TriggerBreakingChanges")


@_attrs_define
class TriggerBreakingChanges:
    """Breaking changes for a single SubWorkflow Trigger.

    Attributes:
        trigger_id: ID of the trigger node
        trigger_name: Name of the trigger (if available)
        changes: List of breaking changes detected for this trigger

        Attributes:
            trigger_id (str): ID of the Subworkflow Trigger whose output contract changed.
            changes (list[BreakingChange]): Output contract changes detected for this trigger.
            trigger_name (None | str | Unset): Optional display name of the Subworkflow Trigger.
    """

    trigger_id: str
    changes: list[BreakingChange]
    trigger_name: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        trigger_id = self.trigger_id

        changes = []
        for changes_item_data in self.changes:
            changes_item = changes_item_data.to_dict()
            changes.append(changes_item)

        trigger_name: None | str | Unset
        if isinstance(self.trigger_name, Unset):
            trigger_name = UNSET
        else:
            trigger_name = self.trigger_name

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "trigger_id": trigger_id,
                "changes": changes,
            }
        )
        if trigger_name is not UNSET:
            field_dict["trigger_name"] = trigger_name

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.breaking_change import BreakingChange

        d = dict(src_dict)
        trigger_id = d.pop("trigger_id")

        changes = []
        _changes = d.pop("changes")
        for changes_item_data in _changes:
            changes_item = BreakingChange.from_dict(changes_item_data)

            changes.append(changes_item)

        def _parse_trigger_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        trigger_name = _parse_trigger_name(d.pop("trigger_name", UNSET))

        trigger_breaking_changes = cls(
            trigger_id=trigger_id,
            changes=changes,
            trigger_name=trigger_name,
        )

        return trigger_breaking_changes
