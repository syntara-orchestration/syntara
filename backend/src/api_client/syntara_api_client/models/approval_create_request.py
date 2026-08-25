from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.activity_summary import ActivitySummary
    from ..models.workflow_context import WorkflowContext


T = TypeVar("T", bound="ApprovalCreateRequest")


@_attrs_define
class ApprovalCreateRequest:
    """Request payload for creating an approval request.

    This is an internal schema used by the Workflows component.

        Attributes:
            execution_id (UUID): Parent workflow execution ID
            project_id (UUID): Project ID (denormalized from execution)
            approval_node_id (str): Canvas node ID from the workflow definition
            name (str): Display name for the approval request
            next_step_approved (ActivitySummary): Activity summary for workflow context.

                Passed through from the workflow engine as-is. Contains at minimum
                ``id``, ``name``, ``type``, and usually ``config`` with the full
                activity parameters so approvers can see what the step will do.
            workflow_context (WorkflowContext): Workflow Context for approvers.

                Essential context for approvers to make a decision.
                Contains workflow identification, inputs, and the output from the immediately
                preceding activity.
            loop_iteration_path (list[int] | Unset): Enclosing-loop indices, outermost first (empty when not inside a loop)
            temporal_activity_id (None | str | Unset): Temporal activity ID to signal on decide (defaults to
                approval_node_id)
            timeout_at (datetime.datetime | None | Unset): When this request expires (null = no timeout)
            next_step_rejected (ActivitySummary | None | Unset): First activity that executes if rejected
            approver_user_ids (list[UUID] | None | Unset): User IDs who can approve (null = any user with approval:decide
                permission)
            approver_group_ids (list[UUID] | None | Unset): Group IDs whose members can approve
    """

    execution_id: UUID
    project_id: UUID
    approval_node_id: str
    name: str
    next_step_approved: ActivitySummary
    workflow_context: WorkflowContext
    loop_iteration_path: list[int] | Unset = UNSET
    temporal_activity_id: None | str | Unset = UNSET
    timeout_at: datetime.datetime | None | Unset = UNSET
    next_step_rejected: ActivitySummary | None | Unset = UNSET
    approver_user_ids: list[UUID] | None | Unset = UNSET
    approver_group_ids: list[UUID] | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.activity_summary import ActivitySummary

        execution_id = str(self.execution_id)

        project_id = str(self.project_id)

        approval_node_id = self.approval_node_id

        name = self.name

        next_step_approved = self.next_step_approved.to_dict()

        workflow_context = self.workflow_context.to_dict()

        loop_iteration_path: list[int] | Unset = UNSET
        if not isinstance(self.loop_iteration_path, Unset):
            loop_iteration_path = self.loop_iteration_path

        temporal_activity_id: None | str | Unset
        if isinstance(self.temporal_activity_id, Unset):
            temporal_activity_id = UNSET
        else:
            temporal_activity_id = self.temporal_activity_id

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

        approver_user_ids: list[str] | None | Unset
        if isinstance(self.approver_user_ids, Unset):
            approver_user_ids = UNSET
        elif isinstance(self.approver_user_ids, list):
            approver_user_ids = []
            for approver_user_ids_type_0_item_data in self.approver_user_ids:
                approver_user_ids_type_0_item = str(approver_user_ids_type_0_item_data)
                approver_user_ids.append(approver_user_ids_type_0_item)

        else:
            approver_user_ids = self.approver_user_ids

        approver_group_ids: list[str] | None | Unset
        if isinstance(self.approver_group_ids, Unset):
            approver_group_ids = UNSET
        elif isinstance(self.approver_group_ids, list):
            approver_group_ids = []
            for approver_group_ids_type_0_item_data in self.approver_group_ids:
                approver_group_ids_type_0_item = str(approver_group_ids_type_0_item_data)
                approver_group_ids.append(approver_group_ids_type_0_item)

        else:
            approver_group_ids = self.approver_group_ids

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "execution_id": execution_id,
                "project_id": project_id,
                "approval_node_id": approval_node_id,
                "name": name,
                "next_step_approved": next_step_approved,
                "workflow_context": workflow_context,
            }
        )
        if loop_iteration_path is not UNSET:
            field_dict["loop_iteration_path"] = loop_iteration_path
        if temporal_activity_id is not UNSET:
            field_dict["temporal_activity_id"] = temporal_activity_id
        if timeout_at is not UNSET:
            field_dict["timeout_at"] = timeout_at
        if next_step_rejected is not UNSET:
            field_dict["next_step_rejected"] = next_step_rejected
        if approver_user_ids is not UNSET:
            field_dict["approver_user_ids"] = approver_user_ids
        if approver_group_ids is not UNSET:
            field_dict["approver_group_ids"] = approver_group_ids

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.activity_summary import ActivitySummary
        from ..models.workflow_context import WorkflowContext

        d = dict(src_dict)
        execution_id = UUID(d.pop("execution_id"))

        project_id = UUID(d.pop("project_id"))

        approval_node_id = d.pop("approval_node_id")

        name = d.pop("name")

        next_step_approved = ActivitySummary.from_dict(d.pop("next_step_approved"))

        workflow_context = WorkflowContext.from_dict(d.pop("workflow_context"))

        loop_iteration_path = cast(list[int], d.pop("loop_iteration_path", UNSET))

        def _parse_temporal_activity_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        temporal_activity_id = _parse_temporal_activity_id(d.pop("temporal_activity_id", UNSET))

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

        def _parse_approver_user_ids(data: object) -> list[UUID] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                approver_user_ids_type_0 = []
                _approver_user_ids_type_0 = data
                for approver_user_ids_type_0_item_data in _approver_user_ids_type_0:
                    approver_user_ids_type_0_item = UUID(approver_user_ids_type_0_item_data)

                    approver_user_ids_type_0.append(approver_user_ids_type_0_item)

                return approver_user_ids_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[UUID] | None | Unset, data)

        approver_user_ids = _parse_approver_user_ids(d.pop("approver_user_ids", UNSET))

        def _parse_approver_group_ids(data: object) -> list[UUID] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                approver_group_ids_type_0 = []
                _approver_group_ids_type_0 = data
                for approver_group_ids_type_0_item_data in _approver_group_ids_type_0:
                    approver_group_ids_type_0_item = UUID(approver_group_ids_type_0_item_data)

                    approver_group_ids_type_0.append(approver_group_ids_type_0_item)

                return approver_group_ids_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[UUID] | None | Unset, data)

        approver_group_ids = _parse_approver_group_ids(d.pop("approver_group_ids", UNSET))

        approval_create_request = cls(
            execution_id=execution_id,
            project_id=project_id,
            approval_node_id=approval_node_id,
            name=name,
            next_step_approved=next_step_approved,
            workflow_context=workflow_context,
            loop_iteration_path=loop_iteration_path,
            temporal_activity_id=temporal_activity_id,
            timeout_at=timeout_at,
            next_step_rejected=next_step_rejected,
            approver_user_ids=approver_user_ids,
            approver_group_ids=approver_group_ids,
        )

        approval_create_request.additional_properties = d
        return approval_create_request

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
