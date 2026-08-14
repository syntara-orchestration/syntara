from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from dateutil.parser import isoparse

from ..models.tool_execution_status import ToolExecutionStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.tool_execution_input_parameters import ToolExecutionInputParameters
    from ..models.tool_execution_labels import ToolExecutionLabels
    from ..models.tool_execution_output_data_type_0 import ToolExecutionOutputDataType0


T = TypeVar("T", bound="ToolExecution")


@_attrs_define
class ToolExecution:
    """Tool execution records stored in database.

    Records individual Tool executions for performance monitoring and analysis.
    This model matches the ToolExecution schema from the metrics contract.

    Inherits from UserOwnedResource:
        id: UUID primary key
        created_at: Creation timestamp
        updated_at: Last update timestamp
        created_by: UUID of user who created the resource
        updated_by: Optional UUID of user who last updated the resource
        labels: Optional key-value metadata

        Attributes:
            created_by (UUID): User (or automation) that created the resource Example: 770e8400-e29b-41d4-a716-446655440000.
            user_id (UUID): Identifier of executing user/agent
            execution_start (datetime.datetime): Execution start timestamp
            status (ToolExecutionStatus): Status of a tool execution.
            input_parameters (ToolExecutionInputParameters): Tool input parameters
            id (UUID | Unset): Unique identifier for the resource Example: 550e8400-e29b-41d4-a716-446655440000.
            created_at (datetime.datetime | Unset): Timestamp when resource was created Example: 2025-10-09T12:00:00Z.
            updated_at (datetime.datetime | Unset): Timestamp when resource was last updated Example: 2025-10-09T12:30:00Z.
            labels (ToolExecutionLabels | Unset): Key-value pairs for resource labeling and filtering Example:
                {'environment': 'production', 'region': 'us-east-1', 'team': 'platform'}.
            updated_by (None | Unset | UUID): User (or automation) that last updated the resource Example:
                880e8400-e29b-41d4-a716-446655440000.
            tool_id (None | Unset | UUID): Foreign key to Tool
            integration_id (None | Unset | UUID): Foreign key to Integration (denormalized from tool)
            execution_end (datetime.datetime | None | Unset): Execution completion timestamp
            duration_ms (int | None | Unset): Execution duration in milliseconds
            output_data (None | ToolExecutionOutputDataType0 | Unset): Tool output data
            error_message (None | str | Unset): Error description for failed executions
            error_code (None | str | Unset): Structured error code
    """

    created_by: UUID
    user_id: UUID
    execution_start: datetime.datetime
    status: ToolExecutionStatus
    input_parameters: ToolExecutionInputParameters
    id: UUID | Unset = UNSET
    created_at: datetime.datetime | Unset = UNSET
    updated_at: datetime.datetime | Unset = UNSET
    labels: ToolExecutionLabels | Unset = UNSET
    updated_by: None | Unset | UUID = UNSET
    tool_id: None | Unset | UUID = UNSET
    integration_id: None | Unset | UUID = UNSET
    execution_end: datetime.datetime | None | Unset = UNSET
    duration_ms: int | None | Unset = UNSET
    output_data: None | ToolExecutionOutputDataType0 | Unset = UNSET
    error_message: None | str | Unset = UNSET
    error_code: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.tool_execution_output_data_type_0 import ToolExecutionOutputDataType0

        created_by = str(self.created_by)

        user_id = str(self.user_id)

        execution_start = self.execution_start.isoformat()

        status = self.status.value

        input_parameters = self.input_parameters.to_dict()

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

        updated_by: None | str | Unset
        if isinstance(self.updated_by, Unset):
            updated_by = UNSET
        elif isinstance(self.updated_by, UUID):
            updated_by = str(self.updated_by)
        else:
            updated_by = self.updated_by

        tool_id: None | str | Unset
        if isinstance(self.tool_id, Unset):
            tool_id = UNSET
        elif isinstance(self.tool_id, UUID):
            tool_id = str(self.tool_id)
        else:
            tool_id = self.tool_id

        integration_id: None | str | Unset
        if isinstance(self.integration_id, Unset):
            integration_id = UNSET
        elif isinstance(self.integration_id, UUID):
            integration_id = str(self.integration_id)
        else:
            integration_id = self.integration_id

        execution_end: None | str | Unset
        if isinstance(self.execution_end, Unset):
            execution_end = UNSET
        elif isinstance(self.execution_end, datetime.datetime):
            execution_end = self.execution_end.isoformat()
        else:
            execution_end = self.execution_end

        duration_ms: int | None | Unset
        if isinstance(self.duration_ms, Unset):
            duration_ms = UNSET
        else:
            duration_ms = self.duration_ms

        output_data: dict[str, Any] | None | Unset
        if isinstance(self.output_data, Unset):
            output_data = UNSET
        elif isinstance(self.output_data, ToolExecutionOutputDataType0):
            output_data = self.output_data.to_dict()
        else:
            output_data = self.output_data

        error_message: None | str | Unset
        if isinstance(self.error_message, Unset):
            error_message = UNSET
        else:
            error_message = self.error_message

        error_code: None | str | Unset
        if isinstance(self.error_code, Unset):
            error_code = UNSET
        else:
            error_code = self.error_code

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "created_by": created_by,
                "user_id": user_id,
                "execution_start": execution_start,
                "status": status,
                "input_parameters": input_parameters,
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
        if updated_by is not UNSET:
            field_dict["updated_by"] = updated_by
        if tool_id is not UNSET:
            field_dict["tool_id"] = tool_id
        if integration_id is not UNSET:
            field_dict["integration_id"] = integration_id
        if execution_end is not UNSET:
            field_dict["execution_end"] = execution_end
        if duration_ms is not UNSET:
            field_dict["duration_ms"] = duration_ms
        if output_data is not UNSET:
            field_dict["output_data"] = output_data
        if error_message is not UNSET:
            field_dict["error_message"] = error_message
        if error_code is not UNSET:
            field_dict["error_code"] = error_code

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.tool_execution_input_parameters import ToolExecutionInputParameters
        from ..models.tool_execution_labels import ToolExecutionLabels
        from ..models.tool_execution_output_data_type_0 import ToolExecutionOutputDataType0

        d = dict(src_dict)
        created_by = UUID(d.pop("created_by"))

        user_id = UUID(d.pop("user_id"))

        execution_start = isoparse(d.pop("execution_start"))

        status = ToolExecutionStatus(d.pop("status"))

        input_parameters = ToolExecutionInputParameters.from_dict(d.pop("input_parameters"))

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
        labels: ToolExecutionLabels | Unset
        if isinstance(_labels, Unset):
            labels = UNSET
        else:
            labels = ToolExecutionLabels.from_dict(_labels)

        def _parse_updated_by(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                updated_by_type_0 = UUID(data)

                return updated_by_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        updated_by = _parse_updated_by(d.pop("updated_by", UNSET))

        def _parse_tool_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                tool_id_type_0 = UUID(data)

                return tool_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        tool_id = _parse_tool_id(d.pop("tool_id", UNSET))

        def _parse_integration_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                integration_id_type_0 = UUID(data)

                return integration_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        integration_id = _parse_integration_id(d.pop("integration_id", UNSET))

        def _parse_execution_end(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                execution_end_type_0 = isoparse(data)

                return execution_end_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        execution_end = _parse_execution_end(d.pop("execution_end", UNSET))

        def _parse_duration_ms(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        duration_ms = _parse_duration_ms(d.pop("duration_ms", UNSET))

        def _parse_output_data(data: object) -> None | ToolExecutionOutputDataType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                output_data_type_0 = ToolExecutionOutputDataType0.from_dict(data)

                return output_data_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ToolExecutionOutputDataType0 | Unset, data)

        output_data = _parse_output_data(d.pop("output_data", UNSET))

        def _parse_error_message(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error_message = _parse_error_message(d.pop("error_message", UNSET))

        def _parse_error_code(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error_code = _parse_error_code(d.pop("error_code", UNSET))

        tool_execution = cls(
            created_by=created_by,
            user_id=user_id,
            execution_start=execution_start,
            status=status,
            input_parameters=input_parameters,
            id=id,
            created_at=created_at,
            updated_at=updated_at,
            labels=labels,
            updated_by=updated_by,
            tool_id=tool_id,
            integration_id=integration_id,
            execution_end=execution_end,
            duration_ms=duration_ms,
            output_data=output_data,
            error_message=error_message,
            error_code=error_code,
        )

        return tool_execution
