from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

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
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        approval_id = str(self.approval_id)

        status = self.status.value

        notes: None | str | Unset
        if isinstance(self.notes, Unset):
            notes = UNSET
        else:
            notes = self.notes

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
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

        batch_approval_decision.additional_properties = d
        return batch_approval_decision

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
