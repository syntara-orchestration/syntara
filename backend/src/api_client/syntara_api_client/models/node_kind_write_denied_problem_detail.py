from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.blocked_step_type import BlockedStepType


T = TypeVar("T", bound="NodeKindWriteDeniedProblemDetail")


@_attrs_define
class NodeKindWriteDeniedProblemDetail:
    """RFC 9457 permission denial with blocked step types.

    Attributes:
        type_ (str): URI reference identifying the problem type
        title (str): Short, human-readable summary of the problem
        detail (str): Human-readable explanation specific to this occurrence
        blocked_step_types (list[BlockedStepType]):
        code (Literal['NODE_KIND_WRITE_DENIED'] | Unset):  Default: 'NODE_KIND_WRITE_DENIED'.
        retryable (bool | Unset):  Default: False.
        instance (None | str | Unset): Optional URI reference identifying the specific occurrence
        status (int | Unset):  Default: 403.
    """

    type_: str
    title: str
    detail: str
    blocked_step_types: list[BlockedStepType]
    code: Literal["NODE_KIND_WRITE_DENIED"] | Unset = "NODE_KIND_WRITE_DENIED"
    retryable: bool | Unset = False
    instance: None | str | Unset = UNSET
    status: int | Unset = 403
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        title = self.title

        detail = self.detail

        blocked_step_types = []
        for blocked_step_types_item_data in self.blocked_step_types:
            blocked_step_types_item = blocked_step_types_item_data.to_dict()
            blocked_step_types.append(blocked_step_types_item)

        code = self.code

        retryable = self.retryable

        instance: None | str | Unset
        if isinstance(self.instance, Unset):
            instance = UNSET
        else:
            instance = self.instance

        status = self.status

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "type": type_,
                "title": title,
                "detail": detail,
                "blocked_step_types": blocked_step_types,
            }
        )
        if code is not UNSET:
            field_dict["code"] = code
        if retryable is not UNSET:
            field_dict["retryable"] = retryable
        if instance is not UNSET:
            field_dict["instance"] = instance
        if status is not UNSET:
            field_dict["status"] = status

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.blocked_step_type import BlockedStepType

        d = dict(src_dict)
        type_ = d.pop("type")

        title = d.pop("title")

        detail = d.pop("detail")

        blocked_step_types = []
        _blocked_step_types = d.pop("blocked_step_types")
        for blocked_step_types_item_data in _blocked_step_types:
            blocked_step_types_item = BlockedStepType.from_dict(blocked_step_types_item_data)

            blocked_step_types.append(blocked_step_types_item)

        code = cast(Literal["NODE_KIND_WRITE_DENIED"] | Unset, d.pop("code", UNSET))
        if code != "NODE_KIND_WRITE_DENIED" and not isinstance(code, Unset):
            raise ValueError(f"code must match const 'NODE_KIND_WRITE_DENIED', got '{code}'")

        retryable = d.pop("retryable", UNSET)

        def _parse_instance(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        instance = _parse_instance(d.pop("instance", UNSET))

        status = d.pop("status", UNSET)

        node_kind_write_denied_problem_detail = cls(
            type_=type_,
            title=title,
            detail=detail,
            blocked_step_types=blocked_step_types,
            code=code,
            retryable=retryable,
            instance=instance,
            status=status,
        )

        node_kind_write_denied_problem_detail.additional_properties = d
        return node_kind_write_denied_problem_detail

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
