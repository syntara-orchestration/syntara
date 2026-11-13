from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.integration_read import IntegrationRead
    from ..models.kafka_integration_read import KafkaIntegrationRead


T = TypeVar("T", bound="IntegrationCatalogListResponse")


@_attrs_define
class IntegrationCatalogListResponse:
    """Paginated integrations of every supported type.

    Attributes:
        resources (list[IntegrationRead | KafkaIntegrationRead]): Array of resources in current page
        next_ (None | str | Unset): Cursor for next page of results
        prev (None | str | Unset): Cursor for previous page of results
        total (int | None | Unset): Total count of resources (only when include_total=true)
    """

    resources: list[IntegrationRead | KafkaIntegrationRead]
    next_: None | str | Unset = UNSET
    prev: None | str | Unset = UNSET
    total: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.integration_read import IntegrationRead

        resources = []
        for resources_item_data in self.resources:
            resources_item: dict[str, Any]
            if isinstance(resources_item_data, IntegrationRead):
                resources_item = resources_item_data.to_dict()
            else:
                resources_item = resources_item_data.to_dict()

            resources.append(resources_item)

        next_: None | str | Unset
        if isinstance(self.next_, Unset):
            next_ = UNSET
        else:
            next_ = self.next_

        prev: None | str | Unset
        if isinstance(self.prev, Unset):
            prev = UNSET
        else:
            prev = self.prev

        total: int | None | Unset
        if isinstance(self.total, Unset):
            total = UNSET
        else:
            total = self.total

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "resources": resources,
            }
        )
        if next_ is not UNSET:
            field_dict["next"] = next_
        if prev is not UNSET:
            field_dict["prev"] = prev
        if total is not UNSET:
            field_dict["total"] = total

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.integration_read import IntegrationRead
        from ..models.kafka_integration_read import KafkaIntegrationRead

        d = dict(src_dict)
        resources = []
        _resources = d.pop("resources")
        for resources_item_data in _resources:

            def _parse_resources_item(data: object) -> IntegrationRead | KafkaIntegrationRead:
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    resources_item_type_0 = IntegrationRead.from_dict(data)

                    return resources_item_type_0
                except (TypeError, ValueError, AttributeError, KeyError):
                    pass
                if not isinstance(data, dict):
                    raise TypeError()
                resources_item_type_1 = KafkaIntegrationRead.from_dict(data)

                return resources_item_type_1

            resources_item = _parse_resources_item(resources_item_data)

            resources.append(resources_item)

        def _parse_next_(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        next_ = _parse_next_(d.pop("next", UNSET))

        def _parse_prev(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        prev = _parse_prev(d.pop("prev", UNSET))

        def _parse_total(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        total = _parse_total(d.pop("total", UNSET))

        integration_catalog_list_response = cls(
            resources=resources,
            next_=next_,
            prev=prev,
            total=total,
        )

        integration_catalog_list_response.additional_properties = d
        return integration_catalog_list_response

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
