from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.filter_configuration import FilterConfiguration
    from ..models.kafka_subscribe_parameters_input_schema_type_0 import KafkaSubscribeParametersInputSchemaType0


T = TypeVar("T", bound="KafkaSubscribeParameters")


@_attrs_define
class KafkaSubscribeParameters:
    """One exact topic; consumer groups and connection settings are not inputs.

    Tightens the transport-neutral ``topic`` with Kafka's naming constraints.

        Attributes:
            integration_id (UUID):
            credential_id (UUID):
            topic (str):
            filter_ (FilterConfiguration | None | Unset):
            input_schema (KafkaSubscribeParametersInputSchemaType0 | None | Unset):
    """

    integration_id: UUID
    credential_id: UUID
    topic: str
    filter_: FilterConfiguration | None | Unset = UNSET
    input_schema: KafkaSubscribeParametersInputSchemaType0 | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.filter_configuration import FilterConfiguration
        from ..models.kafka_subscribe_parameters_input_schema_type_0 import KafkaSubscribeParametersInputSchemaType0

        integration_id = str(self.integration_id)

        credential_id = str(self.credential_id)

        topic = self.topic

        filter_: dict[str, Any] | None | Unset
        if isinstance(self.filter_, Unset):
            filter_ = UNSET
        elif isinstance(self.filter_, FilterConfiguration):
            filter_ = self.filter_.to_dict()
        else:
            filter_ = self.filter_

        input_schema: dict[str, Any] | None | Unset
        if isinstance(self.input_schema, Unset):
            input_schema = UNSET
        elif isinstance(self.input_schema, KafkaSubscribeParametersInputSchemaType0):
            input_schema = self.input_schema.to_dict()
        else:
            input_schema = self.input_schema

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "integration_id": integration_id,
                "credential_id": credential_id,
                "topic": topic,
            }
        )
        if filter_ is not UNSET:
            field_dict["filter"] = filter_
        if input_schema is not UNSET:
            field_dict["input_schema"] = input_schema

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.filter_configuration import FilterConfiguration
        from ..models.kafka_subscribe_parameters_input_schema_type_0 import KafkaSubscribeParametersInputSchemaType0

        d = dict(src_dict)
        integration_id = UUID(d.pop("integration_id"))

        credential_id = UUID(d.pop("credential_id"))

        topic = d.pop("topic")

        def _parse_filter_(data: object) -> FilterConfiguration | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                filter_type_0 = FilterConfiguration.from_dict(data)

                return filter_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(FilterConfiguration | None | Unset, data)

        filter_ = _parse_filter_(d.pop("filter", UNSET))

        def _parse_input_schema(data: object) -> KafkaSubscribeParametersInputSchemaType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                input_schema_type_0 = KafkaSubscribeParametersInputSchemaType0.from_dict(data)

                return input_schema_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(KafkaSubscribeParametersInputSchemaType0 | None | Unset, data)

        input_schema = _parse_input_schema(d.pop("input_schema", UNSET))

        kafka_subscribe_parameters = cls(
            integration_id=integration_id,
            credential_id=credential_id,
            topic=topic,
            filter_=filter_,
            input_schema=input_schema,
        )

        return kafka_subscribe_parameters
