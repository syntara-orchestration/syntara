from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from dateutil.parser import isoparse

T = TypeVar("T", bound="LLMModelBulkUpdateResponse")


@_attrs_define
class LLMModelBulkUpdateResponse:
    """Response for bulk LLM model update.

    Attributes:
        updated_count (int): Number of models updated
        skipped_count (int): Number of model IDs not found in integration
        updated_at (datetime.datetime): Timestamp of the update
    """

    updated_count: int
    skipped_count: int
    updated_at: datetime.datetime

    def to_dict(self) -> dict[str, Any]:
        updated_count = self.updated_count

        skipped_count = self.skipped_count

        updated_at = self.updated_at.isoformat()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "updated_count": updated_count,
                "skipped_count": skipped_count,
                "updated_at": updated_at,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        updated_count = d.pop("updated_count")

        skipped_count = d.pop("skipped_count")

        updated_at = isoparse(d.pop("updated_at"))

        llm_model_bulk_update_response = cls(
            updated_count=updated_count,
            skipped_count=skipped_count,
            updated_at=updated_at,
        )

        return llm_model_bulk_update_response
