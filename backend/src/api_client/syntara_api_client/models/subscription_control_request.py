from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="SubscriptionControlRequest")


@_attrs_define
class SubscriptionControlRequest:
    """Compare-and-set against the published projection and source generation.

    Attributes:
        configuration_revision (int):
        source_generation (int):
    """

    configuration_revision: int
    source_generation: int

    def to_dict(self) -> dict[str, Any]:
        configuration_revision = self.configuration_revision

        source_generation = self.source_generation

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "configuration_revision": configuration_revision,
                "source_generation": source_generation,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        configuration_revision = d.pop("configuration_revision")

        source_generation = d.pop("source_generation")

        subscription_control_request = cls(
            configuration_revision=configuration_revision,
            source_generation=source_generation,
        )

        return subscription_control_request
