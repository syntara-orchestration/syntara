from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.workflow_read import WorkflowRead


T = TypeVar("T", bound="WorkflowListResponse")


@_attrs_define
class WorkflowListResponse:
    """Paginated list response for workflows.

    Attributes:
        resources (list[WorkflowRead]): Array of resources in current page
        next_ (None | str | Unset): Cursor for next page of results
        prev (None | str | Unset): Cursor for previous page of results
        total (int | None | Unset): Total count of resources (only when include_total=true)
    """

    resources: list[WorkflowRead]
    next_: None | str | Unset = UNSET
    prev: None | str | Unset = UNSET
    total: int | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        resources = []
        for resources_item_data in self.resources:
            resources_item = resources_item_data.to_dict()
            resources.append(resources_item)

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

        total: int | None | Unset
        if isinstance(self.total, Unset):
            total = UNSET
        else:
            total = self.total

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "resources": resources,
            }
        )
        if next_ is not UNSET:
            field_dict["next"] = next_
        if prev is not UNSET:
            field_dict["prev"] = prev
        if total is not UNSET:
            field_dict["total"] = total

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

        def _parse_total(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        total = _parse_total(d.pop("total", UNSET))

        workflow_list_response = cls(
            resources=resources,
            next_=next_,
            prev=prev,
            total=total,
        )

        return workflow_list_response
