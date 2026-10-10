from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.initial_tool_selection_parameters_type_0_item import InitialToolSelectionParametersType0Item


T = TypeVar("T", bound="InitialToolSelection")


@_attrs_define
class InitialToolSelection:
    """A tool from the discover step with the user's enabled/disabled choice.

    Attributes:
        name (str): Tool name as returned by the discover endpoint
        description (None | str | Unset): Tool description
        enabled (bool | Unset): Whether the user enabled this tool Default: True.
        parameters (list[InitialToolSelectionParametersType0Item] | None | Unset): Tool parameters from discovery
    """

    name: str
    description: None | str | Unset = UNSET
    enabled: bool | Unset = True
    parameters: list[InitialToolSelectionParametersType0Item] | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        enabled = self.enabled

        parameters: list[dict[str, Any]] | None | Unset
        if isinstance(self.parameters, Unset):
            parameters = UNSET
        elif isinstance(self.parameters, list):
            parameters = []
            for parameters_type_0_item_data in self.parameters:
                parameters_type_0_item = parameters_type_0_item_data.to_dict()
                parameters.append(parameters_type_0_item)

        else:
            parameters = self.parameters

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "name": name,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if parameters is not UNSET:
            field_dict["parameters"] = parameters

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.initial_tool_selection_parameters_type_0_item import InitialToolSelectionParametersType0Item

        d = dict(src_dict)
        name = d.pop("name")

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        enabled = d.pop("enabled", UNSET)

        def _parse_parameters(data: object) -> list[InitialToolSelectionParametersType0Item] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                parameters_type_0 = []
                _parameters_type_0 = data
                for parameters_type_0_item_data in _parameters_type_0:
                    parameters_type_0_item = InitialToolSelectionParametersType0Item.from_dict(
                        parameters_type_0_item_data
                    )

                    parameters_type_0.append(parameters_type_0_item)

                return parameters_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[InitialToolSelectionParametersType0Item] | None | Unset, data)

        parameters = _parse_parameters(d.pop("parameters", UNSET))

        initial_tool_selection = cls(
            name=name,
            description=description,
            enabled=enabled,
            parameters=parameters,
        )

        return initial_tool_selection
