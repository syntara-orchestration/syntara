from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from dateutil.parser import isoparse

from ..models.approval_request_status import ApprovalRequestStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.user_reference import UserReference


T = TypeVar("T", bound="BatchApprovalResult")


@_attrs_define
class BatchApprovalResult:
    """Confirmation for a single approval within a batch response.

    Attributes:
        approval_id (UUID): ID of the approval request
        success (bool): Whether the decision was successfully recorded
        status (ApprovalRequestStatus | None | Unset): New status after the decision (if successful)
        decided_at (datetime.datetime | None | Unset): When decision was recorded (if successful)
        decided_by (None | Unset | UserReference): User who made the decision (if successful)
        decision_notes (None | str | Unset): Notes provided with the decision (echoed back from request)
        error (None | str | Unset): Error message if the decision failed
    """

    approval_id: UUID
    success: bool
    status: ApprovalRequestStatus | None | Unset = UNSET
    decided_at: datetime.datetime | None | Unset = UNSET
    decided_by: None | Unset | UserReference = UNSET
    decision_notes: None | str | Unset = UNSET
    error: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.user_reference import UserReference

        approval_id = str(self.approval_id)

        success = self.success

        status: None | str | Unset
        if isinstance(self.status, Unset):
            status = UNSET
        elif isinstance(self.status, ApprovalRequestStatus):
            status = self.status.value
        else:
            status = self.status

        decided_at: None | str | Unset
        if isinstance(self.decided_at, Unset):
            decided_at = UNSET
        elif isinstance(self.decided_at, datetime.datetime):
            decided_at = self.decided_at.isoformat()
        else:
            decided_at = self.decided_at

        decided_by: dict[str, Any] | None | Unset
        if isinstance(self.decided_by, Unset):
            decided_by = UNSET
        elif isinstance(self.decided_by, UserReference):
            decided_by = self.decided_by.to_dict()
        else:
            decided_by = self.decided_by

        decision_notes: None | str | Unset
        if isinstance(self.decision_notes, Unset):
            decision_notes = UNSET
        else:
            decision_notes = self.decision_notes

        error: None | str | Unset
        if isinstance(self.error, Unset):
            error = UNSET
        else:
            error = self.error

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "approval_id": approval_id,
                "success": success,
            }
        )
        if status is not UNSET:
            field_dict["status"] = status
        if decided_at is not UNSET:
            field_dict["decided_at"] = decided_at
        if decided_by is not UNSET:
            field_dict["decided_by"] = decided_by
        if decision_notes is not UNSET:
            field_dict["decision_notes"] = decision_notes
        if error is not UNSET:
            field_dict["error"] = error

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.user_reference import UserReference

        d = dict(src_dict)
        approval_id = UUID(d.pop("approval_id"))

        success = d.pop("success")

        def _parse_status(data: object) -> ApprovalRequestStatus | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                status_type_0 = ApprovalRequestStatus(data)

                return status_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ApprovalRequestStatus | None | Unset, data)

        status = _parse_status(d.pop("status", UNSET))

        def _parse_decided_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                decided_at_type_0 = isoparse(data)

                return decided_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        decided_at = _parse_decided_at(d.pop("decided_at", UNSET))

        def _parse_decided_by(data: object) -> None | Unset | UserReference:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                decided_by_type_0 = UserReference.from_dict(data)

                return decided_by_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UserReference, data)

        decided_by = _parse_decided_by(d.pop("decided_by", UNSET))

        def _parse_decision_notes(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        decision_notes = _parse_decision_notes(d.pop("decision_notes", UNSET))

        def _parse_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error = _parse_error(d.pop("error", UNSET))

        batch_approval_result = cls(
            approval_id=approval_id,
            success=success,
            status=status,
            decided_at=decided_at,
            decided_by=decided_by,
            decision_notes=decision_notes,
            error=error,
        )

        return batch_approval_result
