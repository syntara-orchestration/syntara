from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="ToolMetricsToolSummary")


@_attrs_define
class ToolMetricsToolSummary:
    """Per-tool aggregated metrics summary for the metrics/tools endpoint.

    Attributes:
        namespaced_name (str): Tool identifier (e.g., 'provider::tool')
        total_executions (int): Total execution count
        success_count (int): Successful executions
        error_count (int): Error executions
        timeout_count (int): Timeout executions
        success_rate (float): Success rate (0.0 to 1.0)
        avg_duration_ms (float): Average execution duration in milliseconds
        last_execution_at (datetime.datetime | None | Unset): Timestamp of most recent execution
    """

    namespaced_name: str
    total_executions: int
    success_count: int
    error_count: int
    timeout_count: int
    success_rate: float
    avg_duration_ms: float
    last_execution_at: datetime.datetime | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        namespaced_name = self.namespaced_name

        total_executions = self.total_executions

        success_count = self.success_count

        error_count = self.error_count

        timeout_count = self.timeout_count

        success_rate = self.success_rate

        avg_duration_ms = self.avg_duration_ms

        last_execution_at: None | str | Unset
        if isinstance(self.last_execution_at, Unset):
            last_execution_at = UNSET
        elif isinstance(self.last_execution_at, datetime.datetime):
            last_execution_at = self.last_execution_at.isoformat()
        else:
            last_execution_at = self.last_execution_at

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "namespaced_name": namespaced_name,
                "total_executions": total_executions,
                "success_count": success_count,
                "error_count": error_count,
                "timeout_count": timeout_count,
                "success_rate": success_rate,
                "avg_duration_ms": avg_duration_ms,
            }
        )
        if last_execution_at is not UNSET:
            field_dict["last_execution_at"] = last_execution_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        namespaced_name = d.pop("namespaced_name")

        total_executions = d.pop("total_executions")

        success_count = d.pop("success_count")

        error_count = d.pop("error_count")

        timeout_count = d.pop("timeout_count")

        success_rate = d.pop("success_rate")

        avg_duration_ms = d.pop("avg_duration_ms")

        def _parse_last_execution_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_execution_at_type_0 = isoparse(data)

                return last_execution_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        last_execution_at = _parse_last_execution_at(d.pop("last_execution_at", UNSET))

        tool_metrics_tool_summary = cls(
            namespaced_name=namespaced_name,
            total_executions=total_executions,
            success_count=success_count,
            error_count=error_count,
            timeout_count=timeout_count,
            success_rate=success_rate,
            avg_duration_ms=avg_duration_ms,
            last_execution_at=last_execution_at,
        )

        return tool_metrics_tool_summary
