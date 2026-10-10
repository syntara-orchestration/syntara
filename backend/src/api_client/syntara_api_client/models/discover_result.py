from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from dateutil.parser import isoparse

from ..models.health_check_error_type import HealthCheckErrorType
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.discovered_llm_model import DiscoveredLLMModel
    from ..models.discovered_tool import DiscoveredTool


T = TypeVar("T", bound="DiscoverResult")


@_attrs_define
class DiscoverResult:
    """Result of a resource-discovery operation (discover endpoint).

    Returned by the unsaved-connection test (POST /integrations/discover)
    and used internally by refresh_resources() to drive tool sync.

        Attributes:
            success (bool):
            checked_at (datetime.datetime):
            error (None | str | Unset):
            error_type (HealthCheckErrorType | None | Unset):
            discovered_tools (list[DiscoveredTool] | None | Unset):
            discovered_models (list[DiscoveredLLMModel] | None | Unset):
    """

    success: bool
    checked_at: datetime.datetime
    error: None | str | Unset = UNSET
    error_type: HealthCheckErrorType | None | Unset = UNSET
    discovered_tools: list[DiscoveredTool] | None | Unset = UNSET
    discovered_models: list[DiscoveredLLMModel] | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        success = self.success

        checked_at = self.checked_at.isoformat()

        error: None | str | Unset
        if isinstance(self.error, Unset):
            error = UNSET
        else:
            error = self.error

        error_type: None | str | Unset
        if isinstance(self.error_type, Unset):
            error_type = UNSET
        elif isinstance(self.error_type, HealthCheckErrorType):
            error_type = self.error_type.value
        else:
            error_type = self.error_type

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
                "success": success,
                "checked_at": checked_at,
            }
        )
        if error is not UNSET:
            field_dict["error"] = error
        if error_type is not UNSET:
            field_dict["error_type"] = error_type
        if discovered_tools is not UNSET:
            field_dict["discovered_tools"] = discovered_tools
        if discovered_models is not UNSET:
            field_dict["discovered_models"] = discovered_models

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.discovered_llm_model import DiscoveredLLMModel
        from ..models.discovered_tool import DiscoveredTool

        d = dict(src_dict)
        success = d.pop("success")

        checked_at = isoparse(d.pop("checked_at"))

        def _parse_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error = _parse_error(d.pop("error", UNSET))

        def _parse_error_type(data: object) -> HealthCheckErrorType | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                error_type_type_0 = HealthCheckErrorType(data)

                return error_type_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(HealthCheckErrorType | None | Unset, data)

        error_type = _parse_error_type(d.pop("error_type", UNSET))

        def _parse_discovered_tools(data: object) -> list[DiscoveredTool] | None | Unset:
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
                    discovered_tools_type_0_item = DiscoveredTool.from_dict(discovered_tools_type_0_item_data)

                    discovered_tools_type_0.append(discovered_tools_type_0_item)

                return discovered_tools_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[DiscoveredTool] | None | Unset, data)

        discovered_tools = _parse_discovered_tools(d.pop("discovered_tools", UNSET))

        def _parse_discovered_models(data: object) -> list[DiscoveredLLMModel] | None | Unset:
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
                    discovered_models_type_0_item = DiscoveredLLMModel.from_dict(discovered_models_type_0_item_data)

                    discovered_models_type_0.append(discovered_models_type_0_item)

                return discovered_models_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[DiscoveredLLMModel] | None | Unset, data)

        discovered_models = _parse_discovered_models(d.pop("discovered_models", UNSET))

        discover_result = cls(
            success=success,
            checked_at=checked_at,
            error=error,
            error_type=error_type,
            discovered_tools=discovered_tools,
            discovered_models=discovered_models,
        )

        return discover_result
