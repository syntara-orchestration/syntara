from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from dateutil.parser import isoparse

from ..models.integration_refresh_status import IntegrationRefreshStatus
from ..models.integration_scope import IntegrationScope
from ..models.integration_status import IntegrationStatus
from ..models.integration_type import IntegrationType
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.aap_configuration import AAPConfiguration
    from ..models.integration_read_labels import IntegrationReadLabels
    from ..models.llm_provider_configuration import LLMProviderConfiguration
    from ..models.mcp_server_configuration_input import MCPServerConfigurationInput
    from ..models.user_reference import UserReference


T = TypeVar("T", bound="IntegrationRead")


@_attrs_define
class IntegrationRead:
    """Schema for integration API responses.

    Attributes:
        name (str): Human-readable name for the resource Example: Authentication Service.
        integration_type (IntegrationType): Type of external integration.
        configuration (AAPConfiguration | LLMProviderConfiguration | MCPServerConfigurationInput): Integration-specific
            configuration
        id (UUID | Unset): Unique identifier for the resource Example: 550e8400-e29b-41d4-a716-446655440000.
        created_at (datetime.datetime | Unset): Timestamp when resource was created Example: 2025-10-09T12:00:00Z.
        updated_at (datetime.datetime | Unset): Timestamp when resource was last updated Example: 2025-10-09T12:30:00Z.
        labels (IntegrationReadLabels | Unset): Key-value pairs for resource labeling and filtering Example:
            {'environment': 'production', 'region': 'us-east-1', 'team': 'platform'}.
        description (None | str | Unset): Detailed description of the resource Example: Handles user authentication and
            authorization workflows.
        created_by (None | Unset | UserReference): User who created the integration
        updated_by (None | Unset | UserReference): User who last modified the integration
        enabled (bool | Unset):  Default: True.
        validation_status (IntegrationStatus | Unset): Validation status of an integration.
        scope (IntegrationScope | Unset): Visibility scope of an integration.
        last_validated_at (datetime.datetime | None | Unset):
        management_credential_id (None | Unset | UUID):
        validation_error (None | str | Unset):
        refresh_status (IntegrationRefreshStatus | None | Unset):
        last_refreshed_at (datetime.datetime | None | Unset):
        last_successful_refresh_at (datetime.datetime | None | Unset):
        refresh_error (None | str | Unset):
        project_ids (list[UUID] | Unset): IDs of projects this integration is assigned to (empty for global scope)
        total_tool_count (int | Unset): Total number of tools linked to this integration Default: 0.
        enabled_tool_count (int | Unset): Number of enabled tools linked to this integration Default: 0.
        total_model_count (int | Unset): Total number of models linked to this integration Default: 0.
        enabled_model_count (int | Unset): Number of enabled models linked to this integration Default: 0.
    """

    name: str
    integration_type: IntegrationType
    configuration: AAPConfiguration | LLMProviderConfiguration | MCPServerConfigurationInput
    id: UUID | Unset = UNSET
    created_at: datetime.datetime | Unset = UNSET
    updated_at: datetime.datetime | Unset = UNSET
    labels: IntegrationReadLabels | Unset = UNSET
    description: None | str | Unset = UNSET
    created_by: None | Unset | UserReference = UNSET
    updated_by: None | Unset | UserReference = UNSET
    enabled: bool | Unset = True
    validation_status: IntegrationStatus | Unset = UNSET
    scope: IntegrationScope | Unset = UNSET
    last_validated_at: datetime.datetime | None | Unset = UNSET
    management_credential_id: None | Unset | UUID = UNSET
    validation_error: None | str | Unset = UNSET
    refresh_status: IntegrationRefreshStatus | None | Unset = UNSET
    last_refreshed_at: datetime.datetime | None | Unset = UNSET
    last_successful_refresh_at: datetime.datetime | None | Unset = UNSET
    refresh_error: None | str | Unset = UNSET
    project_ids: list[UUID] | Unset = UNSET
    total_tool_count: int | Unset = 0
    enabled_tool_count: int | Unset = 0
    total_model_count: int | Unset = 0
    enabled_model_count: int | Unset = 0

    def to_dict(self) -> dict[str, Any]:
        from ..models.llm_provider_configuration import LLMProviderConfiguration
        from ..models.mcp_server_configuration_input import MCPServerConfigurationInput
        from ..models.user_reference import UserReference

        name = self.name

        integration_type = self.integration_type.value

        configuration: dict[str, Any]
        if isinstance(self.configuration, MCPServerConfigurationInput):
            configuration = self.configuration.to_dict()
        elif isinstance(self.configuration, LLMProviderConfiguration):
            configuration = self.configuration.to_dict()
        else:
            configuration = self.configuration.to_dict()

        id: str | Unset = UNSET
        if not isinstance(self.id, Unset):
            id = str(self.id)

        created_at: str | Unset = UNSET
        if not isinstance(self.created_at, Unset):
            created_at = self.created_at.isoformat()

        updated_at: str | Unset = UNSET
        if not isinstance(self.updated_at, Unset):
            updated_at = self.updated_at.isoformat()

        labels: dict[str, Any] | Unset = UNSET
        if not isinstance(self.labels, Unset):
            labels = self.labels.to_dict()

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        created_by: dict[str, Any] | None | Unset
        if isinstance(self.created_by, Unset):
            created_by = UNSET
        elif isinstance(self.created_by, UserReference):
            created_by = self.created_by.to_dict()
        else:
            created_by = self.created_by

        updated_by: dict[str, Any] | None | Unset
        if isinstance(self.updated_by, Unset):
            updated_by = UNSET
        elif isinstance(self.updated_by, UserReference):
            updated_by = self.updated_by.to_dict()
        else:
            updated_by = self.updated_by

        enabled = self.enabled

        validation_status: str | Unset = UNSET
        if not isinstance(self.validation_status, Unset):
            validation_status = self.validation_status.value

        scope: str | Unset = UNSET
        if not isinstance(self.scope, Unset):
            scope = self.scope.value

        last_validated_at: None | str | Unset
        if isinstance(self.last_validated_at, Unset):
            last_validated_at = UNSET
        elif isinstance(self.last_validated_at, datetime.datetime):
            last_validated_at = self.last_validated_at.isoformat()
        else:
            last_validated_at = self.last_validated_at

        management_credential_id: None | str | Unset
        if isinstance(self.management_credential_id, Unset):
            management_credential_id = UNSET
        elif isinstance(self.management_credential_id, UUID):
            management_credential_id = str(self.management_credential_id)
        else:
            management_credential_id = self.management_credential_id

        validation_error: None | str | Unset
        if isinstance(self.validation_error, Unset):
            validation_error = UNSET
        else:
            validation_error = self.validation_error

        refresh_status: None | str | Unset
        if isinstance(self.refresh_status, Unset):
            refresh_status = UNSET
        elif isinstance(self.refresh_status, IntegrationRefreshStatus):
            refresh_status = self.refresh_status.value
        else:
            refresh_status = self.refresh_status

        last_refreshed_at: None | str | Unset
        if isinstance(self.last_refreshed_at, Unset):
            last_refreshed_at = UNSET
        elif isinstance(self.last_refreshed_at, datetime.datetime):
            last_refreshed_at = self.last_refreshed_at.isoformat()
        else:
            last_refreshed_at = self.last_refreshed_at

        last_successful_refresh_at: None | str | Unset
        if isinstance(self.last_successful_refresh_at, Unset):
            last_successful_refresh_at = UNSET
        elif isinstance(self.last_successful_refresh_at, datetime.datetime):
            last_successful_refresh_at = self.last_successful_refresh_at.isoformat()
        else:
            last_successful_refresh_at = self.last_successful_refresh_at

        refresh_error: None | str | Unset
        if isinstance(self.refresh_error, Unset):
            refresh_error = UNSET
        else:
            refresh_error = self.refresh_error

        project_ids: list[str] | Unset = UNSET
        if not isinstance(self.project_ids, Unset):
            project_ids = []
            for project_ids_item_data in self.project_ids:
                project_ids_item = str(project_ids_item_data)
                project_ids.append(project_ids_item)

        total_tool_count = self.total_tool_count

        enabled_tool_count = self.enabled_tool_count

        total_model_count = self.total_model_count

        enabled_model_count = self.enabled_model_count

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "name": name,
                "integration_type": integration_type,
                "configuration": configuration,
            }
        )
        if id is not UNSET:
            field_dict["id"] = id
        if created_at is not UNSET:
            field_dict["created_at"] = created_at
        if updated_at is not UNSET:
            field_dict["updated_at"] = updated_at
        if labels is not UNSET:
            field_dict["labels"] = labels
        if description is not UNSET:
            field_dict["description"] = description
        if created_by is not UNSET:
            field_dict["created_by"] = created_by
        if updated_by is not UNSET:
            field_dict["updated_by"] = updated_by
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if validation_status is not UNSET:
            field_dict["validation_status"] = validation_status
        if scope is not UNSET:
            field_dict["scope"] = scope
        if last_validated_at is not UNSET:
            field_dict["last_validated_at"] = last_validated_at
        if management_credential_id is not UNSET:
            field_dict["management_credential_id"] = management_credential_id
        if validation_error is not UNSET:
            field_dict["validation_error"] = validation_error
        if refresh_status is not UNSET:
            field_dict["refresh_status"] = refresh_status
        if last_refreshed_at is not UNSET:
            field_dict["last_refreshed_at"] = last_refreshed_at
        if last_successful_refresh_at is not UNSET:
            field_dict["last_successful_refresh_at"] = last_successful_refresh_at
        if refresh_error is not UNSET:
            field_dict["refresh_error"] = refresh_error
        if project_ids is not UNSET:
            field_dict["project_ids"] = project_ids
        if total_tool_count is not UNSET:
            field_dict["total_tool_count"] = total_tool_count
        if enabled_tool_count is not UNSET:
            field_dict["enabled_tool_count"] = enabled_tool_count
        if total_model_count is not UNSET:
            field_dict["total_model_count"] = total_model_count
        if enabled_model_count is not UNSET:
            field_dict["enabled_model_count"] = enabled_model_count

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.aap_configuration import AAPConfiguration
        from ..models.integration_read_labels import IntegrationReadLabels
        from ..models.llm_provider_configuration import LLMProviderConfiguration
        from ..models.mcp_server_configuration_input import MCPServerConfigurationInput
        from ..models.user_reference import UserReference

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

        _id = d.pop("id", UNSET)
        id: UUID | Unset
        if isinstance(_id, Unset):
            id = UNSET
        else:
            id = UUID(_id)

        _created_at = d.pop("created_at", UNSET)
        created_at: datetime.datetime | Unset
        if isinstance(_created_at, Unset):
            created_at = UNSET
        else:
            created_at = isoparse(_created_at)

        _updated_at = d.pop("updated_at", UNSET)
        updated_at: datetime.datetime | Unset
        if isinstance(_updated_at, Unset):
            updated_at = UNSET
        else:
            updated_at = isoparse(_updated_at)

        _labels = d.pop("labels", UNSET)
        labels: IntegrationReadLabels | Unset
        if isinstance(_labels, Unset):
            labels = UNSET
        else:
            labels = IntegrationReadLabels.from_dict(_labels)

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        def _parse_created_by(data: object) -> None | Unset | UserReference:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                created_by_type_0 = UserReference.from_dict(data)

                return created_by_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UserReference, data)

        created_by = _parse_created_by(d.pop("created_by", UNSET))

        def _parse_updated_by(data: object) -> None | Unset | UserReference:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                updated_by_type_0 = UserReference.from_dict(data)

                return updated_by_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UserReference, data)

        updated_by = _parse_updated_by(d.pop("updated_by", UNSET))

        enabled = d.pop("enabled", UNSET)

        _validation_status = d.pop("validation_status", UNSET)
        validation_status: IntegrationStatus | Unset
        if isinstance(_validation_status, Unset):
            validation_status = UNSET
        else:
            validation_status = IntegrationStatus(_validation_status)

        _scope = d.pop("scope", UNSET)
        scope: IntegrationScope | Unset
        if isinstance(_scope, Unset):
            scope = UNSET
        else:
            scope = IntegrationScope(_scope)

        def _parse_last_validated_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_validated_at_type_0 = isoparse(data)

                return last_validated_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        last_validated_at = _parse_last_validated_at(d.pop("last_validated_at", UNSET))

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

        def _parse_validation_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        validation_error = _parse_validation_error(d.pop("validation_error", UNSET))

        def _parse_refresh_status(data: object) -> IntegrationRefreshStatus | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                refresh_status_type_0 = IntegrationRefreshStatus(data)

                return refresh_status_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(IntegrationRefreshStatus | None | Unset, data)

        refresh_status = _parse_refresh_status(d.pop("refresh_status", UNSET))

        def _parse_last_refreshed_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_refreshed_at_type_0 = isoparse(data)

                return last_refreshed_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        last_refreshed_at = _parse_last_refreshed_at(d.pop("last_refreshed_at", UNSET))

        def _parse_last_successful_refresh_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_successful_refresh_at_type_0 = isoparse(data)

                return last_successful_refresh_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        last_successful_refresh_at = _parse_last_successful_refresh_at(d.pop("last_successful_refresh_at", UNSET))

        def _parse_refresh_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        refresh_error = _parse_refresh_error(d.pop("refresh_error", UNSET))

        _project_ids = d.pop("project_ids", UNSET)
        project_ids: list[UUID] | Unset = UNSET
        if _project_ids is not UNSET:
            project_ids = []
            for project_ids_item_data in _project_ids:
                project_ids_item = UUID(project_ids_item_data)

                project_ids.append(project_ids_item)

        total_tool_count = d.pop("total_tool_count", UNSET)

        enabled_tool_count = d.pop("enabled_tool_count", UNSET)

        total_model_count = d.pop("total_model_count", UNSET)

        enabled_model_count = d.pop("enabled_model_count", UNSET)

        integration_read = cls(
            name=name,
            integration_type=integration_type,
            configuration=configuration,
            id=id,
            created_at=created_at,
            updated_at=updated_at,
            labels=labels,
            description=description,
            created_by=created_by,
            updated_by=updated_by,
            enabled=enabled,
            validation_status=validation_status,
            scope=scope,
            last_validated_at=last_validated_at,
            management_credential_id=management_credential_id,
            validation_error=validation_error,
            refresh_status=refresh_status,
            last_refreshed_at=last_refreshed_at,
            last_successful_refresh_at=last_successful_refresh_at,
            refresh_error=refresh_error,
            project_ids=project_ids,
            total_tool_count=total_tool_count,
            enabled_tool_count=enabled_tool_count,
            total_model_count=total_model_count,
            enabled_model_count=enabled_model_count,
        )

        return integration_read
