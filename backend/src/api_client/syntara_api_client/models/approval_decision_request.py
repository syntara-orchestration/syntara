from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.approval_decision_status import ApprovalDecisionStatus
from ..types import UNSET, Unset

T = TypeVar("T", bound="ApprovalDecisionRequest")


@_attrs_define
class ApprovalDecisionRequest:
    """Request payload for submitting an approval decision.

    Status values:
    - approved: Approver grants the request, workflow continues on approval path
    - rejected: Approver denies the request, workflow continues on rejection path
    - cancelled: Internal use only - set by workflow engine when parent workflow is cancelled

        Attributes:
            status (ApprovalDecisionStatus): Status values for approval decisions.

                This is a subset of ApprovalRequestStatus representing only the
                values that can be submitted in decision requests.
            notes (None | str | Unset): Optional notes explaining the decision. Accepts either `notes` or `decision_notes`
                (the key returned in responses) as the request field name.
    """

    status: ApprovalDecisionStatus
    notes: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
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
                "status": status,
            }
        )
        if notes is not UNSET:
            field_dict["notes"] = notes

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        status = ApprovalDecisionStatus(d.pop("status"))

        def _parse_notes(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        notes = _parse_notes(d.pop("notes", UNSET))

        approval_decision_request = cls(
            status=status,
            notes=notes,
        )

        approval_decision_request.additional_properties = d
        return approval_decision_request

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
