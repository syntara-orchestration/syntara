from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="WorkflowReferencedConfirmationProblem")


@_attrs_define
class WorkflowReferencedConfirmationProblem:
    """Typed RFC 9457 problem body for the delete-confirmation 409.

    Extends the base problem with the count of referencing published parents; their identities are
    never disclosed, since the caller may lack read access to them. Mirrors
    ``WorkflowReferencedConfirmationProblem`` in the OpenAPI spec so generated clients type the field.

        Attributes:
            code (Literal['WORKFLOW_REFERENCED_CONFIRMATION_REQUIRED']): Machine-readable error code; fixed for this problem
                type.
            detail (str): Human-readable explanation specific to this occurrence
            referencing_count (int): Distinct published parents that reference this workflow and would be affected by
                deletion.
            retryable (bool): Whether this error can be retried by creating a new invocation
            title (str): Short, human-readable summary of the problem
            type_ (str): URI reference identifying the problem type
            instance (None | str | Unset): Optional URI reference identifying the specific occurrence
    """

    code: Literal["WORKFLOW_REFERENCED_CONFIRMATION_REQUIRED"]
    detail: str
    referencing_count: int
    retryable: bool
    title: str
    type_: str
    instance: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        code = self.code

        detail = self.detail

        referencing_count = self.referencing_count

        retryable = self.retryable

        title = self.title

        type_ = self.type_

        instance: None | str | Unset
        if isinstance(self.instance, Unset):
            instance = UNSET
        else:
            instance = self.instance

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "code": code,
                "detail": detail,
                "referencing_count": referencing_count,
                "retryable": retryable,
                "title": title,
                "type": type_,
            }
        )
        if instance is not UNSET:
            field_dict["instance"] = instance

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        code = cast(Literal["WORKFLOW_REFERENCED_CONFIRMATION_REQUIRED"], d.pop("code"))
        if code != "WORKFLOW_REFERENCED_CONFIRMATION_REQUIRED":
            raise ValueError(f"code must match const 'WORKFLOW_REFERENCED_CONFIRMATION_REQUIRED', got '{code}'")

        detail = d.pop("detail")

        referencing_count = d.pop("referencing_count")

        retryable = d.pop("retryable")

        title = d.pop("title")

        type_ = d.pop("type")

        def _parse_instance(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        instance = _parse_instance(d.pop("instance", UNSET))

        workflow_referenced_confirmation_problem = cls(
            code=code,
            detail=detail,
            referencing_count=referencing_count,
            retryable=retryable,
            title=title,
            type_=type_,
            instance=instance,
        )

        workflow_referenced_confirmation_problem.additional_properties = d
        return workflow_referenced_confirmation_problem

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
