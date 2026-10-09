from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define

T = TypeVar("T", bound="LLMModelBulkUpdate")


@_attrs_define
class LLMModelBulkUpdate:
    """Schema for bulk-updating LLM models.

    Attributes:
        model_ids (list[UUID]): Model IDs to update
        enabled (bool): New enabled state
    """

    model_ids: list[UUID]
    enabled: bool

    def to_dict(self) -> dict[str, Any]:
        model_ids = []
        for model_ids_item_data in self.model_ids:
            model_ids_item = str(model_ids_item_data)
            model_ids.append(model_ids_item)

        enabled = self.enabled

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "model_ids": model_ids,
                "enabled": enabled,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        model_ids = []
        _model_ids = d.pop("model_ids")
        for model_ids_item_data in _model_ids:
            model_ids_item = UUID(model_ids_item_data)

            model_ids.append(model_ids_item)

        enabled = d.pop("enabled")

        llm_model_bulk_update = cls(
            model_ids=model_ids,
            enabled=enabled,
        )

        return llm_model_bulk_update
