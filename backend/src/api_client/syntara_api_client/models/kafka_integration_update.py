from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define

from ..models.integration_scope import IntegrationScope
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.kafka_configuration import KafkaConfiguration
    from ..models.kafka_integration_update_labels_type_0 import KafkaIntegrationUpdateLabelsType0


T = TypeVar("T", bound="KafkaIntegrationUpdate")


@_attrs_define
class KafkaIntegrationUpdate:
    """Patch Kafka settings, preserving omitted fields.

    Attributes:
        name (None | str | Unset):
        description (None | str | Unset):
        configuration (KafkaConfiguration | None | Unset):
        management_credential_id (None | Unset | UUID):
        enabled (bool | None | Unset):
        scope (IntegrationScope | None | Unset):
        labels (KafkaIntegrationUpdateLabelsType0 | None | Unset):
    """

    name: None | str | Unset = UNSET
    description: None | str | Unset = UNSET
    configuration: KafkaConfiguration | None | Unset = UNSET
    management_credential_id: None | Unset | UUID = UNSET
    enabled: bool | None | Unset = UNSET
    scope: IntegrationScope | None | Unset = UNSET
    labels: KafkaIntegrationUpdateLabelsType0 | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.kafka_configuration import KafkaConfiguration
        from ..models.kafka_integration_update_labels_type_0 import KafkaIntegrationUpdateLabelsType0

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        configuration: dict[str, Any] | None | Unset
        if isinstance(self.configuration, Unset):
            configuration = UNSET
        elif isinstance(self.configuration, KafkaConfiguration):
            configuration = self.configuration.to_dict()
        else:
            configuration = self.configuration

        management_credential_id: None | str | Unset
        if isinstance(self.management_credential_id, Unset):
            management_credential_id = UNSET
        elif isinstance(self.management_credential_id, UUID):
            management_credential_id = str(self.management_credential_id)
        else:
            management_credential_id = self.management_credential_id

        enabled: bool | None | Unset
        if isinstance(self.enabled, Unset):
            enabled = UNSET
        else:
            enabled = self.enabled

        scope: None | str | Unset
        if isinstance(self.scope, Unset):
            scope = UNSET
        elif isinstance(self.scope, IntegrationScope):
            scope = self.scope.value
        else:
            scope = self.scope

        labels: dict[str, Any] | None | Unset
        if isinstance(self.labels, Unset):
            labels = UNSET
        elif isinstance(self.labels, KafkaIntegrationUpdateLabelsType0):
            labels = self.labels.to_dict()
        else:
            labels = self.labels

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if name is not UNSET:
            field_dict["name"] = name
        if description is not UNSET:
            field_dict["description"] = description
        if configuration is not UNSET:
            field_dict["configuration"] = configuration
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
        from ..models.kafka_integration_update_labels_type_0 import KafkaIntegrationUpdateLabelsType0

        d = dict(src_dict)

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        def _parse_configuration(data: object) -> KafkaConfiguration | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                configuration_type_0 = KafkaConfiguration.from_dict(data)

                return configuration_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(KafkaConfiguration | None | Unset, data)

        configuration = _parse_configuration(d.pop("configuration", UNSET))

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

        def _parse_enabled(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        enabled = _parse_enabled(d.pop("enabled", UNSET))

        def _parse_scope(data: object) -> IntegrationScope | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                scope_type_0 = IntegrationScope(data)

                return scope_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(IntegrationScope | None | Unset, data)

        scope = _parse_scope(d.pop("scope", UNSET))

        def _parse_labels(data: object) -> KafkaIntegrationUpdateLabelsType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                labels_type_0 = KafkaIntegrationUpdateLabelsType0.from_dict(data)

                return labels_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(KafkaIntegrationUpdateLabelsType0 | None | Unset, data)

        labels = _parse_labels(d.pop("labels", UNSET))

        kafka_integration_update = cls(
            name=name,
            description=description,
            configuration=configuration,
            management_credential_id=management_credential_id,
            enabled=enabled,
            scope=scope,
            labels=labels,
        )

        return kafka_integration_update
