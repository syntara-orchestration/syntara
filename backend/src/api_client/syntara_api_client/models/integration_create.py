from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define

from ..models.integration_scope import IntegrationScope
from ..models.integration_type import IntegrationType
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.aap_configuration import AAPConfiguration
    from ..models.initial_model_selection import InitialModelSelection
    from ..models.initial_tool_selection import InitialToolSelection
    from ..models.integration_create_labels import IntegrationCreateLabels
    from ..models.llm_provider_configuration import LLMProviderConfiguration
    from ..models.mcp_server_configuration_input import MCPServerConfigurationInput


T = TypeVar("T", bound="IntegrationCreate")


@_attrs_define
class IntegrationCreate:
    """Schema for creating a new integration.

    Attributes:
        name (str): Human-readable name for the integration
        integration_type (IntegrationType): Type of external integration.
        configuration (AAPConfiguration | LLMProviderConfiguration | MCPServerConfigurationInput): Integration-specific
            configuration
        description (None | str | Unset): Detailed description of the integration
        management_credential_id (None | Unset | UUID): Optional credential for admin operations
        enabled (bool | Unset): Whether the integration is active Default: True.
        scope (IntegrationScope | Unset): Visibility scope of an integration.
        labels (IntegrationCreateLabels | Unset): Key-value labels
        discovered_tools (list[InitialToolSelection] | None | Unset): Tools discovered during setup with
            enabled/disabled selections
        discovered_models (list[InitialModelSelection] | None | Unset): Models discovered during setup with
            enabled/disabled selections
    """

    name: str
    integration_type: IntegrationType
    configuration: AAPConfiguration | LLMProviderConfiguration | MCPServerConfigurationInput
    description: None | str | Unset = UNSET
    management_credential_id: None | Unset | UUID = UNSET
    enabled: bool | Unset = True
    scope: IntegrationScope | Unset = UNSET
    labels: IntegrationCreateLabels | Unset = UNSET
    discovered_tools: list[InitialToolSelection] | None | Unset = UNSET
    discovered_models: list[InitialModelSelection] | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.llm_provider_configuration import LLMProviderConfiguration
        from ..models.mcp_server_configuration_input import MCPServerConfigurationInput

        name = self.name

        integration_type = self.integration_type.value

        configuration: dict[str, Any]
        if isinstance(self.configuration, MCPServerConfigurationInput):
            configuration = self.configuration.to_dict()
        elif isinstance(self.configuration, LLMProviderConfiguration):
            configuration = self.configuration.to_dict()
        else:
            configuration = self.configuration.to_dict()

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

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

        discovered_tools: list[dict[str, Any]] | None | Unset
        if isinstance(self.discovered_tools, Unset):
            discovered_tools = UNSET
        elif isinstance(self.discovered_tools, list):
            discovered_tools = []
            for discovered_tools_type_0_item_data in self.discovered_tools:
                discovered_tools_type_0_item = discovered_tools_type_0_item_data.to_dict()
                discovered_tools.append(discovered_tools_type_0_item)

        else:
            discovered_tools = self.discovered_tools

        discovered_models: list[dict[str, Any]] | None | Unset
        if isinstance(self.discovered_models, Unset):
            discovered_models = UNSET
        elif isinstance(self.discovered_models, list):
            discovered_models = []
            for discovered_models_type_0_item_data in self.discovered_models:
                discovered_models_type_0_item = discovered_models_type_0_item_data.to_dict()
                discovered_models.append(discovered_models_type_0_item)

        else:
            discovered_models = self.discovered_models

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "name": name,
                "integration_type": integration_type,
                "configuration": configuration,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description
        if management_credential_id is not UNSET:
            field_dict["management_credential_id"] = management_credential_id
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if scope is not UNSET:
            field_dict["scope"] = scope
        if labels is not UNSET:
            field_dict["labels"] = labels
        if discovered_tools is not UNSET:
            field_dict["discovered_tools"] = discovered_tools
        if discovered_models is not UNSET:
            field_dict["discovered_models"] = discovered_models

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.aap_configuration import AAPConfiguration
        from ..models.initial_model_selection import InitialModelSelection
        from ..models.initial_tool_selection import InitialToolSelection
        from ..models.integration_create_labels import IntegrationCreateLabels
        from ..models.llm_provider_configuration import LLMProviderConfiguration
        from ..models.mcp_server_configuration_input import MCPServerConfigurationInput

        d = dict(src_dict)
        name = d.pop("name")

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

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

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
        labels: IntegrationCreateLabels | Unset
        if isinstance(_labels, Unset):
            labels = UNSET
        else:
            labels = IntegrationCreateLabels.from_dict(_labels)

        def _parse_discovered_tools(data: object) -> list[InitialToolSelection] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                discovered_tools_type_0 = []
                _discovered_tools_type_0 = data
                for discovered_tools_type_0_item_data in _discovered_tools_type_0:
                    discovered_tools_type_0_item = InitialToolSelection.from_dict(discovered_tools_type_0_item_data)

                    discovered_tools_type_0.append(discovered_tools_type_0_item)

                return discovered_tools_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[InitialToolSelection] | None | Unset, data)

        discovered_tools = _parse_discovered_tools(d.pop("discovered_tools", UNSET))

        def _parse_discovered_models(data: object) -> list[InitialModelSelection] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                discovered_models_type_0 = []
                _discovered_models_type_0 = data
                for discovered_models_type_0_item_data in _discovered_models_type_0:
                    discovered_models_type_0_item = InitialModelSelection.from_dict(discovered_models_type_0_item_data)

                    discovered_models_type_0.append(discovered_models_type_0_item)

                return discovered_models_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[InitialModelSelection] | None | Unset, data)

        discovered_models = _parse_discovered_models(d.pop("discovered_models", UNSET))

        integration_create = cls(
            name=name,
            integration_type=integration_type,
            configuration=configuration,
            description=description,
            management_credential_id=management_credential_id,
            enabled=enabled,
            scope=scope,
            labels=labels,
            discovered_tools=discovered_tools,
            discovered_models=discovered_models,
        )

        return integration_create
