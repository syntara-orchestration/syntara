from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define

from ..models.integration_type import IntegrationType
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.aap_configuration import AAPConfiguration
    from ..models.llm_provider_configuration import LLMProviderConfiguration
    from ..models.mcp_server_configuration_input import MCPServerConfigurationInput


T = TypeVar("T", bound="IntegrationTestConnection")


@_attrs_define
class IntegrationTestConnection:
    """Schema for testing a connection without saving an integration.

    Attributes:
        integration_type (IntegrationType): Type of external integration.
        configuration (AAPConfiguration | LLMProviderConfiguration | MCPServerConfigurationInput): Integration-specific
            configuration
        credential_id (None | Unset | UUID): Credential to use for the connection test
    """

    integration_type: IntegrationType
    configuration: AAPConfiguration | LLMProviderConfiguration | MCPServerConfigurationInput
    credential_id: None | Unset | UUID = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.llm_provider_configuration import LLMProviderConfiguration
        from ..models.mcp_server_configuration_input import MCPServerConfigurationInput

        integration_type = self.integration_type.value

        configuration: dict[str, Any]
        if isinstance(self.configuration, MCPServerConfigurationInput):
            configuration = self.configuration.to_dict()
        elif isinstance(self.configuration, LLMProviderConfiguration):
            configuration = self.configuration.to_dict()
        else:
            configuration = self.configuration.to_dict()

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
                "integration_type": integration_type,
                "configuration": configuration,
            }
        )
        if credential_id is not UNSET:
            field_dict["credential_id"] = credential_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.aap_configuration import AAPConfiguration
        from ..models.llm_provider_configuration import LLMProviderConfiguration
        from ..models.mcp_server_configuration_input import MCPServerConfigurationInput

        d = dict(src_dict)
        integration_type = IntegrationType(d.pop("integration_type"))

        def _parse_configuration(
            data: object,
        ) -> AAPConfiguration | LLMProviderConfiguration | MCPServerConfigurationInput:
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                configuration_type_0 = MCPServerConfigurationInput.from_dict(data)

                return configuration_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                configuration_type_1 = LLMProviderConfiguration.from_dict(data)

                return configuration_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            configuration_type_2 = AAPConfiguration.from_dict(data)

            return configuration_type_2

        configuration = _parse_configuration(d.pop("configuration"))

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

        integration_test_connection = cls(
            integration_type=integration_type,
            configuration=configuration,
            credential_id=credential_id,
        )

        return integration_test_connection
