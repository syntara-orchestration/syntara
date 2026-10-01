from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.form_definition import FormDefinition


T = TypeVar("T", bound="FormPromptCreateRequest")


@_attrs_define
class FormPromptCreateRequest:
    """Request payload for creating a form prompt.

    This is an internal schema used by the Workflows component.

        Attributes:
            execution_id (UUID): Parent workflow execution ID
            project_id (UUID): Project ID (denormalized from execution)
            prompt_node_id (str): Canvas node ID from the workflow definition
            name (str): Display name for the form prompt
            temporal_activity_id (str): Temporal activity ID to signal on submit
            form_definition (FormDefinition): Complete form definition with fields and metadata.
            message (None | str | Unset): Resolved message shown above the form
            loop_iteration_path (list[int] | Unset): Enclosing-loop indices, outermost first (empty when not inside a loop)
            timeout_at (datetime.datetime | None | Unset): When this prompt expires (null = no timeout)
            submit_label (None | str | Unset): Submit button label
            success_message (None | str | Unset): Success message after submit
            timezone (None | str | Unset): IANA timezone for date fields
            css_override (None | str | Unset): Custom CSS for form rendering
            responder_user_ids (list[UUID] | None | Unset): User IDs who can respond (null = any user with
                form_prompt:submit permission)
            responder_group_ids (list[UUID] | None | Unset): Group IDs whose members can respond
    """

    execution_id: UUID
    project_id: UUID
    prompt_node_id: str
    name: str
    temporal_activity_id: str
    form_definition: FormDefinition
    message: None | str | Unset = UNSET
    loop_iteration_path: list[int] | Unset = UNSET
    timeout_at: datetime.datetime | None | Unset = UNSET
    submit_label: None | str | Unset = UNSET
    success_message: None | str | Unset = UNSET
    timezone: None | str | Unset = UNSET
    css_override: None | str | Unset = UNSET
    responder_user_ids: list[UUID] | None | Unset = UNSET
    responder_group_ids: list[UUID] | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        execution_id = str(self.execution_id)

        project_id = str(self.project_id)

        prompt_node_id = self.prompt_node_id

        name = self.name

        temporal_activity_id = self.temporal_activity_id

        form_definition = self.form_definition.to_dict()

        message: None | str | Unset
        if isinstance(self.message, Unset):
            message = UNSET
        else:
            message = self.message

        loop_iteration_path: list[int] | Unset = UNSET
        if not isinstance(self.loop_iteration_path, Unset):
            loop_iteration_path = self.loop_iteration_path

        timeout_at: None | str | Unset
        if isinstance(self.timeout_at, Unset):
            timeout_at = UNSET
        elif isinstance(self.timeout_at, datetime.datetime):
            timeout_at = self.timeout_at.isoformat()
        else:
            timeout_at = self.timeout_at

        submit_label: None | str | Unset
        if isinstance(self.submit_label, Unset):
            submit_label = UNSET
        else:
            submit_label = self.submit_label

        success_message: None | str | Unset
        if isinstance(self.success_message, Unset):
            success_message = UNSET
        else:
            success_message = self.success_message

        timezone: None | str | Unset
        if isinstance(self.timezone, Unset):
            timezone = UNSET
        else:
            timezone = self.timezone

        css_override: None | str | Unset
        if isinstance(self.css_override, Unset):
            css_override = UNSET
        else:
            css_override = self.css_override

        responder_user_ids: list[str] | None | Unset
        if isinstance(self.responder_user_ids, Unset):
            responder_user_ids = UNSET
        elif isinstance(self.responder_user_ids, list):
            responder_user_ids = []
            for responder_user_ids_type_0_item_data in self.responder_user_ids:
                responder_user_ids_type_0_item = str(responder_user_ids_type_0_item_data)
                responder_user_ids.append(responder_user_ids_type_0_item)

        else:
            responder_user_ids = self.responder_user_ids

        responder_group_ids: list[str] | None | Unset
        if isinstance(self.responder_group_ids, Unset):
            responder_group_ids = UNSET
        elif isinstance(self.responder_group_ids, list):
            responder_group_ids = []
            for responder_group_ids_type_0_item_data in self.responder_group_ids:
                responder_group_ids_type_0_item = str(responder_group_ids_type_0_item_data)
                responder_group_ids.append(responder_group_ids_type_0_item)

        else:
            responder_group_ids = self.responder_group_ids

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "execution_id": execution_id,
                "project_id": project_id,
                "prompt_node_id": prompt_node_id,
                "name": name,
                "temporal_activity_id": temporal_activity_id,
                "form_definition": form_definition,
            }
        )
        if message is not UNSET:
            field_dict["message"] = message
        if loop_iteration_path is not UNSET:
            field_dict["loop_iteration_path"] = loop_iteration_path
        if timeout_at is not UNSET:
            field_dict["timeout_at"] = timeout_at
        if submit_label is not UNSET:
            field_dict["submit_label"] = submit_label
        if success_message is not UNSET:
            field_dict["success_message"] = success_message
        if timezone is not UNSET:
            field_dict["timezone"] = timezone
        if css_override is not UNSET:
            field_dict["css_override"] = css_override
        if responder_user_ids is not UNSET:
            field_dict["responder_user_ids"] = responder_user_ids
        if responder_group_ids is not UNSET:
            field_dict["responder_group_ids"] = responder_group_ids

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.form_definition import FormDefinition

        d = dict(src_dict)
        execution_id = UUID(d.pop("execution_id"))

        project_id = UUID(d.pop("project_id"))

        prompt_node_id = d.pop("prompt_node_id")

        name = d.pop("name")

        temporal_activity_id = d.pop("temporal_activity_id")

        form_definition = FormDefinition.from_dict(d.pop("form_definition"))

        def _parse_message(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        message = _parse_message(d.pop("message", UNSET))

        loop_iteration_path = cast(list[int], d.pop("loop_iteration_path", UNSET))

        def _parse_timeout_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                timeout_at_type_0 = isoparse(data)

                return timeout_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        timeout_at = _parse_timeout_at(d.pop("timeout_at", UNSET))

        def _parse_submit_label(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        submit_label = _parse_submit_label(d.pop("submit_label", UNSET))

        def _parse_success_message(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        success_message = _parse_success_message(d.pop("success_message", UNSET))

        def _parse_timezone(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        timezone = _parse_timezone(d.pop("timezone", UNSET))

        def _parse_css_override(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        css_override = _parse_css_override(d.pop("css_override", UNSET))

        def _parse_responder_user_ids(data: object) -> list[UUID] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                responder_user_ids_type_0 = []
                _responder_user_ids_type_0 = data
                for responder_user_ids_type_0_item_data in _responder_user_ids_type_0:
                    responder_user_ids_type_0_item = UUID(responder_user_ids_type_0_item_data)

                    responder_user_ids_type_0.append(responder_user_ids_type_0_item)

                return responder_user_ids_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[UUID] | None | Unset, data)

        responder_user_ids = _parse_responder_user_ids(d.pop("responder_user_ids", UNSET))

        def _parse_responder_group_ids(data: object) -> list[UUID] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                responder_group_ids_type_0 = []
                _responder_group_ids_type_0 = data
                for responder_group_ids_type_0_item_data in _responder_group_ids_type_0:
                    responder_group_ids_type_0_item = UUID(responder_group_ids_type_0_item_data)

                    responder_group_ids_type_0.append(responder_group_ids_type_0_item)

                return responder_group_ids_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[UUID] | None | Unset, data)

        responder_group_ids = _parse_responder_group_ids(d.pop("responder_group_ids", UNSET))

        form_prompt_create_request = cls(
            execution_id=execution_id,
            project_id=project_id,
            prompt_node_id=prompt_node_id,
            name=name,
            temporal_activity_id=temporal_activity_id,
            form_definition=form_definition,
            message=message,
            loop_iteration_path=loop_iteration_path,
            timeout_at=timeout_at,
            submit_label=submit_label,
            success_message=success_message,
            timezone=timezone,
            css_override=css_override,
            responder_user_ids=responder_user_ids,
            responder_group_ids=responder_group_ids,
        )

        form_prompt_create_request.additional_properties = d
        return form_prompt_create_request

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
