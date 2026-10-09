from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from dateutil.parser import isoparse

from ..models.health_check_error_type import HealthCheckErrorType
from ..types import UNSET, Unset

T = TypeVar("T", bound="ValidateResult")


@_attrs_define
class ValidateResult:
    """Result of a lightweight connectivity ping (validate endpoint).

    Contains only connection-health fields. No resource discovery fields.

        Attributes:
            success (bool):
            checked_at (datetime.datetime):
            error (None | str | Unset):
            error_type (HealthCheckErrorType | None | Unset):
    """

    success: bool
    checked_at: datetime.datetime
    error: None | str | Unset = UNSET
    error_type: HealthCheckErrorType | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        success = self.success

        checked_at = self.checked_at.isoformat()

        error: None | str | Unset
        if isinstance(self.error, Unset):
            error = UNSET
        else:
            error = self.error

        error_type: None | str | Unset
        if isinstance(self.error_type, Unset):
            error_type = UNSET
        elif isinstance(self.error_type, HealthCheckErrorType):
            error_type = self.error_type.value
        else:
            error_type = self.error_type

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "success": success,
                "checked_at": checked_at,
            }
        )
        if error is not UNSET:
            field_dict["error"] = error
        if error_type is not UNSET:
            field_dict["error_type"] = error_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        success = d.pop("success")

        checked_at = isoparse(d.pop("checked_at"))

        def _parse_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error = _parse_error(d.pop("error", UNSET))

        def _parse_error_type(data: object) -> HealthCheckErrorType | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                error_type_type_0 = HealthCheckErrorType(data)

                return error_type_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(HealthCheckErrorType | None | Unset, data)

        error_type = _parse_error_type(d.pop("error_type", UNSET))

        validate_result = cls(
            success=success,
            checked_at=checked_at,
            error=error,
            error_type=error_type,
        )

        return validate_result
