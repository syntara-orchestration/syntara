from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.kafka_source_configuration import KafkaSourceConfiguration


T = TypeVar("T", bound="EventSubscriptionSourceRead")


@_attrs_define
class EventSubscriptionSourceRead:
    """The current source's non-secret configuration.

    Attributes:
        id (UUID):
        generation (int):
        integration_id (None | UUID):
        transport (str):
        configuration (KafkaSourceConfiguration): Fixed Kafka source address for one source generation; no secrets or
            payloads.

            ``topic`` and the generated ``group_id`` are immutable within a generation.
            ``cluster_id`` and ``topic_id`` are populated once during verified
            initialization where the broker exposes them; an identity change creates a
            new generation rather than mutating these fields.
        initialized_at (datetime.datetime | None | Unset):
        retired_at (datetime.datetime | None | Unset):
        retirement_completed_at (datetime.datetime | None | Unset):
    """

    id: UUID
    generation: int
    integration_id: None | UUID
    transport: str
    configuration: KafkaSourceConfiguration
    initialized_at: datetime.datetime | None | Unset = UNSET
    retired_at: datetime.datetime | None | Unset = UNSET
    retirement_completed_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        generation = self.generation

        integration_id: None | str
        if isinstance(self.integration_id, UUID):
            integration_id = str(self.integration_id)
        else:
            integration_id = self.integration_id

        transport = self.transport

        configuration = self.configuration.to_dict()

        initialized_at: None | str | Unset
        if isinstance(self.initialized_at, Unset):
            initialized_at = UNSET
        elif isinstance(self.initialized_at, datetime.datetime):
            initialized_at = self.initialized_at.isoformat()
        else:
            initialized_at = self.initialized_at

        retired_at: None | str | Unset
        if isinstance(self.retired_at, Unset):
            retired_at = UNSET
        elif isinstance(self.retired_at, datetime.datetime):
            retired_at = self.retired_at.isoformat()
        else:
            retired_at = self.retired_at

        retirement_completed_at: None | str | Unset
        if isinstance(self.retirement_completed_at, Unset):
            retirement_completed_at = UNSET
        elif isinstance(self.retirement_completed_at, datetime.datetime):
            retirement_completed_at = self.retirement_completed_at.isoformat()
        else:
            retirement_completed_at = self.retirement_completed_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "generation": generation,
                "integration_id": integration_id,
                "transport": transport,
                "configuration": configuration,
            }
        )
        if initialized_at is not UNSET:
            field_dict["initialized_at"] = initialized_at
        if retired_at is not UNSET:
            field_dict["retired_at"] = retired_at
        if retirement_completed_at is not UNSET:
            field_dict["retirement_completed_at"] = retirement_completed_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.kafka_source_configuration import KafkaSourceConfiguration

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        generation = d.pop("generation")

        def _parse_integration_id(data: object) -> None | UUID:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                integration_id_type_0 = UUID(data)

                return integration_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | UUID, data)

        integration_id = _parse_integration_id(d.pop("integration_id"))

        transport = d.pop("transport")

        configuration = KafkaSourceConfiguration.from_dict(d.pop("configuration"))

        def _parse_initialized_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                initialized_at_type_0 = isoparse(data)

                return initialized_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        initialized_at = _parse_initialized_at(d.pop("initialized_at", UNSET))

        def _parse_retired_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                retired_at_type_0 = isoparse(data)

                return retired_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        retired_at = _parse_retired_at(d.pop("retired_at", UNSET))

        def _parse_retirement_completed_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                retirement_completed_at_type_0 = isoparse(data)

                return retirement_completed_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        retirement_completed_at = _parse_retirement_completed_at(d.pop("retirement_completed_at", UNSET))

        event_subscription_source_read = cls(
            id=id,
            generation=generation,
            integration_id=integration_id,
            transport=transport,
            configuration=configuration,
            initialized_at=initialized_at,
            retired_at=retired_at,
            retirement_completed_at=retirement_completed_at,
        )

        event_subscription_source_read.additional_properties = d
        return event_subscription_source_read

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
