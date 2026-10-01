from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.batch_update_result import BatchUpdateResult


T = TypeVar("T", bound="BatchUpdateResponse")


@_attrs_define
class BatchUpdateResponse:
    """Response payload for batch form prompt updates.

    Attributes:
        results (list[BatchUpdateResult]): Individual update results
        total_success (int): Count of successful updates
        total_failed (int): Count of failed updates
    """

    results: list[BatchUpdateResult]
    total_success: int
    total_failed: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        results = []
        for results_item_data in self.results:
            results_item = results_item_data.to_dict()
            results.append(results_item)

        total_success = self.total_success

        total_failed = self.total_failed

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "results": results,
                "total_success": total_success,
                "total_failed": total_failed,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.batch_update_result import BatchUpdateResult

        d = dict(src_dict)
        results = []
        _results = d.pop("results")
        for results_item_data in _results:
            results_item = BatchUpdateResult.from_dict(results_item_data)

            results.append(results_item)

        total_success = d.pop("total_success")

        total_failed = d.pop("total_failed")

        batch_update_response = cls(
            results=results,
            total_success=total_success,
            total_failed=total_failed,
        )

        batch_update_response.additional_properties = d
        return batch_update_response

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
