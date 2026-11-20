from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..models.form_prompt_node_parameters_fallback_decision_type_0 import FormPromptNodeParametersFallbackDecisionType0
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.form_prompt_definition import FormPromptDefinition
    from ..models.form_prompt_node_parameters_response_schema_type_0 import FormPromptNodeParametersResponseSchemaType0


T = TypeVar("T", bound="FormPromptNodeParameters")


@_attrs_define
class FormPromptNodeParameters:
    """Parameters for form prompt nodes.

    Attributes:
        form_definition (FormPromptDefinition): Authored form definition for a form prompt; resolved snapshots are
            engine-only.
        message (None | str | Unset): Message shown above the form. Supports ${...} template expressions.
        response_schema (FormPromptNodeParametersResponseSchemaType0 | None | Unset): Backend-generated JSON Schema for
            normalized response_data values.
        responder_users (list[str] | None | Unset): Usernames allowed to respond. Empty/omitted = any user with
            form_prompt:submit. If a configured list resolves to no users, the form-prompt node fails before creating a
            prompt.
        responder_groups (list[str] | None | Unset): Group names whose members may respond. Empty/omitted = any user
            with form_prompt:submit. If a configured list resolves to no groups, the form-prompt node fails before creating
            a prompt.
        response_window (int | None | Unset): Seconds the responder has before the prompt expires. Falls back to
            workflow_engine.form_prompt_response_window_seconds.
        fallback_decision (FormPromptNodeParametersFallbackDecisionType0 | None | Unset): Decision when form prompt
            times out with continue_on_failure enabled
        submit_label (None | str | Unset): Submit button label.
        success_message (None | str | Unset): Shown after submission.
    """

    form_definition: FormPromptDefinition
    message: None | str | Unset = UNSET
    response_schema: FormPromptNodeParametersResponseSchemaType0 | None | Unset = UNSET
    responder_users: list[str] | None | Unset = UNSET
    responder_groups: list[str] | None | Unset = UNSET
    response_window: int | None | Unset = UNSET
    fallback_decision: FormPromptNodeParametersFallbackDecisionType0 | None | Unset = UNSET
    submit_label: None | str | Unset = UNSET
    success_message: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.form_prompt_node_parameters_response_schema_type_0 import (
            FormPromptNodeParametersResponseSchemaType0,
        )

        form_definition = self.form_definition.to_dict()

        message: None | str | Unset
        if isinstance(self.message, Unset):
            message = UNSET
        else:
            message = self.message

        response_schema: dict[str, Any] | None | Unset
        if isinstance(self.response_schema, Unset):
            response_schema = UNSET
        elif isinstance(self.response_schema, FormPromptNodeParametersResponseSchemaType0):
            response_schema = self.response_schema.to_dict()
        else:
            response_schema = self.response_schema

        responder_users: list[str] | None | Unset
        if isinstance(self.responder_users, Unset):
            responder_users = UNSET
        elif isinstance(self.responder_users, list):
            responder_users = self.responder_users

        else:
            responder_users = self.responder_users

        responder_groups: list[str] | None | Unset
        if isinstance(self.responder_groups, Unset):
            responder_groups = UNSET
        elif isinstance(self.responder_groups, list):
            responder_groups = self.responder_groups

        else:
            responder_groups = self.responder_groups

        response_window: int | None | Unset
        if isinstance(self.response_window, Unset):
            response_window = UNSET
        else:
            response_window = self.response_window

        fallback_decision: None | str | Unset
        if isinstance(self.fallback_decision, Unset):
            fallback_decision = UNSET
        elif isinstance(self.fallback_decision, FormPromptNodeParametersFallbackDecisionType0):
            fallback_decision = self.fallback_decision.value
        else:
            fallback_decision = self.fallback_decision

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

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "form_definition": form_definition,
            }
        )
        if message is not UNSET:
            field_dict["message"] = message
        if response_schema is not UNSET:
            field_dict["response_schema"] = response_schema
        if responder_users is not UNSET:
            field_dict["responder_users"] = responder_users
        if responder_groups is not UNSET:
            field_dict["responder_groups"] = responder_groups
        if response_window is not UNSET:
            field_dict["response_window"] = response_window
        if fallback_decision is not UNSET:
            field_dict["fallback_decision"] = fallback_decision
        if submit_label is not UNSET:
            field_dict["submit_label"] = submit_label
        if success_message is not UNSET:
            field_dict["success_message"] = success_message

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.form_prompt_definition import FormPromptDefinition
        from ..models.form_prompt_node_parameters_response_schema_type_0 import (
            FormPromptNodeParametersResponseSchemaType0,
        )

        d = dict(src_dict)
        form_definition = FormPromptDefinition.from_dict(d.pop("form_definition"))

        def _parse_message(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        message = _parse_message(d.pop("message", UNSET))

        def _parse_response_schema(data: object) -> FormPromptNodeParametersResponseSchemaType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                response_schema_type_0 = FormPromptNodeParametersResponseSchemaType0.from_dict(data)

                return response_schema_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(FormPromptNodeParametersResponseSchemaType0 | None | Unset, data)

        response_schema = _parse_response_schema(d.pop("response_schema", UNSET))

        def _parse_responder_users(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                responder_users_type_0 = cast(list[str], data)

                return responder_users_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        responder_users = _parse_responder_users(d.pop("responder_users", UNSET))

        def _parse_responder_groups(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                responder_groups_type_0 = cast(list[str], data)

                return responder_groups_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        responder_groups = _parse_responder_groups(d.pop("responder_groups", UNSET))

        def _parse_response_window(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        response_window = _parse_response_window(d.pop("response_window", UNSET))

        def _parse_fallback_decision(data: object) -> FormPromptNodeParametersFallbackDecisionType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                fallback_decision_type_0 = FormPromptNodeParametersFallbackDecisionType0(data)

                return fallback_decision_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(FormPromptNodeParametersFallbackDecisionType0 | None | Unset, data)

        fallback_decision = _parse_fallback_decision(d.pop("fallback_decision", UNSET))

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

        form_prompt_node_parameters = cls(
            form_definition=form_definition,
            message=message,
            response_schema=response_schema,
            responder_users=responder_users,
            responder_groups=responder_groups,
            response_window=response_window,
            fallback_decision=fallback_decision,
            submit_label=submit_label,
            success_message=success_message,
        )

        return form_prompt_node_parameters
