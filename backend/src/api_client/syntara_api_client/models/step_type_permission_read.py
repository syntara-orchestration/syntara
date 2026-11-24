from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.step_type_blocked_by import StepTypeBlockedBy


T = TypeVar("T", bound="StepTypePermissionRead")


@_attrs_define
class StepTypePermissionRead:
    """One step type as the calling principal sees it in one project.

    Attributes:
        kind: The step type identifier (a ``NodeType`` value).
        category: Registry grouping (trigger, flow_control or action).
        can_write: The caller's own ``step_type:write`` verdict for this kind
            in the requested project.
        blocked_by: Why the kind is blocked, or ``None`` when it is not.

        Attributes:
            kind (str):
            category (str):
            can_write (bool):
            blocked_by (None | StepTypeBlockedBy | Unset):
    """

    kind: str
    category: str
    can_write: bool
    blocked_by: None | StepTypeBlockedBy | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.step_type_blocked_by import StepTypeBlockedBy

        kind = self.kind

        category = self.category

        can_write = self.can_write

        blocked_by: dict[str, Any] | None | Unset
        if isinstance(self.blocked_by, Unset):
            blocked_by = UNSET
        elif isinstance(self.blocked_by, StepTypeBlockedBy):
            blocked_by = self.blocked_by.to_dict()
        else:
            blocked_by = self.blocked_by

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "kind": kind,
                "category": category,
                "can_write": can_write,
            }
        )
        if blocked_by is not UNSET:
            field_dict["blocked_by"] = blocked_by

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.step_type_blocked_by import StepTypeBlockedBy

        d = dict(src_dict)
        kind = d.pop("kind")

        category = d.pop("category")

        can_write = d.pop("can_write")

        def _parse_blocked_by(data: object) -> None | StepTypeBlockedBy | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                blocked_by_type_0 = StepTypeBlockedBy.from_dict(data)

                return blocked_by_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | StepTypeBlockedBy | Unset, data)

        blocked_by = _parse_blocked_by(d.pop("blocked_by", UNSET))

        step_type_permission_read = cls(
            kind=kind,
            category=category,
            can_write=can_write,
            blocked_by=blocked_by,
        )

        step_type_permission_read.additional_properties = d
        return step_type_permission_read

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
