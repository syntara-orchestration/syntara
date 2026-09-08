from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.metric_type import MetricType
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.metric_record_labels import MetricRecordLabels


T = TypeVar("T", bound="MetricRecord")


@_attrs_define
class MetricRecord:
    """Lightweight in-memory metric data point.


    Uses a slotted dataclass instead of SQLModel to reduce per-instance

    memory from ~4.1KB to ~72 bytes.  This record never touches a database.

      Attributes:
          metric_type (MetricType): Categories of metrics recorded by Orchestrator.

              Each value corresponds to a specific measurable quantity exposed via the
              metrics REST API and (where applicable) Prometheus endpoint.
          value (float):
          unit (str | Unset):  Default: ''.
          labels (MetricRecordLabels | Unset):
          id (UUID | Unset):
          created_at (datetime.datetime | Unset):
    """

    metric_type: MetricType
    value: float
    unit: str | Unset = ""
    labels: MetricRecordLabels | Unset = UNSET
    id: UUID | Unset = UNSET
    created_at: datetime.datetime | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        metric_type = self.metric_type.value

        value = self.value

        unit = self.unit

        labels: dict[str, Any] | Unset = UNSET
        if not isinstance(self.labels, Unset):
            labels = self.labels.to_dict()

        id: str | Unset = UNSET
        if not isinstance(self.id, Unset):
            id = str(self.id)

        created_at: str | Unset = UNSET
        if not isinstance(self.created_at, Unset):
            created_at = self.created_at.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "metric_type": metric_type,
                "value": value,
            }
        )
        if unit is not UNSET:
            field_dict["unit"] = unit
        if labels is not UNSET:
            field_dict["labels"] = labels
        if id is not UNSET:
            field_dict["id"] = id
        if created_at is not UNSET:
            field_dict["created_at"] = created_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.metric_record_labels import MetricRecordLabels

        d = dict(src_dict)
        metric_type = MetricType(d.pop("metric_type"))

        value = d.pop("value")

        unit = d.pop("unit", UNSET)

        _labels = d.pop("labels", UNSET)
        labels: MetricRecordLabels | Unset
        if isinstance(_labels, Unset):
            labels = UNSET
        else:
            labels = MetricRecordLabels.from_dict(_labels)

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

        metric_record = cls(
            metric_type=metric_type,
            value=value,
            unit=unit,
            labels=labels,
            id=id,
            created_at=created_at,
        )

        metric_record.additional_properties = d
        return metric_record

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
