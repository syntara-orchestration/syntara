from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.agentic_executor_parameters_tool_selection_strategy_type_0 import (
    AgenticExecutorParametersToolSelectionStrategyType0,
)
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.agentic_executor_parameters_response_schema_type_0 import AgenticExecutorParametersResponseSchemaType0
    from ..models.integration_connection_config import IntegrationConnectionConfig


T = TypeVar("T", bound="AgenticExecutorParameters")


@_attrs_define
class AgenticExecutorParameters:
    """Parameters for agentic executor.

    Attributes:
        prompt (str): Prompt template for the agent
        agent (None | str | Unset):
        llm_model_id (None | str | Unset): UUID of the LLMModel record identifying the provider integration and model.
        credential_id (None | str | Unset): Syntara credential UUID for LLM provider authentication
        file_ids (list[str] | Unset): File IDs for agent context
        response_schema (AgenticExecutorParametersResponseSchemaType0 | None | str | Unset): JSON Schema for structured
            output. When defined, agent output conforms to this schema.
        integration_connections (list[IntegrationConnectionConfig] | None | Unset): Per-integration execution
            credentials. Each entry overrides the management credential for that integration. Integrations not listed fall
            back to their management credential.
        tool_selection_strategy (AgenticExecutorParametersToolSelectionStrategyType0 | None | Unset): ALL (all enabled
            tools), NONE (no tools), or SELECTED (specific tools from tool_selections)
        tool_selections (list[str] | Unset): Tool UUIDs to make available when tool_selection_strategy is SELECTED
    """

    prompt: str
    agent: None | str | Unset = UNSET
    llm_model_id: None | str | Unset = UNSET
    credential_id: None | str | Unset = UNSET
    file_ids: list[str] | Unset = UNSET
    response_schema: AgenticExecutorParametersResponseSchemaType0 | None | str | Unset = UNSET
    integration_connections: list[IntegrationConnectionConfig] | None | Unset = UNSET
    tool_selection_strategy: AgenticExecutorParametersToolSelectionStrategyType0 | None | Unset = UNSET
    tool_selections: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.agentic_executor_parameters_response_schema_type_0 import (
            AgenticExecutorParametersResponseSchemaType0,
        )

        prompt = self.prompt

        agent: None | str | Unset
        if isinstance(self.agent, Unset):
            agent = UNSET
        else:
            agent = self.agent

        llm_model_id: None | str | Unset
        if isinstance(self.llm_model_id, Unset):
            llm_model_id = UNSET
        else:
            llm_model_id = self.llm_model_id

        credential_id: None | str | Unset
        if isinstance(self.credential_id, Unset):
            credential_id = UNSET
        else:
            credential_id = self.credential_id

        file_ids: list[str] | Unset = UNSET
        if not isinstance(self.file_ids, Unset):
            file_ids = self.file_ids

        response_schema: dict[str, Any] | None | str | Unset
        if isinstance(self.response_schema, Unset):
            response_schema = UNSET
        elif isinstance(self.response_schema, AgenticExecutorParametersResponseSchemaType0):
            response_schema = self.response_schema.to_dict()
        else:
            response_schema = self.response_schema

        integration_connections: list[dict[str, Any]] | None | Unset
        if isinstance(self.integration_connections, Unset):
            integration_connections = UNSET
        elif isinstance(self.integration_connections, list):
            integration_connections = []
            for integration_connections_type_0_item_data in self.integration_connections:
                integration_connections_type_0_item = integration_connections_type_0_item_data.to_dict()
                integration_connections.append(integration_connections_type_0_item)

        else:
            integration_connections = self.integration_connections

        tool_selection_strategy: None | str | Unset
        if isinstance(self.tool_selection_strategy, Unset):
            tool_selection_strategy = UNSET
        elif isinstance(self.tool_selection_strategy, AgenticExecutorParametersToolSelectionStrategyType0):
            tool_selection_strategy = self.tool_selection_strategy.value
        else:
            tool_selection_strategy = self.tool_selection_strategy

        tool_selections: list[str] | Unset = UNSET
        if not isinstance(self.tool_selections, Unset):
            tool_selections = self.tool_selections

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "prompt": prompt,
            }
        )
        if agent is not UNSET:
            field_dict["agent"] = agent
        if llm_model_id is not UNSET:
            field_dict["llm_model_id"] = llm_model_id
        if credential_id is not UNSET:
            field_dict["credential_id"] = credential_id
        if file_ids is not UNSET:
            field_dict["file_ids"] = file_ids
        if response_schema is not UNSET:
            field_dict["responseSchema"] = response_schema
        if integration_connections is not UNSET:
            field_dict["integration_connections"] = integration_connections
        if tool_selection_strategy is not UNSET:
            field_dict["tool_selection_strategy"] = tool_selection_strategy
        if tool_selections is not UNSET:
            field_dict["tool_selections"] = tool_selections

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.agentic_executor_parameters_response_schema_type_0 import (
            AgenticExecutorParametersResponseSchemaType0,
        )
        from ..models.integration_connection_config import IntegrationConnectionConfig

        d = dict(src_dict)
        prompt = d.pop("prompt")

        def _parse_agent(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        agent = _parse_agent(d.pop("agent", UNSET))

        def _parse_llm_model_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        llm_model_id = _parse_llm_model_id(d.pop("llm_model_id", UNSET))

        def _parse_credential_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        credential_id = _parse_credential_id(d.pop("credential_id", UNSET))

        file_ids = cast(list[str], d.pop("file_ids", UNSET))

        def _parse_response_schema(data: object) -> AgenticExecutorParametersResponseSchemaType0 | None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                response_schema_type_0 = AgenticExecutorParametersResponseSchemaType0.from_dict(data)

                return response_schema_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AgenticExecutorParametersResponseSchemaType0 | None | str | Unset, data)

        response_schema = _parse_response_schema(d.pop("responseSchema", UNSET))

        def _parse_integration_connections(data: object) -> list[IntegrationConnectionConfig] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                integration_connections_type_0 = []
                _integration_connections_type_0 = data
                for integration_connections_type_0_item_data in _integration_connections_type_0:
                    integration_connections_type_0_item = IntegrationConnectionConfig.from_dict(
                        integration_connections_type_0_item_data
                    )

                    integration_connections_type_0.append(integration_connections_type_0_item)

                return integration_connections_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[IntegrationConnectionConfig] | None | Unset, data)

        integration_connections = _parse_integration_connections(d.pop("integration_connections", UNSET))

        def _parse_tool_selection_strategy(
            data: object,
        ) -> AgenticExecutorParametersToolSelectionStrategyType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                tool_selection_strategy_type_0 = AgenticExecutorParametersToolSelectionStrategyType0(data)

                return tool_selection_strategy_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AgenticExecutorParametersToolSelectionStrategyType0 | None | Unset, data)

        tool_selection_strategy = _parse_tool_selection_strategy(d.pop("tool_selection_strategy", UNSET))

        tool_selections = cast(list[str], d.pop("tool_selections", UNSET))

        agentic_executor_parameters = cls(
            prompt=prompt,
            agent=agent,
            llm_model_id=llm_model_id,
            credential_id=credential_id,
            file_ids=file_ids,
            response_schema=response_schema,
            integration_connections=integration_connections,
            tool_selection_strategy=tool_selection_strategy,
            tool_selections=tool_selections,
        )

        agentic_executor_parameters.additional_properties = d
        return agentic_executor_parameters

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
