from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.workflow_read import WorkflowRead


T = TypeVar("T", bound="WorkflowUsedByResponse")


@_attrs_define
class WorkflowUsedByResponse:
    """Used-By response: the published parents that reference a given workflow.

    ``resources`` is the RBAC-filtered page of referencing parents the requester may view, paged by ``next``/``prev``.
    ``referencing_parent_count`` is a domain value -- not a pagination total -- giving the number of distinct published
    parents across all projects, counted regardless of the requester's visibility, so the Used-By badge reflects true
    impact even when some parents sit in projects the caller cannot see. The page envelope's ``total``/``include_total``
    are deliberately omitted here.

        Attributes:
            resources (list[WorkflowRead]): Page of referencing published parents the caller may view.
            referencing_parent_count (int): Distinct published parent workflows that reference this workflow, counted across
                all projects regardless of the requester's visibility. A domain value, not a pagination total.
            next_ (None | str | Unset): Cursor for the next page of referencing parents.
            prev (None | str | Unset): Cursor for the previous page of referencing parents.
    """

    resources: list[WorkflowRead]
    referencing_parent_count: int
    next_: None | str | Unset = UNSET
    prev: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        resources = []
        for resources_item_data in self.resources:
            resources_item = resources_item_data.to_dict()
            resources.append(resources_item)

        referencing_parent_count = self.referencing_parent_count

        next_: None | str | Unset
        if isinstance(self.next_, Unset):
            next_ = UNSET
        else:
            next_ = self.next_

        prev: None | str | Unset
        if isinstance(self.prev, Unset):
            prev = UNSET
        else:
            prev = self.prev

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "resources": resources,
                "referencing_parent_count": referencing_parent_count,
            }
        )
        if next_ is not UNSET:
            field_dict["next"] = next_
        if prev is not UNSET:
            field_dict["prev"] = prev

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.workflow_read import WorkflowRead

        d = dict(src_dict)
        resources = []
        _resources = d.pop("resources")
        for resources_item_data in _resources:
            resources_item = WorkflowRead.from_dict(resources_item_data)

            resources.append(resources_item)

        referencing_parent_count = d.pop("referencing_parent_count")

        def _parse_next_(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        next_ = _parse_next_(d.pop("next", UNSET))

        def _parse_prev(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        prev = _parse_prev(d.pop("prev", UNSET))

        workflow_used_by_response = cls(
            resources=resources,
            referencing_parent_count=referencing_parent_count,
            next_=next_,
            prev=prev,
        )

        workflow_used_by_response.additional_properties = d
        return workflow_used_by_response

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
