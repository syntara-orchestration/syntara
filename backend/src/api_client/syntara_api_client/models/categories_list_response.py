from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.setting_category_read import SettingCategoryRead


T = TypeVar("T", bound="CategoriesListResponse")


@_attrs_define
class CategoriesListResponse:
    """Response schema for listing setting categories.

    Attributes:
        resources (list[SettingCategoryRead]):
    """

    resources: list[SettingCategoryRead]

    def to_dict(self) -> dict[str, Any]:
        resources = []
        for resources_item_data in self.resources:
            resources_item = resources_item_data.to_dict()
            resources.append(resources_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "resources": resources,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.setting_category_read import SettingCategoryRead

        d = dict(src_dict)
        resources = []
        _resources = d.pop("resources")
        for resources_item_data in _resources:
            resources_item = SettingCategoryRead.from_dict(resources_item_data)

            resources.append(resources_item)

        categories_list_response = cls(
            resources=resources,
        )

        return categories_list_response
