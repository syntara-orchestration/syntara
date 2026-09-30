from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.workflow_launch_rejected_problem_reason import WorkflowLaunchRejectedProblemReason
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.workflow_launch_rejected_step import WorkflowLaunchRejectedStep


T = TypeVar("T", bound="WorkflowLaunchRejectedProblem")


@_attrs_define
class WorkflowLaunchRejectedProblem:
    """RFC 9457 response returned when launch authorization rejects a workflow.

    Attributes:
        code (Literal['WORKFLOW_LAUNCH_REJECTED']):
        denied_steps (list[WorkflowLaunchRejectedStep]):
        detail (str):
        instance (str):
        principal_id (UUID):
        project_id (UUID):
        reason (WorkflowLaunchRejectedProblemReason):
        retryable (bool):
        title (str):
        trigger_type (None | str):
        type_ (str):
        denied_by (None | str | Unset):
        execution_id (None | Unset | UUID):
    """

    code: Literal["WORKFLOW_LAUNCH_REJECTED"]
    denied_steps: list[WorkflowLaunchRejectedStep]
    detail: str
    instance: str
    principal_id: UUID
    project_id: UUID
    reason: WorkflowLaunchRejectedProblemReason
    retryable: bool
    title: str
    trigger_type: None | str
    type_: str
    denied_by: None | str | Unset = UNSET
    execution_id: None | Unset | UUID = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        code = self.code

        denied_steps = []
        for denied_steps_item_data in self.denied_steps:
            denied_steps_item = denied_steps_item_data.to_dict()
            denied_steps.append(denied_steps_item)

        detail = self.detail

        instance = self.instance

        principal_id = str(self.principal_id)

        project_id = str(self.project_id)

        reason = self.reason.value

        retryable = self.retryable

        title = self.title

        trigger_type: None | str
        trigger_type = self.trigger_type

        type_ = self.type_

        denied_by: None | str | Unset
        if isinstance(self.denied_by, Unset):
            denied_by = UNSET
        else:
            denied_by = self.denied_by

        execution_id: None | str | Unset
        if isinstance(self.execution_id, Unset):
            execution_id = UNSET
        elif isinstance(self.execution_id, UUID):
            execution_id = str(self.execution_id)
        else:
            execution_id = self.execution_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "code": code,
                "denied_steps": denied_steps,
                "detail": detail,
                "instance": instance,
                "principal_id": principal_id,
                "project_id": project_id,
                "reason": reason,
                "retryable": retryable,
                "title": title,
                "trigger_type": trigger_type,
                "type": type_,
            }
        )
        if denied_by is not UNSET:
            field_dict["denied_by"] = denied_by
        if execution_id is not UNSET:
            field_dict["execution_id"] = execution_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.workflow_launch_rejected_step import WorkflowLaunchRejectedStep

        d = dict(src_dict)
        code = cast(Literal["WORKFLOW_LAUNCH_REJECTED"], d.pop("code"))
        if code != "WORKFLOW_LAUNCH_REJECTED":
            raise ValueError(f"code must match const 'WORKFLOW_LAUNCH_REJECTED', got '{code}'")

        denied_steps = []
        _denied_steps = d.pop("denied_steps")
        for denied_steps_item_data in _denied_steps:
            denied_steps_item = WorkflowLaunchRejectedStep.from_dict(denied_steps_item_data)

            denied_steps.append(denied_steps_item)

        detail = d.pop("detail")

        instance = d.pop("instance")

        principal_id = UUID(d.pop("principal_id"))

        project_id = UUID(d.pop("project_id"))

        reason = WorkflowLaunchRejectedProblemReason(d.pop("reason"))

        retryable = d.pop("retryable")

        title = d.pop("title")

        def _parse_trigger_type(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        trigger_type = _parse_trigger_type(d.pop("trigger_type"))

        type_ = d.pop("type")

        def _parse_denied_by(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        denied_by = _parse_denied_by(d.pop("denied_by", UNSET))

        def _parse_execution_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                execution_id_type_0 = UUID(data)

                return execution_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        execution_id = _parse_execution_id(d.pop("execution_id", UNSET))

        workflow_launch_rejected_problem = cls(
            code=code,
            denied_steps=denied_steps,
            detail=detail,
            instance=instance,
            principal_id=principal_id,
            project_id=project_id,
            reason=reason,
            retryable=retryable,
            title=title,
            trigger_type=trigger_type,
            type_=type_,
            denied_by=denied_by,
            execution_id=execution_id,
        )

        workflow_launch_rejected_problem.additional_properties = d
        return workflow_launch_rejected_problem

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
