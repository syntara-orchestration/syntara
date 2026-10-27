from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define

from ..models.integration_scope import IntegrationScope
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.kafka_configuration import KafkaConfiguration
    from ..models.kafka_integration_create_labels import KafkaIntegrationCreateLabels


T = TypeVar("T", bound="KafkaIntegrationCreate")


@_attrs_define
class KafkaIntegrationCreate:
    """Create a Kafka connection without extending the original integration union.

    Attributes:
        name (str):
        configuration (KafkaConfiguration): Configuration for a Kafka cluster integration.

            Broker addresses live here. The username and password stay on the
            linked Kafka credential when SASL_SSL is selected. Unauthenticated SSL
            and explicitly opted-in PLAINTEXT do not require a credential.
        description (None | str | Unset):
        integration_type (Literal['kafka'] | Unset):  Default: 'kafka'.
        management_credential_id (None | Unset | UUID):
        enabled (bool | Unset):  Default: True.
        scope (IntegrationScope | Unset): Visibility scope of an integration.
        labels (KafkaIntegrationCreateLabels | Unset):
    """

    name: str
    configuration: KafkaConfiguration
    description: None | str | Unset = UNSET
    integration_type: Literal["kafka"] | Unset = "kafka"
    management_credential_id: None | Unset | UUID = UNSET
    enabled: bool | Unset = True
    scope: IntegrationScope | Unset = UNSET
    labels: KafkaIntegrationCreateLabels | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        configuration = self.configuration.to_dict()

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        integration_type = self.integration_type

        management_credential_id: None | str | Unset
        if isinstance(self.management_credential_id, Unset):
            management_credential_id = UNSET
        elif isinstance(self.management_credential_id, UUID):
            management_credential_id = str(self.management_credential_id)
        else:
            management_credential_id = self.management_credential_id

        enabled = self.enabled

        scope: str | Unset = UNSET
        if not isinstance(self.scope, Unset):
            scope = self.scope.value

        labels: dict[str, Any] | Unset = UNSET
        if not isinstance(self.labels, Unset):
            labels = self.labels.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "name": name,
                "configuration": configuration,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description
        if integration_type is not UNSET:
            field_dict["integration_type"] = integration_type
        if management_credential_id is not UNSET:
            field_dict["management_credential_id"] = management_credential_id
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if scope is not UNSET:
            field_dict["scope"] = scope
        if labels is not UNSET:
            field_dict["labels"] = labels

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.kafka_configuration import KafkaConfiguration
        from ..models.kafka_integration_create_labels import KafkaIntegrationCreateLabels

        d = dict(src_dict)
        name = d.pop("name")

        configuration = KafkaConfiguration.from_dict(d.pop("configuration"))

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        integration_type = cast(Literal["kafka"] | Unset, d.pop("integration_type", UNSET))
        if integration_type != "kafka" and not isinstance(integration_type, Unset):
            raise ValueError(f"integration_type must match const 'kafka', got '{integration_type}'")

        def _parse_management_credential_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                management_credential_id_type_0 = UUID(data)

                return management_credential_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        management_credential_id = _parse_management_credential_id(d.pop("management_credential_id", UNSET))

        enabled = d.pop("enabled", UNSET)

        _scope = d.pop("scope", UNSET)
        scope: IntegrationScope | Unset
        if isinstance(_scope, Unset):
            scope = UNSET
        else:
            scope = IntegrationScope(_scope)

        _labels = d.pop("labels", UNSET)
        labels: KafkaIntegrationCreateLabels | Unset
        if isinstance(_labels, Unset):
            labels = UNSET
        else:
            labels = KafkaIntegrationCreateLabels.from_dict(_labels)

        kafka_integration_create = cls(
            name=name,
            configuration=configuration,
            description=description,
            integration_type=integration_type,
            management_credential_id=management_credential_id,
            enabled=enabled,
            scope=scope,
            labels=labels,
        )

        return kafka_integration_create
