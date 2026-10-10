from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define

from ..models.batch_approval_decision_status import BatchApprovalDecisionStatus
from ..types import UNSET, Unset

T = TypeVar("T", bound="BatchApprovalDecision")


@_attrs_define
class BatchApprovalDecision:
    """Single decision within a batch approval request.

    Attributes:
        approval_id (UUID): ID of the approval request
        status (BatchApprovalDecisionStatus): Status values that can be submitted in batch approval decisions.

            This is a subset of ApprovalRequestStatus containing only system-actionable values.
        notes (None | str | Unset): Optional notes explaining the decision. Accepts either `notes` or `decision_notes`
            (the key returned in responses) as the request field name.
    """

    approval_id: UUID
    status: BatchApprovalDecisionStatus
    notes: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        approval_id = str(self.approval_id)

        status = self.status.value

        notes: None | str | Unset
        if isinstance(self.notes, Unset):
            notes = UNSET
        else:
            notes = self.notes

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "approval_id": approval_id,
                "status": status,
            }
        )
        if notes is not UNSET:
            field_dict["notes"] = notes

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        approval_id = UUID(d.pop("approval_id"))

        status = BatchApprovalDecisionStatus(d.pop("status"))

        def _parse_notes(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        notes = _parse_notes(d.pop("notes", UNSET))

        batch_approval_decision = cls(
            approval_id=approval_id,
            status=status,
            notes=notes,
        )

        return batch_approval_decision
