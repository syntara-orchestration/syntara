from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.activity_data_output_data_type_0 import ActivityDataOutputDataType0


T = TypeVar("T", bound="ActivityData")


@_attrs_define
class ActivityData:
    """Activity data for execution response.

    Attributes:
        activity_id (str):
        status (str):
        error_details (None | str | Unset):
        iteration (int | None | Unset):
        output_data (ActivityDataOutputDataType0 | None | Unset):
        started_at (datetime.datetime | None | Unset):
        completed_at (datetime.datetime | None | Unset):
    """

    activity_id: str
    status: str
    error_details: None | str | Unset = UNSET
    iteration: int | None | Unset = UNSET
    output_data: ActivityDataOutputDataType0 | None | Unset = UNSET
    started_at: datetime.datetime | None | Unset = UNSET
    completed_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.activity_data_output_data_type_0 import ActivityDataOutputDataType0

        activity_id = self.activity_id

        status = self.status

        error_details: None | str | Unset
        if isinstance(self.error_details, Unset):
            error_details = UNSET
        else:
            error_details = self.error_details

        iteration: int | None | Unset
        if isinstance(self.iteration, Unset):
            iteration = UNSET
        else:
            iteration = self.iteration

        output_data: dict[str, Any] | None | Unset
        if isinstance(self.output_data, Unset):
            output_data = UNSET
        elif isinstance(self.output_data, ActivityDataOutputDataType0):
            output_data = self.output_data.to_dict()
        else:
            output_data = self.output_data

        started_at: None | str | Unset
        if isinstance(self.started_at, Unset):
            started_at = UNSET
        elif isinstance(self.started_at, datetime.datetime):
            started_at = self.started_at.isoformat()
        else:
            started_at = self.started_at

        completed_at: None | str | Unset
        if isinstance(self.completed_at, Unset):
            completed_at = UNSET
        elif isinstance(self.completed_at, datetime.datetime):
            completed_at = self.completed_at.isoformat()
        else:
            completed_at = self.completed_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "activity_id": activity_id,
                "status": status,
            }
        )
        if error_details is not UNSET:
            field_dict["error_details"] = error_details
        if iteration is not UNSET:
            field_dict["iteration"] = iteration
        if output_data is not UNSET:
            field_dict["output_data"] = output_data
        if started_at is not UNSET:
            field_dict["started_at"] = started_at
        if completed_at is not UNSET:
            field_dict["completed_at"] = completed_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.activity_data_output_data_type_0 import ActivityDataOutputDataType0

        d = dict(src_dict)
        activity_id = d.pop("activity_id")

        status = d.pop("status")

        def _parse_error_details(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error_details = _parse_error_details(d.pop("error_details", UNSET))

        def _parse_iteration(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        iteration = _parse_iteration(d.pop("iteration", UNSET))

        def _parse_output_data(data: object) -> ActivityDataOutputDataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                output_data_type_0 = ActivityDataOutputDataType0.from_dict(data)

                return output_data_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ActivityDataOutputDataType0 | None | Unset, data)

        output_data = _parse_output_data(d.pop("output_data", UNSET))

        def _parse_started_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                started_at_type_0 = isoparse(data)

                return started_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        started_at = _parse_started_at(d.pop("started_at", UNSET))

        def _parse_completed_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                completed_at_type_0 = isoparse(data)

                return completed_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        completed_at = _parse_completed_at(d.pop("completed_at", UNSET))

        activity_data = cls(
            activity_id=activity_id,
            status=status,
            error_details=error_details,
            iteration=iteration,
            output_data=output_data,
            started_at=started_at,
            completed_at=completed_at,
        )

        activity_data.additional_properties = d
        return activity_data

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
