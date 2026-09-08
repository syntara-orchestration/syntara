from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="IntegrationConnectionConfig")


@_attrs_define
class IntegrationConnectionConfig:
    """Execution credential override for one integration.


    When included in AgenticExecutorParameters.integration_connections, this credential

    is used for calls against that integration instead of the integration's

    management credential.

        Attributes:
            integration_id (str): UUID of the integration
            credential_id (str): Orchestrator credential UUID for execution calls (distinct from management credential)
    """

    integration_id: str
    credential_id: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        integration_id = self.integration_id

        credential_id = self.credential_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "integration_id": integration_id,
                "credential_id": credential_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        integration_id = d.pop("integration_id")

        credential_id = d.pop("credential_id")

        integration_connection_config = cls(
            integration_id=integration_id,
            credential_id=credential_id,
        )

        integration_connection_config.additional_properties = d
        return integration_connection_config

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
