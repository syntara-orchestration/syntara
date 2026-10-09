from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.who_can_request_resource_labels import WhoCanRequestResourceLabels
    from ..models.who_can_request_resource_metadata import WhoCanRequestResourceMetadata


T = TypeVar("T", bound="WhoCanRequest")


@_attrs_define
class WhoCanRequest:
    """Request body for the Who can? endpoint.

    Attributes:
        action (str):
        resource_type (str):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        resource_id (str | Unset):  Default: ''.
        resource_labels (WhoCanRequestResourceLabels | Unset):
        resource_metadata (WhoCanRequestResourceMetadata | Unset):
        resource_project (str | Unset): Project scope of the resource (project name or UUID) Default: ''.
    """

    action: str
    resource_type: str
    limit: int | Unset = 20
    cursor: None | str | Unset = UNSET
    sort: None | str | Unset = UNSET
    include_total: bool | Unset = False
    resource_id: str | Unset = ""
    resource_labels: WhoCanRequestResourceLabels | Unset = UNSET
    resource_metadata: WhoCanRequestResourceMetadata | Unset = UNSET
    resource_project: str | Unset = ""

    def to_dict(self) -> dict[str, Any]:
        action = self.action

        resource_type = self.resource_type

        limit = self.limit

        cursor: None | str | Unset
        if isinstance(self.cursor, Unset):
            cursor = UNSET
        else:
            cursor = self.cursor

        sort: None | str | Unset
        if isinstance(self.sort, Unset):
            sort = UNSET
        else:
            sort = self.sort

        include_total = self.include_total

        resource_id = self.resource_id

        resource_labels: dict[str, Any] | Unset = UNSET
        if not isinstance(self.resource_labels, Unset):
            resource_labels = self.resource_labels.to_dict()

        resource_metadata: dict[str, Any] | Unset = UNSET
        if not isinstance(self.resource_metadata, Unset):
            resource_metadata = self.resource_metadata.to_dict()

        resource_project = self.resource_project

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "action": action,
                "resource_type": resource_type,
            }
        )
        if limit is not UNSET:
            field_dict["limit"] = limit
        if cursor is not UNSET:
            field_dict["cursor"] = cursor
        if sort is not UNSET:
            field_dict["sort"] = sort
        if include_total is not UNSET:
            field_dict["include_total"] = include_total
        if resource_id is not UNSET:
            field_dict["resource_id"] = resource_id
        if resource_labels is not UNSET:
            field_dict["resource_labels"] = resource_labels
        if resource_metadata is not UNSET:
            field_dict["resource_metadata"] = resource_metadata
        if resource_project is not UNSET:
            field_dict["resource_project"] = resource_project

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.who_can_request_resource_labels import WhoCanRequestResourceLabels
        from ..models.who_can_request_resource_metadata import WhoCanRequestResourceMetadata

        d = dict(src_dict)
        action = d.pop("action")

        resource_type = d.pop("resource_type")

        limit = d.pop("limit", UNSET)

        def _parse_cursor(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cursor = _parse_cursor(d.pop("cursor", UNSET))

        def _parse_sort(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        sort = _parse_sort(d.pop("sort", UNSET))

        include_total = d.pop("include_total", UNSET)

        resource_id = d.pop("resource_id", UNSET)

        _resource_labels = d.pop("resource_labels", UNSET)
        resource_labels: WhoCanRequestResourceLabels | Unset
        if isinstance(_resource_labels, Unset):
            resource_labels = UNSET
        else:
            resource_labels = WhoCanRequestResourceLabels.from_dict(_resource_labels)

        _resource_metadata = d.pop("resource_metadata", UNSET)
        resource_metadata: WhoCanRequestResourceMetadata | Unset
        if isinstance(_resource_metadata, Unset):
            resource_metadata = UNSET
        else:
            resource_metadata = WhoCanRequestResourceMetadata.from_dict(_resource_metadata)

        resource_project = d.pop("resource_project", UNSET)

        who_can_request = cls(
            action=action,
            resource_type=resource_type,
            limit=limit,
            cursor=cursor,
            sort=sort,
            include_total=include_total,
            resource_id=resource_id,
            resource_labels=resource_labels,
            resource_metadata=resource_metadata,
            resource_project=resource_project,
        )

        return who_can_request
