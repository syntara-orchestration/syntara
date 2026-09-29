from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from dateutil.parser import isoparse

from ..models.form_prompt_status import FormPromptStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.form_definition import FormDefinition
    from ..models.form_prompt_read_labels import FormPromptReadLabels
    from ..models.form_prompt_read_response_data_type_0 import FormPromptReadResponseDataType0
    from ..models.responder_group_summary import ResponderGroupSummary
    from ..models.responder_user_summary import ResponderUserSummary
    from ..models.user_reference import UserReference


T = TypeVar("T", bound="FormPromptRead")


@_attrs_define
class FormPromptRead:
    """FormPrompt API response model with typed nested fields.

    Overrides the JSONB dict fields from BaseFormPrompt with typed models
    so API consumers get proper validation and type safety. Pydantic coerces
    the raw dicts from the database into these typed models during serialization.

        Attributes:
            project_id (UUID): Project this form prompt belongs to
            name (str): Human-readable name for the form prompt
            execution_id (UUID): Parent execution ID
            prompt_node_id (str): Canvas node ID from the workflow definition
            form_definition (FormDefinition): Complete form definition with fields and metadata.
            id (UUID | Unset): Unique identifier for the resource Example: 550e8400-e29b-41d4-a716-446655440000.
            created_at (datetime.datetime | Unset): Timestamp when resource was created Example: 2025-10-09T12:00:00Z.
            updated_at (datetime.datetime | Unset): Timestamp when resource was last updated Example: 2025-10-09T12:30:00Z.
            labels (FormPromptReadLabels | Unset): Key-value pairs for resource labeling and filtering Example:
                {'environment': 'production', 'region': 'us-east-1', 'team': 'platform'}.
            message (None | str | Unset): Resolved guidance message shown to responders
            loop_iteration_path (list[int] | Unset): Enclosing-loop indices, outermost first (empty when not inside a loop)
            status (FormPromptStatus | Unset): Form prompt status enumeration.
            notes (None | str | Unset): Optional notes explaining the last status change (e.g., reason for cancellation)
            timeout_at (datetime.datetime | None | Unset): When this prompt expires
            submit_label (None | str | Unset): Submit button label shown to the responder
            success_message (None | str | Unset): Message shown after successful form submission
            timezone (None | str | Unset): IANA timezone name for interpreting date/datetime field values
            css_override (None | str | Unset): Custom CSS applied to the form view
            response_data (FormPromptReadResponseDataType0 | None | Unset): Submitted form values
            responded_at (datetime.datetime | None | Unset): When response was submitted
            responder_users (list[ResponderUserSummary] | Unset): Users who can respond to this prompt (empty = any user
                with permission)
            responder_groups (list[ResponderGroupSummary] | Unset): Groups whose members can respond to this prompt
            responded_by (None | Unset | UserReference): User who submitted the response
            signal_delivery_error (None | str | Unset): Error if the workflow signal failed after a response. Only present
                in the respond response; null on subsequent reads.
    """

    project_id: UUID
    name: str
    execution_id: UUID
    prompt_node_id: str
    form_definition: FormDefinition
    id: UUID | Unset = UNSET
    created_at: datetime.datetime | Unset = UNSET
    updated_at: datetime.datetime | Unset = UNSET
    labels: FormPromptReadLabels | Unset = UNSET
    message: None | str | Unset = UNSET
    loop_iteration_path: list[int] | Unset = UNSET
    status: FormPromptStatus | Unset = UNSET
    notes: None | str | Unset = UNSET
    timeout_at: datetime.datetime | None | Unset = UNSET
    submit_label: None | str | Unset = UNSET
    success_message: None | str | Unset = UNSET
    timezone: None | str | Unset = UNSET
    css_override: None | str | Unset = UNSET
    response_data: FormPromptReadResponseDataType0 | None | Unset = UNSET
    responded_at: datetime.datetime | None | Unset = UNSET
    responder_users: list[ResponderUserSummary] | Unset = UNSET
    responder_groups: list[ResponderGroupSummary] | Unset = UNSET
    responded_by: None | Unset | UserReference = UNSET
    signal_delivery_error: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.form_prompt_read_response_data_type_0 import FormPromptReadResponseDataType0
        from ..models.user_reference import UserReference

        project_id = str(self.project_id)

        name = self.name

        execution_id = str(self.execution_id)

        prompt_node_id = self.prompt_node_id

        form_definition = self.form_definition.to_dict()

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

        message: None | str | Unset
        if isinstance(self.message, Unset):
            message = UNSET
        else:
            message = self.message

        loop_iteration_path: list[int] | Unset = UNSET
        if not isinstance(self.loop_iteration_path, Unset):
            loop_iteration_path = self.loop_iteration_path

        status: str | Unset = UNSET
        if not isinstance(self.status, Unset):
            status = self.status.value

        notes: None | str | Unset
        if isinstance(self.notes, Unset):
            notes = UNSET
        else:
            notes = self.notes

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

        response_data: dict[str, Any] | None | Unset
        if isinstance(self.response_data, Unset):
            response_data = UNSET
        elif isinstance(self.response_data, FormPromptReadResponseDataType0):
            response_data = self.response_data.to_dict()
        else:
            response_data = self.response_data

        responded_at: None | str | Unset
        if isinstance(self.responded_at, Unset):
            responded_at = UNSET
        elif isinstance(self.responded_at, datetime.datetime):
            responded_at = self.responded_at.isoformat()
        else:
            responded_at = self.responded_at

        responder_users: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.responder_users, Unset):
            responder_users = []
            for responder_users_item_data in self.responder_users:
                responder_users_item = responder_users_item_data.to_dict()
                responder_users.append(responder_users_item)

        responder_groups: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.responder_groups, Unset):
            responder_groups = []
            for responder_groups_item_data in self.responder_groups:
                responder_groups_item = responder_groups_item_data.to_dict()
                responder_groups.append(responder_groups_item)

        responded_by: dict[str, Any] | None | Unset
        if isinstance(self.responded_by, Unset):
            responded_by = UNSET
        elif isinstance(self.responded_by, UserReference):
            responded_by = self.responded_by.to_dict()
        else:
            responded_by = self.responded_by

        signal_delivery_error: None | str | Unset
        if isinstance(self.signal_delivery_error, Unset):
            signal_delivery_error = UNSET
        else:
            signal_delivery_error = self.signal_delivery_error

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "project_id": project_id,
                "name": name,
                "execution_id": execution_id,
                "prompt_node_id": prompt_node_id,
                "form_definition": form_definition,
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
        if message is not UNSET:
            field_dict["message"] = message
        if loop_iteration_path is not UNSET:
            field_dict["loop_iteration_path"] = loop_iteration_path
        if status is not UNSET:
            field_dict["status"] = status
        if notes is not UNSET:
            field_dict["notes"] = notes
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
        if response_data is not UNSET:
            field_dict["response_data"] = response_data
        if responded_at is not UNSET:
            field_dict["responded_at"] = responded_at
        if responder_users is not UNSET:
            field_dict["responder_users"] = responder_users
        if responder_groups is not UNSET:
            field_dict["responder_groups"] = responder_groups
        if responded_by is not UNSET:
            field_dict["responded_by"] = responded_by
        if signal_delivery_error is not UNSET:
            field_dict["signal_delivery_error"] = signal_delivery_error

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.form_definition import FormDefinition
        from ..models.form_prompt_read_labels import FormPromptReadLabels
        from ..models.form_prompt_read_response_data_type_0 import FormPromptReadResponseDataType0
        from ..models.responder_group_summary import ResponderGroupSummary
        from ..models.responder_user_summary import ResponderUserSummary
        from ..models.user_reference import UserReference

        d = dict(src_dict)
        project_id = UUID(d.pop("project_id"))

        name = d.pop("name")

        execution_id = UUID(d.pop("execution_id"))

        prompt_node_id = d.pop("prompt_node_id")

        form_definition = FormDefinition.from_dict(d.pop("form_definition"))

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
        labels: FormPromptReadLabels | Unset
        if isinstance(_labels, Unset):
            labels = UNSET
        else:
            labels = FormPromptReadLabels.from_dict(_labels)

        def _parse_message(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        message = _parse_message(d.pop("message", UNSET))

        loop_iteration_path = cast(list[int], d.pop("loop_iteration_path", UNSET))

        _status = d.pop("status", UNSET)
        status: FormPromptStatus | Unset
        if isinstance(_status, Unset):
            status = UNSET
        else:
            status = FormPromptStatus(_status)

        def _parse_notes(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        notes = _parse_notes(d.pop("notes", UNSET))

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

        def _parse_response_data(data: object) -> FormPromptReadResponseDataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                response_data_type_0 = FormPromptReadResponseDataType0.from_dict(data)

                return response_data_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(FormPromptReadResponseDataType0 | None | Unset, data)

        response_data = _parse_response_data(d.pop("response_data", UNSET))

        def _parse_responded_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                responded_at_type_0 = isoparse(data)

                return responded_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        responded_at = _parse_responded_at(d.pop("responded_at", UNSET))

        _responder_users = d.pop("responder_users", UNSET)
        responder_users: list[ResponderUserSummary] | Unset = UNSET
        if _responder_users is not UNSET:
            responder_users = []
            for responder_users_item_data in _responder_users:
                responder_users_item = ResponderUserSummary.from_dict(responder_users_item_data)

                responder_users.append(responder_users_item)

        _responder_groups = d.pop("responder_groups", UNSET)
        responder_groups: list[ResponderGroupSummary] | Unset = UNSET
        if _responder_groups is not UNSET:
            responder_groups = []
            for responder_groups_item_data in _responder_groups:
                responder_groups_item = ResponderGroupSummary.from_dict(responder_groups_item_data)

                responder_groups.append(responder_groups_item)

        def _parse_responded_by(data: object) -> None | Unset | UserReference:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                responded_by_type_0 = UserReference.from_dict(data)

                return responded_by_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UserReference, data)

        responded_by = _parse_responded_by(d.pop("responded_by", UNSET))

        def _parse_signal_delivery_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        signal_delivery_error = _parse_signal_delivery_error(d.pop("signal_delivery_error", UNSET))

        form_prompt_read = cls(
            project_id=project_id,
            name=name,
            execution_id=execution_id,
            prompt_node_id=prompt_node_id,
            form_definition=form_definition,
            id=id,
            created_at=created_at,
            updated_at=updated_at,
            labels=labels,
            message=message,
            loop_iteration_path=loop_iteration_path,
            status=status,
            notes=notes,
            timeout_at=timeout_at,
            submit_label=submit_label,
            success_message=success_message,
            timezone=timezone,
            css_override=css_override,
            response_data=response_data,
            responded_at=responded_at,
            responder_users=responder_users,
            responder_groups=responder_groups,
            responded_by=responded_by,
            signal_delivery_error=signal_delivery_error,
        )

        return form_prompt_read
