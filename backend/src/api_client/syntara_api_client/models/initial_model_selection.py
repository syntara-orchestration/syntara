from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="InitialModelSelection")


@_attrs_define
class InitialModelSelection:
    """A model from the discover step with the user's enabled/disabled choice.

    Attributes:
        model_id (str): Provider model identifier from discover
        name (str): Human-readable display name
        description (None | str | Unset): Model description
        enabled (bool | Unset): Whether the user enabled this model Default: True.
        is_default (bool | Unset): Whether this is the default model Default: False.
    """

    model_id: str
    name: str
    description: None | str | Unset = UNSET
    enabled: bool | Unset = True
    is_default: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        model_id = self.model_id

        name = self.name

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        enabled = self.enabled

        is_default = self.is_default

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "model_id": model_id,
                "name": name,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if is_default is not UNSET:
            field_dict["is_default"] = is_default

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        model_id = d.pop("model_id")

        name = d.pop("name")

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        enabled = d.pop("enabled", UNSET)

        is_default = d.pop("is_default", UNSET)

        initial_model_selection = cls(
            model_id=model_id,
            name=name,
            description=description,
            enabled=enabled,
            is_default=is_default,
        )

        return initial_model_selection
