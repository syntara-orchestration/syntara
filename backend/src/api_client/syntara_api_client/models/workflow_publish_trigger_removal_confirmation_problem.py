from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.workflow_publish_trigger_removal_confirmation_problem_code import (
    WorkflowPublishTriggerRemovalConfirmationProblemCode,
)
from ..types import UNSET, Unset

T = TypeVar("T", bound="WorkflowPublishTriggerRemovalConfirmationProblem")


@_attrs_define
class WorkflowPublishTriggerRemovalConfirmationProblem:
    """RFC 9457 problem body returned (HTTP 409) when publishing a version that removes a Subworkflow Trigger invoked by
    published parents without ``confirm=true``. Extends ``ErrorData`` with the count of affected parents; their
    identities are never disclosed.

        Attributes:
            type_ (str): URI reference identifying the problem type
            title (str): Short, human-readable summary of the problem
            detail (str): Human-readable explanation specific to this occurrence
            code (WorkflowPublishTriggerRemovalConfirmationProblemCode): Machine-readable error code; fixed for this problem
                type.
            retryable (bool): Whether this error can be retried by creating a new invocation
            affected_count (int): Distinct published parent workflows that invoke a Subworkflow Trigger removed by this
                publish.
            instance (None | str | Unset): Optional URI reference identifying the specific occurrence
    """

    type_: str
    title: str
    detail: str
    code: WorkflowPublishTriggerRemovalConfirmationProblemCode
    retryable: bool
    affected_count: int
    instance: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        title = self.title

        detail = self.detail

        code = self.code.value

        retryable = self.retryable

        affected_count = self.affected_count

        instance: None | str | Unset
        if isinstance(self.instance, Unset):
            instance = UNSET
        else:
            instance = self.instance

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "type": type_,
                "title": title,
                "detail": detail,
                "code": code,
                "retryable": retryable,
                "affected_count": affected_count,
            }
        )
        if instance is not UNSET:
            field_dict["instance"] = instance

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        type_ = d.pop("type")

        title = d.pop("title")

        detail = d.pop("detail")

        code = WorkflowPublishTriggerRemovalConfirmationProblemCode(d.pop("code"))

        retryable = d.pop("retryable")

        affected_count = d.pop("affected_count")

        def _parse_instance(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        instance = _parse_instance(d.pop("instance", UNSET))

        workflow_publish_trigger_removal_confirmation_problem = cls(
            type_=type_,
            title=title,
            detail=detail,
            code=code,
            retryable=retryable,
            affected_count=affected_count,
            instance=instance,
        )

        workflow_publish_trigger_removal_confirmation_problem.additional_properties = d
        return workflow_publish_trigger_removal_confirmation_problem

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
