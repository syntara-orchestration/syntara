from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.component_kpi_summary_metrics import ComponentKPISummaryMetrics


T = TypeVar("T", bound="ComponentKPISummary")


@_attrs_define
class ComponentKPISummary:
    """KPI summary for a single Orchestrator component.

    Attributes:
        component (str): Component identifier
        metrics (ComponentKPISummaryMetrics | Unset): Metric name → stats, scalar value, or distribution map
    """

    component: str
    metrics: ComponentKPISummaryMetrics | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        component = self.component

        metrics: dict[str, Any] | Unset = UNSET
        if not isinstance(self.metrics, Unset):
            metrics = self.metrics.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "component": component,
            }
        )
        if metrics is not UNSET:
            field_dict["metrics"] = metrics

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.component_kpi_summary_metrics import ComponentKPISummaryMetrics

        d = dict(src_dict)
        component = d.pop("component")

        _metrics = d.pop("metrics", UNSET)
        metrics: ComponentKPISummaryMetrics | Unset
        if isinstance(_metrics, Unset):
            metrics = UNSET
        else:
            metrics = ComponentKPISummaryMetrics.from_dict(_metrics)

        component_kpi_summary = cls(
            component=component,
            metrics=metrics,
        )

        return component_kpi_summary
