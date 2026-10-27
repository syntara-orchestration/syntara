from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.kafka_configuration import KafkaConfiguration


T = TypeVar("T", bound="KafkaIntegrationTestConnection")


@_attrs_define
class KafkaIntegrationTestConnection:
    """Test a Kafka connection without persisting it.

    Attributes:
        configuration (KafkaConfiguration): Configuration for a Kafka cluster integration.

            Broker addresses live here. The username and password stay on the
            linked Kafka credential when SASL_SSL is selected. Unauthenticated SSL
            and explicitly opted-in PLAINTEXT do not require a credential.
        integration_type (Literal['kafka'] | Unset):  Default: 'kafka'.
        credential_id (None | Unset | UUID):
    """

    configuration: KafkaConfiguration
    integration_type: Literal["kafka"] | Unset = "kafka"
    credential_id: None | Unset | UUID = UNSET

    def to_dict(self) -> dict[str, Any]:
        configuration = self.configuration.to_dict()

        integration_type = self.integration_type

        credential_id: None | str | Unset
        if isinstance(self.credential_id, Unset):
            credential_id = UNSET
        elif isinstance(self.credential_id, UUID):
            credential_id = str(self.credential_id)
        else:
            credential_id = self.credential_id

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "configuration": configuration,
            }
        )
        if integration_type is not UNSET:
            field_dict["integration_type"] = integration_type
        if credential_id is not UNSET:
            field_dict["credential_id"] = credential_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.kafka_configuration import KafkaConfiguration

        d = dict(src_dict)
        configuration = KafkaConfiguration.from_dict(d.pop("configuration"))

        integration_type = cast(Literal["kafka"] | Unset, d.pop("integration_type", UNSET))
        if integration_type != "kafka" and not isinstance(integration_type, Unset):
            raise ValueError(f"integration_type must match const 'kafka', got '{integration_type}'")

        def _parse_credential_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                credential_id_type_0 = UUID(data)

                return credential_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        credential_id = _parse_credential_id(d.pop("credential_id", UNSET))

        kafka_integration_test_connection = cls(
            configuration=configuration,
            integration_type=integration_type,
            credential_id=credential_id,
        )

        return kafka_integration_test_connection
