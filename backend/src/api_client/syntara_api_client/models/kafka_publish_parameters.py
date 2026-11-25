from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.kafka_encoded_value import KafkaEncodedValue
    from ..models.kafka_publish_header import KafkaPublishHeader


T = TypeVar("T", bound="KafkaPublishParameters")


@_attrs_define
class KafkaPublishParameters:
    """Fixed destination and a templated JSON message, with no producer overrides.

    Attributes:
        integration_id (str):
        credential_id (str): Required runtime Kafka credential reference
        topic (str):
        payload (Any): Required JSON value; explicit null publishes JSON null, not a tombstone
        key (KafkaEncodedValue | None | Unset):
        headers (list[KafkaPublishHeader] | str | Unset):
        cloudevents_mode (bool | Unset): Automatically add binary-mode CloudEvents headers Default: False.
        ce_type (None | str | Unset): Required event type when CloudEvents mode is enabled
        ce_source (None | str | Unset): Required event source URI-reference in CloudEvents mode
    """

    integration_id: str
    credential_id: str
    topic: str
    payload: Any
    key: KafkaEncodedValue | None | Unset = UNSET
    headers: list[KafkaPublishHeader] | str | Unset = UNSET
    cloudevents_mode: bool | Unset = False
    ce_type: None | str | Unset = UNSET
    ce_source: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.kafka_encoded_value import KafkaEncodedValue

        integration_id = self.integration_id

        credential_id = self.credential_id

        topic = self.topic

        payload = self.payload

        key: dict[str, Any] | None | Unset
        if isinstance(self.key, Unset):
            key = UNSET
        elif isinstance(self.key, KafkaEncodedValue):
            key = self.key.to_dict()
        else:
            key = self.key

        headers: list[dict[str, Any]] | str | Unset
        if isinstance(self.headers, Unset):
            headers = UNSET
        elif isinstance(self.headers, list):
            headers = []
            for headers_type_0_item_data in self.headers:
                headers_type_0_item = headers_type_0_item_data.to_dict()
                headers.append(headers_type_0_item)

        else:
            headers = self.headers

        cloudevents_mode = self.cloudevents_mode

        ce_type: None | str | Unset
        if isinstance(self.ce_type, Unset):
            ce_type = UNSET
        else:
            ce_type = self.ce_type

        ce_source: None | str | Unset
        if isinstance(self.ce_source, Unset):
            ce_source = UNSET
        else:
            ce_source = self.ce_source

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "integration_id": integration_id,
                "credential_id": credential_id,
                "topic": topic,
                "payload": payload,
            }
        )
        if key is not UNSET:
            field_dict["key"] = key
        if headers is not UNSET:
            field_dict["headers"] = headers
        if cloudevents_mode is not UNSET:
            field_dict["cloudevents_mode"] = cloudevents_mode
        if ce_type is not UNSET:
            field_dict["ce_type"] = ce_type
        if ce_source is not UNSET:
            field_dict["ce_source"] = ce_source

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.kafka_encoded_value import KafkaEncodedValue
        from ..models.kafka_publish_header import KafkaPublishHeader

        d = dict(src_dict)
        integration_id = d.pop("integration_id")

        credential_id = d.pop("credential_id")

        topic = d.pop("topic")

        payload = d.pop("payload")

        def _parse_key(data: object) -> KafkaEncodedValue | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                key_type_0 = KafkaEncodedValue.from_dict(data)

                return key_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(KafkaEncodedValue | None | Unset, data)

        key = _parse_key(d.pop("key", UNSET))

        def _parse_headers(data: object) -> list[KafkaPublishHeader] | str | Unset:
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                headers_type_0 = []
                _headers_type_0 = data
                for headers_type_0_item_data in _headers_type_0:
                    headers_type_0_item = KafkaPublishHeader.from_dict(headers_type_0_item_data)

                    headers_type_0.append(headers_type_0_item)

                return headers_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[KafkaPublishHeader] | str | Unset, data)

        headers = _parse_headers(d.pop("headers", UNSET))

        cloudevents_mode = d.pop("cloudevents_mode", UNSET)

        def _parse_ce_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ce_type = _parse_ce_type(d.pop("ce_type", UNSET))

        def _parse_ce_source(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ce_source = _parse_ce_source(d.pop("ce_source", UNSET))

        kafka_publish_parameters = cls(
            integration_id=integration_id,
            credential_id=credential_id,
            topic=topic,
            payload=payload,
            key=key,
            headers=headers,
            cloudevents_mode=cloudevents_mode,
            ce_type=ce_type,
            ce_source=ce_source,
        )

        return kafka_publish_parameters
