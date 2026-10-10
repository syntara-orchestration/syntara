from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.batch_approval_decision import BatchApprovalDecision


T = TypeVar("T", bound="BatchApprovalRequest")


@_attrs_define
class BatchApprovalRequest:
    """Request payload for submitting multiple approval decisions at once.

    Attributes:
        decisions (list[BatchApprovalDecision]): List of approval decisions to submit
    """

    decisions: list[BatchApprovalDecision]

    def to_dict(self) -> dict[str, Any]:
        decisions = []
        for decisions_item_data in self.decisions:
            decisions_item = decisions_item_data.to_dict()
            decisions.append(decisions_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "decisions": decisions,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.batch_approval_decision import BatchApprovalDecision

        d = dict(src_dict)
        decisions = []
        _decisions = d.pop("decisions")
        for decisions_item_data in _decisions:
            decisions_item = BatchApprovalDecision.from_dict(decisions_item_data)

            decisions.append(decisions_item)

        batch_approval_request = cls(
            decisions=decisions,
        )

        return batch_approval_request
