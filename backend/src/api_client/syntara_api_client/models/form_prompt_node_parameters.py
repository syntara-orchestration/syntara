from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..models.form_prompt_node_parameters_fallback_behavior import FormPromptNodeParametersFallbackBehavior
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.form_definition import FormDefinition


T = TypeVar("T", bound="FormPromptNodeParameters")


@_attrs_define
class FormPromptNodeParameters:
    """Parameters for form prompt nodes.

    Attributes:
        form_definition (FormDefinition): Complete form definition with fields and metadata.
        message (None | str | Unset): Message shown above the form. Supports ${...} template expressions.
        responder_users (list[str] | None | Unset): Usernames allowed to respond. Empty/omitted = any user with
            form_prompt:submit.
        responder_groups (list[str] | None | Unset): Group names whose members may respond. Empty/omitted = any user
            with form_prompt:submit.
        response_window (int | None | Unset): Seconds the responder has before the prompt expires. Falls back to
            workflow_engine.form_prompt_response_window_seconds.
        fallback_behavior (FormPromptNodeParametersFallbackBehavior | Unset): What happens when the prompt is not
            answered in time: fail the workflow, or route to the 'fallback' output port. Default:
            FormPromptNodeParametersFallbackBehavior.FAIL.
        submit_label (None | str | Unset): Submit button label.
        success_message (None | str | Unset): Shown after submission.
        timezone (None | str | Unset): IANA timezone for interpreting date/datetime field values in the form.
        css_override (None | str | Unset): Custom CSS applied to the form view.
    """

    form_definition: FormDefinition
    message: None | str | Unset = UNSET
    responder_users: list[str] | None | Unset = UNSET
    responder_groups: list[str] | None | Unset = UNSET
    response_window: int | None | Unset = UNSET
    fallback_behavior: FormPromptNodeParametersFallbackBehavior | Unset = FormPromptNodeParametersFallbackBehavior.FAIL
    submit_label: None | str | Unset = UNSET
    success_message: None | str | Unset = UNSET
    timezone: None | str | Unset = UNSET
    css_override: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        form_definition = self.form_definition.to_dict()

        message: None | str | Unset
        if isinstance(self.message, Unset):
            message = UNSET
        else:
            message = self.message

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

        fallback_behavior: str | Unset = UNSET
        if not isinstance(self.fallback_behavior, Unset):
            fallback_behavior = self.fallback_behavior.value

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

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "form_definition": form_definition,
            }
        )
        if message is not UNSET:
            field_dict["message"] = message
        if responder_users is not UNSET:
            field_dict["responder_users"] = responder_users
        if responder_groups is not UNSET:
            field_dict["responder_groups"] = responder_groups
        if response_window is not UNSET:
            field_dict["response_window"] = response_window
        if fallback_behavior is not UNSET:
            field_dict["fallback_behavior"] = fallback_behavior
        if submit_label is not UNSET:
            field_dict["submit_label"] = submit_label
        if success_message is not UNSET:
            field_dict["success_message"] = success_message
        if timezone is not UNSET:
            field_dict["timezone"] = timezone
        if css_override is not UNSET:
            field_dict["css_override"] = css_override

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.form_definition import FormDefinition

        d = dict(src_dict)
        form_definition = FormDefinition.from_dict(d.pop("form_definition"))

        def _parse_message(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        message = _parse_message(d.pop("message", UNSET))

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

        _fallback_behavior = d.pop("fallback_behavior", UNSET)
        fallback_behavior: FormPromptNodeParametersFallbackBehavior | Unset
        if isinstance(_fallback_behavior, Unset):
            fallback_behavior = UNSET
        else:
            fallback_behavior = FormPromptNodeParametersFallbackBehavior(_fallback_behavior)

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

        form_prompt_node_parameters = cls(
            form_definition=form_definition,
            message=message,
            responder_users=responder_users,
            responder_groups=responder_groups,
            response_window=response_window,
            fallback_behavior=fallback_behavior,
            submit_label=submit_label,
            success_message=success_message,
            timezone=timezone,
            css_override=css_override,
        )

        return form_prompt_node_parameters
