from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="NodeSettingsCofDisabled")


@_attrs_define
class NodeSettingsCofDisabled:
    """Settings with disabled and continue_on_failure (wait, form_prompt).

    Attributes:
        continue_on_failure (bool | None | Unset):
        disabled (bool | None | Unset):
    """

    continue_on_failure: bool | None | Unset = UNSET
    disabled: bool | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        continue_on_failure: bool | None | Unset
        if isinstance(self.continue_on_failure, Unset):
            continue_on_failure = UNSET
        else:
            continue_on_failure = self.continue_on_failure

        disabled: bool | None | Unset
        if isinstance(self.disabled, Unset):
            disabled = UNSET
        else:
            disabled = self.disabled

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if continue_on_failure is not UNSET:
            field_dict["continue_on_failure"] = continue_on_failure
        if disabled is not UNSET:
            field_dict["disabled"] = disabled

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_continue_on_failure(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        continue_on_failure = _parse_continue_on_failure(d.pop("continue_on_failure", UNSET))

        def _parse_disabled(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        disabled = _parse_disabled(d.pop("disabled", UNSET))

        node_settings_cof_disabled = cls(
            continue_on_failure=continue_on_failure,
            disabled=disabled,
        )

        return node_settings_cof_disabled
