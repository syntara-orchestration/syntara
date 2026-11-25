from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.workflow_used_by_count import WorkflowUsedByCount


T = TypeVar("T", bound="WorkflowUsedByCountsResponse")


@_attrs_define
class WorkflowUsedByCountsResponse:
    """Batch Used-By totals for a set of workflows.

    Totals are counted across all projects (matching the Used-By badge). Only workflows the caller may read are
    included; others are omitted so the endpoint cannot probe counts for workflows outside the caller's visibility.

        Attributes:
            counts (list[WorkflowUsedByCount] | Unset):
    """

    counts: list[WorkflowUsedByCount] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        counts: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.counts, Unset):
            counts = []
            for counts_item_data in self.counts:
                counts_item = counts_item_data.to_dict()
                counts.append(counts_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if counts is not UNSET:
            field_dict["counts"] = counts

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.workflow_used_by_count import WorkflowUsedByCount

        d = dict(src_dict)
        _counts = d.pop("counts", UNSET)
        counts: list[WorkflowUsedByCount] | Unset = UNSET
        if _counts is not UNSET:
            counts = []
            for counts_item_data in _counts:
                counts_item = WorkflowUsedByCount.from_dict(counts_item_data)

                counts.append(counts_item)

        workflow_used_by_counts_response = cls(
            counts=counts,
        )

        workflow_used_by_counts_response.additional_properties = d
        return workflow_used_by_counts_response

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
