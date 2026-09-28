from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from dateutil.parser import isoparse

from ..models.tool_status import ToolStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.tool_parameter import ToolParameter
    from ..models.tool_with_parameters_labels import ToolWithParametersLabels
    from ..models.user_reference import UserReference


T = TypeVar("T", bound="ToolWithParameters")


@_attrs_define
class ToolWithParameters:
    """Schema for Tool response with ToolParameter details.

    Attributes:
        name (str): Human-readable name for the resource Example: Authentication Service.
        integration_id (UUID): UUID of the owning Integration (mcp_server)
        namespaced_name (str): Unique namespaced name for the tool
        parameters (list[ToolParameter]): Tool parameters
        id (UUID | Unset): Unique identifier for the resource Example: 550e8400-e29b-41d4-a716-446655440000.
        created_at (datetime.datetime | Unset): Timestamp when resource was created Example: 2025-10-09T12:00:00Z.
        updated_at (datetime.datetime | Unset): Timestamp when resource was last updated Example: 2025-10-09T12:30:00Z.
        labels (ToolWithParametersLabels | Unset): Key-value pairs for resource labeling and filtering Example:
            {'environment': 'production', 'region': 'us-east-1', 'team': 'platform'}.
        description (None | str | Unset): Detailed description of the resource Example: Handles user authentication and
            authorization workflows.
        created_by (None | Unset | UserReference): User who created the tool
        updated_by (None | Unset | UserReference): User who last modified the tool
        enabled (bool | Unset): Whether the tool is enabled Default: True.
        status (ToolStatus | Unset): Status of a tool.
        last_executed_at (datetime.datetime | None | Unset): Timestamp of last execution
        last_refreshed_at (datetime.datetime | None | Unset): Timestamp of last refresh from provider
        refresh_error (None | str | Unset): Error message from last refresh attempt
    """

    name: str
    integration_id: UUID
    namespaced_name: str
    parameters: list[ToolParameter]
    id: UUID | Unset = UNSET
    created_at: datetime.datetime | Unset = UNSET
    updated_at: datetime.datetime | Unset = UNSET
    labels: ToolWithParametersLabels | Unset = UNSET
    description: None | str | Unset = UNSET
    created_by: None | Unset | UserReference = UNSET
    updated_by: None | Unset | UserReference = UNSET
    enabled: bool | Unset = True
    status: ToolStatus | Unset = UNSET
    last_executed_at: datetime.datetime | None | Unset = UNSET
    last_refreshed_at: datetime.datetime | None | Unset = UNSET
    refresh_error: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.user_reference import UserReference

        name = self.name

        integration_id = str(self.integration_id)

        namespaced_name = self.namespaced_name

        parameters = []
        for parameters_item_data in self.parameters:
            parameters_item = parameters_item_data.to_dict()
            parameters.append(parameters_item)

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

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        created_by: dict[str, Any] | None | Unset
        if isinstance(self.created_by, Unset):
            created_by = UNSET
        elif isinstance(self.created_by, UserReference):
            created_by = self.created_by.to_dict()
        else:
            created_by = self.created_by

        updated_by: dict[str, Any] | None | Unset
        if isinstance(self.updated_by, Unset):
            updated_by = UNSET
        elif isinstance(self.updated_by, UserReference):
            updated_by = self.updated_by.to_dict()
        else:
            updated_by = self.updated_by

        enabled = self.enabled

        status: str | Unset = UNSET
        if not isinstance(self.status, Unset):
            status = self.status.value

        last_executed_at: None | str | Unset
        if isinstance(self.last_executed_at, Unset):
            last_executed_at = UNSET
        elif isinstance(self.last_executed_at, datetime.datetime):
            last_executed_at = self.last_executed_at.isoformat()
        else:
            last_executed_at = self.last_executed_at

        last_refreshed_at: None | str | Unset
        if isinstance(self.last_refreshed_at, Unset):
            last_refreshed_at = UNSET
        elif isinstance(self.last_refreshed_at, datetime.datetime):
            last_refreshed_at = self.last_refreshed_at.isoformat()
        else:
            last_refreshed_at = self.last_refreshed_at

        refresh_error: None | str | Unset
        if isinstance(self.refresh_error, Unset):
            refresh_error = UNSET
        else:
            refresh_error = self.refresh_error

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "name": name,
                "integration_id": integration_id,
                "namespaced_name": namespaced_name,
                "parameters": parameters,
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
        if description is not UNSET:
            field_dict["description"] = description
        if created_by is not UNSET:
            field_dict["created_by"] = created_by
        if updated_by is not UNSET:
            field_dict["updated_by"] = updated_by
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if status is not UNSET:
            field_dict["status"] = status
        if last_executed_at is not UNSET:
            field_dict["last_executed_at"] = last_executed_at
        if last_refreshed_at is not UNSET:
            field_dict["last_refreshed_at"] = last_refreshed_at
        if refresh_error is not UNSET:
            field_dict["refresh_error"] = refresh_error

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.tool_parameter import ToolParameter
        from ..models.tool_with_parameters_labels import ToolWithParametersLabels
        from ..models.user_reference import UserReference

        d = dict(src_dict)
        name = d.pop("name")

        integration_id = UUID(d.pop("integration_id"))

        namespaced_name = d.pop("namespaced_name")

        parameters = []
        _parameters = d.pop("parameters")
        for parameters_item_data in _parameters:
            parameters_item = ToolParameter.from_dict(parameters_item_data)

            parameters.append(parameters_item)

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
        labels: ToolWithParametersLabels | Unset
        if isinstance(_labels, Unset):
            labels = UNSET
        else:
            labels = ToolWithParametersLabels.from_dict(_labels)

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        def _parse_created_by(data: object) -> None | Unset | UserReference:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                created_by_type_0 = UserReference.from_dict(data)

                return created_by_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UserReference, data)

        created_by = _parse_created_by(d.pop("created_by", UNSET))

        def _parse_updated_by(data: object) -> None | Unset | UserReference:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                updated_by_type_0 = UserReference.from_dict(data)

                return updated_by_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UserReference, data)

        updated_by = _parse_updated_by(d.pop("updated_by", UNSET))

        enabled = d.pop("enabled", UNSET)

        _status = d.pop("status", UNSET)
        status: ToolStatus | Unset
        if isinstance(_status, Unset):
            status = UNSET
        else:
            status = ToolStatus(_status)

        def _parse_last_executed_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_executed_at_type_0 = isoparse(data)

                return last_executed_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        last_executed_at = _parse_last_executed_at(d.pop("last_executed_at", UNSET))

        def _parse_last_refreshed_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_refreshed_at_type_0 = isoparse(data)

                return last_refreshed_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        last_refreshed_at = _parse_last_refreshed_at(d.pop("last_refreshed_at", UNSET))

        def _parse_refresh_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        refresh_error = _parse_refresh_error(d.pop("refresh_error", UNSET))

        tool_with_parameters = cls(
            name=name,
            integration_id=integration_id,
            namespaced_name=namespaced_name,
            parameters=parameters,
            id=id,
            created_at=created_at,
            updated_at=updated_at,
            labels=labels,
            description=description,
            created_by=created_by,
            updated_by=updated_by,
            enabled=enabled,
            status=status,
            last_executed_at=last_executed_at,
            last_refreshed_at=last_refreshed_at,
            refresh_error=refresh_error,
        )

        return tool_with_parameters
