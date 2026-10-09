from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.batch_approval_result import BatchApprovalResult


T = TypeVar("T", bound="BatchApprovalResponse")


@_attrs_define
class BatchApprovalResponse:
    """Response for batch approval submission.

    Attributes:
        results (list[BatchApprovalResult]): Individual results for each decision
        total_success (int): Number of successfully processed decisions
        total_failed (int): Number of failed decisions
    """

    results: list[BatchApprovalResult]
    total_success: int
    total_failed: int

    def to_dict(self) -> dict[str, Any]:
        results = []
        for results_item_data in self.results:
            results_item = results_item_data.to_dict()
            results.append(results_item)

        total_success = self.total_success

        total_failed = self.total_failed

        field_dict: dict[str, Any] = {}

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
        from ..models.batch_approval_result import BatchApprovalResult

        d = dict(src_dict)
        results = []
        _results = d.pop("results")
        for results_item_data in _results:
            results_item = BatchApprovalResult.from_dict(results_item_data)

            results.append(results_item)

        total_success = d.pop("total_success")

        total_failed = d.pop("total_failed")

        batch_approval_response = cls(
            results=results,
            total_success=total_success,
            total_failed=total_failed,
        )

        return batch_approval_response
