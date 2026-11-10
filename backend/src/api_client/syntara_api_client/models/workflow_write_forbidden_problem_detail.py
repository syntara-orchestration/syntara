from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.blocked_step_type import BlockedStepType


T = TypeVar("T", bound="WorkflowWriteForbiddenProblemDetail")


@_attrs_define
class WorkflowWriteForbiddenProblemDetail:
    """Standard forbidden response with optional step-type denial details.

    Attributes:
        type_ (str): URI reference identifying the problem type
        title (str): Short, human-readable summary of the problem
        detail (str): Human-readable explanation specific to this occurrence
        code (str): Machine-readable error code for programmatic handling
        retryable (bool): Whether this error can be retried by creating a new invocation
        instance (None | str | Unset): Optional URI reference identifying the specific occurrence
        blocked_step_types (list[BlockedStepType] | None | Unset):
    """

    type_: str
    title: str
    detail: str
    code: str
    retryable: bool
    instance: None | str | Unset = UNSET
    blocked_step_types: list[BlockedStepType] | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        title = self.title

        detail = self.detail

        code = self.code

        retryable = self.retryable

        instance: None | str | Unset
        if isinstance(self.instance, Unset):
            instance = UNSET
        else:
            instance = self.instance

        blocked_step_types: list[dict[str, Any]] | None | Unset
        if isinstance(self.blocked_step_types, Unset):
            blocked_step_types = UNSET
        elif isinstance(self.blocked_step_types, list):
            blocked_step_types = []
            for blocked_step_types_type_0_item_data in self.blocked_step_types:
                blocked_step_types_type_0_item = blocked_step_types_type_0_item_data.to_dict()
                blocked_step_types.append(blocked_step_types_type_0_item)

        else:
            blocked_step_types = self.blocked_step_types

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "type": type_,
                "title": title,
                "detail": detail,
                "code": code,
                "retryable": retryable,
            }
        )
        if instance is not UNSET:
            field_dict["instance"] = instance
        if blocked_step_types is not UNSET:
            field_dict["blocked_step_types"] = blocked_step_types

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.blocked_step_type import BlockedStepType

        d = dict(src_dict)
        type_ = d.pop("type")

        title = d.pop("title")

        detail = d.pop("detail")

        code = d.pop("code")

        retryable = d.pop("retryable")

        def _parse_instance(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        instance = _parse_instance(d.pop("instance", UNSET))

        def _parse_blocked_step_types(data: object) -> list[BlockedStepType] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                blocked_step_types_type_0 = []
                _blocked_step_types_type_0 = data
                for blocked_step_types_type_0_item_data in _blocked_step_types_type_0:
                    blocked_step_types_type_0_item = BlockedStepType.from_dict(blocked_step_types_type_0_item_data)

                    blocked_step_types_type_0.append(blocked_step_types_type_0_item)

                return blocked_step_types_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[BlockedStepType] | None | Unset, data)

        blocked_step_types = _parse_blocked_step_types(d.pop("blocked_step_types", UNSET))

        workflow_write_forbidden_problem_detail = cls(
            type_=type_,
            title=title,
            detail=detail,
            code=code,
            retryable=retryable,
            instance=instance,
            blocked_step_types=blocked_step_types,
        )

        workflow_write_forbidden_problem_detail.additional_properties = d
        return workflow_write_forbidden_problem_detail

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
