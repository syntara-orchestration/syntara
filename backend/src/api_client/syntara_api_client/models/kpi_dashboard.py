from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.component_kpi_summary import ComponentKPISummary


T = TypeVar("T", bound="KPIDashboard")


@_attrs_define
class KPIDashboard:
    """Full KPI dashboard covering all Nexus components.

    Attributes:
        generated_at (datetime.datetime): Timestamp of generation
        components (list[ComponentKPISummary] | Unset):
    """

    generated_at: datetime.datetime
    components: list[ComponentKPISummary] | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        generated_at = self.generated_at.isoformat()

        components: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.components, Unset):
            components = []
            for components_item_data in self.components:
                components_item = components_item_data.to_dict()
                components.append(components_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "generated_at": generated_at,
            }
        )
        if components is not UNSET:
            field_dict["components"] = components

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.component_kpi_summary import ComponentKPISummary

        d = dict(src_dict)
        generated_at = isoparse(d.pop("generated_at"))

        _components = d.pop("components", UNSET)
        components: list[ComponentKPISummary] | Unset = UNSET
        if _components is not UNSET:
            components = []
            for components_item_data in _components:
                components_item = ComponentKPISummary.from_dict(components_item_data)

                components.append(components_item)

        kpi_dashboard = cls(
            generated_at=generated_at,
            components=components,
        )

        return kpi_dashboard
