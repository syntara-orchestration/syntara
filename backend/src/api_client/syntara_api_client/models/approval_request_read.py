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
    from ..models.activity_summary import ActivitySummary
    from ..models.approval_request_read_labels import ApprovalRequestReadLabels
    from ..models.approver_group_summary import ApproverGroupSummary
    from ..models.approver_user_summary import ApproverUserSummary
    from ..models.user_reference import UserReference
    from ..models.workflow_context import WorkflowContext


T = TypeVar("T", bound="ApprovalRequestRead")


@_attrs_define
class ApprovalRequestRead:
    """ApprovalRequest API response model with typed nested fields.

    Overrides the JSONB dict fields from BaseApprovalRequest with typed models
    so API consumers get proper validation and type safety. Pydantic coerces
    the raw dicts from the database into these typed models during serialization.

        Attributes:
            project_id (UUID): Project this approval belongs to (denormalized from execution)
            execution_id (UUID): Parent execution ID
            approval_node_id (str): Canvas node ID from the workflow definition
            name (str): Human-readable name for the approval request
            next_step_approved (ActivitySummary): Activity summary for workflow context.

                Passed through from the workflow engine as-is. Contains at minimum
                ``id``, ``name``, ``type``, and usually ``config`` with the full
                activity parameters so approvers can see what the step will do.
            workflow_context (WorkflowContext): Workflow Context for approvers.

                Essential context for approvers to make a decision.
                Contains workflow identification, inputs, and the output from the immediately
                preceding activity.
            id (UUID | Unset): Unique identifier for the resource Example: 550e8400-e29b-41d4-a716-446655440000.
            created_at (datetime.datetime | Unset): Timestamp when resource was created Example: 2025-10-09T12:00:00Z.
            updated_at (datetime.datetime | Unset): Timestamp when resource was last updated Example: 2025-10-09T12:30:00Z.
            labels (ApprovalRequestReadLabels | Unset): Key-value pairs for resource labeling and filtering Example:
                {'environment': 'production', 'region': 'us-east-1', 'team': 'platform'}.
            loop_iteration_path (list[int] | Unset): Enclosing-loop indices, outermost first (empty when not inside a loop)
            prompt (None | str | Unset): Resolved guidance message from the approval node, shown to approvers
            status (ApprovalRequestStatus | Unset): Approval request status enumeration.
            timeout_at (datetime.datetime | None | Unset): When this request expires
            next_step_rejected (ActivitySummary | None | Unset): First activity that executes if rejected
            approver_users (list[ApproverUserSummary] | Unset): Users who can approve this request (empty = any user with
                permission)
            approver_groups (list[ApproverGroupSummary] | Unset): Groups whose members can approve this request
            decided_by (None | Unset | UserReference): User who made the decision
            decided_at (datetime.datetime | None | Unset): When decision was made
            decision_notes (None | str | Unset): Notes provided with decision
            signal_delivery_error (None | str | Unset): Error if the workflow signal failed after a decision. Only present
                in the decide response; null on subsequent reads.
    """

    project_id: UUID
    execution_id: UUID
    approval_node_id: str
    name: str
    next_step_approved: ActivitySummary
    workflow_context: WorkflowContext
    id: UUID | Unset = UNSET
    created_at: datetime.datetime | Unset = UNSET
    updated_at: datetime.datetime | Unset = UNSET
    labels: ApprovalRequestReadLabels | Unset = UNSET
    loop_iteration_path: list[int] | Unset = UNSET
    prompt: None | str | Unset = UNSET
    status: ApprovalRequestStatus | Unset = UNSET
    timeout_at: datetime.datetime | None | Unset = UNSET
    next_step_rejected: ActivitySummary | None | Unset = UNSET
    approver_users: list[ApproverUserSummary] | Unset = UNSET
    approver_groups: list[ApproverGroupSummary] | Unset = UNSET
    decided_by: None | Unset | UserReference = UNSET
    decided_at: datetime.datetime | None | Unset = UNSET
    decision_notes: None | str | Unset = UNSET
    signal_delivery_error: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.activity_summary import ActivitySummary
        from ..models.user_reference import UserReference

        project_id = str(self.project_id)

        execution_id = str(self.execution_id)

        approval_node_id = self.approval_node_id

        name = self.name

        next_step_approved = self.next_step_approved.to_dict()

        workflow_context = self.workflow_context.to_dict()

        id: str | Unset = UNSET
        if not isinstance(self.id, Unset):
            id = str(self.id)

        created_at: str | Unset = UNSET
        if not isinstance(self.created_at, Unset):
            created_at = self.created_at.isoformat()

        updated_at: str | Unset = UNSET
        if not isinstance(self.updated_at, Unset):
            updated_at = self.updated_at.isoformat()

        labels: dict[str, Any] | Unset = UNSET
        if not isinstance(self.labels, Unset):
            labels = self.labels.to_dict()

        loop_iteration_path: list[int] | Unset = UNSET
        if not isinstance(self.loop_iteration_path, Unset):
            loop_iteration_path = self.loop_iteration_path

        prompt: None | str | Unset
        if isinstance(self.prompt, Unset):
            prompt = UNSET
        else:
            prompt = self.prompt

        status: str | Unset = UNSET
        if not isinstance(self.status, Unset):
            status = self.status.value

        timeout_at: None | str | Unset
        if isinstance(self.timeout_at, Unset):
            timeout_at = UNSET
        elif isinstance(self.timeout_at, datetime.datetime):
            timeout_at = self.timeout_at.isoformat()
        else:
            timeout_at = self.timeout_at

        next_step_rejected: dict[str, Any] | None | Unset
        if isinstance(self.next_step_rejected, Unset):
            next_step_rejected = UNSET
        elif isinstance(self.next_step_rejected, ActivitySummary):
            next_step_rejected = self.next_step_rejected.to_dict()
        else:
            next_step_rejected = self.next_step_rejected

        approver_users: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.approver_users, Unset):
            approver_users = []
            for approver_users_item_data in self.approver_users:
                approver_users_item = approver_users_item_data.to_dict()
                approver_users.append(approver_users_item)

        approver_groups: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.approver_groups, Unset):
            approver_groups = []
            for approver_groups_item_data in self.approver_groups:
                approver_groups_item = approver_groups_item_data.to_dict()
                approver_groups.append(approver_groups_item)

        decided_by: dict[str, Any] | None | Unset
        if isinstance(self.decided_by, Unset):
            decided_by = UNSET
        elif isinstance(self.decided_by, UserReference):
            decided_by = self.decided_by.to_dict()
        else:
            decided_by = self.decided_by

        decided_at: None | str | Unset
        if isinstance(self.decided_at, Unset):
            decided_at = UNSET
        elif isinstance(self.decided_at, datetime.datetime):
            decided_at = self.decided_at.isoformat()
        else:
            decided_at = self.decided_at

        decision_notes: None | str | Unset
        if isinstance(self.decision_notes, Unset):
            decision_notes = UNSET
        else:
            decision_notes = self.decision_notes

        signal_delivery_error: None | str | Unset
        if isinstance(self.signal_delivery_error, Unset):
            signal_delivery_error = UNSET
        else:
            signal_delivery_error = self.signal_delivery_error

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "project_id": project_id,
                "execution_id": execution_id,
                "approval_node_id": approval_node_id,
                "name": name,
                "next_step_approved": next_step_approved,
                "workflow_context": workflow_context,
            }
        )
        if id is not UNSET:
            field_dict["id"] = id
        if created_at is not UNSET:
            field_dict["created_at"] = created_at
        if updated_at is not UNSET:
            field_dict["updated_at"] = updated_at
        if labels is not UNSET:
            field_dict["labels"] = labels
        if loop_iteration_path is not UNSET:
            field_dict["loop_iteration_path"] = loop_iteration_path
        if prompt is not UNSET:
            field_dict["prompt"] = prompt
        if status is not UNSET:
            field_dict["status"] = status
        if timeout_at is not UNSET:
            field_dict["timeout_at"] = timeout_at
        if next_step_rejected is not UNSET:
            field_dict["next_step_rejected"] = next_step_rejected
        if approver_users is not UNSET:
            field_dict["approver_users"] = approver_users
        if approver_groups is not UNSET:
            field_dict["approver_groups"] = approver_groups
        if decided_by is not UNSET:
            field_dict["decided_by"] = decided_by
        if decided_at is not UNSET:
            field_dict["decided_at"] = decided_at
        if decision_notes is not UNSET:
            field_dict["decision_notes"] = decision_notes
        if signal_delivery_error is not UNSET:
            field_dict["signal_delivery_error"] = signal_delivery_error

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.activity_summary import ActivitySummary
        from ..models.approval_request_read_labels import ApprovalRequestReadLabels
        from ..models.approver_group_summary import ApproverGroupSummary
        from ..models.approver_user_summary import ApproverUserSummary
        from ..models.user_reference import UserReference
        from ..models.workflow_context import WorkflowContext

        d = dict(src_dict)
        project_id = UUID(d.pop("project_id"))

        execution_id = UUID(d.pop("execution_id"))

        approval_node_id = d.pop("approval_node_id")

        name = d.pop("name")

        next_step_approved = ActivitySummary.from_dict(d.pop("next_step_approved"))

        workflow_context = WorkflowContext.from_dict(d.pop("workflow_context"))

        _id = d.pop("id", UNSET)
        id: UUID | Unset
        if isinstance(_id, Unset):
            id = UNSET
        else:
            id = UUID(_id)

        _created_at = d.pop("created_at", UNSET)
        created_at: datetime.datetime | Unset
        if isinstance(_created_at, Unset):
            created_at = UNSET
        else:
            created_at = isoparse(_created_at)

        _updated_at = d.pop("updated_at", UNSET)
        updated_at: datetime.datetime | Unset
        if isinstance(_updated_at, Unset):
            updated_at = UNSET
        else:
            updated_at = isoparse(_updated_at)

        _labels = d.pop("labels", UNSET)
        labels: ApprovalRequestReadLabels | Unset
        if isinstance(_labels, Unset):
            labels = UNSET
        else:
            labels = ApprovalRequestReadLabels.from_dict(_labels)

        loop_iteration_path = cast(list[int], d.pop("loop_iteration_path", UNSET))

        def _parse_prompt(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        prompt = _parse_prompt(d.pop("prompt", UNSET))

        _status = d.pop("status", UNSET)
        status: ApprovalRequestStatus | Unset
        if isinstance(_status, Unset):
            status = UNSET
        else:
            status = ApprovalRequestStatus(_status)

        def _parse_timeout_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                timeout_at_type_0 = isoparse(data)

                return timeout_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        timeout_at = _parse_timeout_at(d.pop("timeout_at", UNSET))

        def _parse_next_step_rejected(data: object) -> ActivitySummary | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                next_step_rejected_type_0 = ActivitySummary.from_dict(data)

                return next_step_rejected_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ActivitySummary | None | Unset, data)

        next_step_rejected = _parse_next_step_rejected(d.pop("next_step_rejected", UNSET))

        _approver_users = d.pop("approver_users", UNSET)
        approver_users: list[ApproverUserSummary] | Unset = UNSET
        if _approver_users is not UNSET:
            approver_users = []
            for approver_users_item_data in _approver_users:
                approver_users_item = ApproverUserSummary.from_dict(approver_users_item_data)

                approver_users.append(approver_users_item)

        _approver_groups = d.pop("approver_groups", UNSET)
        approver_groups: list[ApproverGroupSummary] | Unset = UNSET
        if _approver_groups is not UNSET:
            approver_groups = []
            for approver_groups_item_data in _approver_groups:
                approver_groups_item = ApproverGroupSummary.from_dict(approver_groups_item_data)

                approver_groups.append(approver_groups_item)

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

        def _parse_decision_notes(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        decision_notes = _parse_decision_notes(d.pop("decision_notes", UNSET))

        def _parse_signal_delivery_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        signal_delivery_error = _parse_signal_delivery_error(d.pop("signal_delivery_error", UNSET))

        approval_request_read = cls(
            project_id=project_id,
            execution_id=execution_id,
            approval_node_id=approval_node_id,
            name=name,
            next_step_approved=next_step_approved,
            workflow_context=workflow_context,
            id=id,
            created_at=created_at,
            updated_at=updated_at,
            labels=labels,
            loop_iteration_path=loop_iteration_path,
            prompt=prompt,
            status=status,
            timeout_at=timeout_at,
            next_step_rejected=next_step_rejected,
            approver_users=approver_users,
            approver_groups=approver_groups,
            decided_by=decided_by,
            decided_at=decided_at,
            decision_notes=decision_notes,
            signal_delivery_error=signal_delivery_error,
        )

        return approval_request_read
