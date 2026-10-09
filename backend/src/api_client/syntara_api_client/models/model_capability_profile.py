from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="ModelCapabilityProfile")


@_attrs_define
class ModelCapabilityProfile:
    """Typed view of an LLM model's capability profile.

    Attributes:
        name (None | str | Unset):
        status (None | str | Unset):
        release_date (None | str | Unset):
        last_updated (None | str | Unset):
        open_weights (bool | None | Unset):
        max_input_tokens (int | None | Unset):
        text_inputs (bool | None | Unset):
        image_inputs (bool | None | Unset):
        image_url_inputs (bool | None | Unset):
        pdf_inputs (bool | None | Unset):
        audio_inputs (bool | None | Unset):
        video_inputs (bool | None | Unset):
        image_tool_message (bool | None | Unset):
        pdf_tool_message (bool | None | Unset):
        max_output_tokens (int | None | Unset):
        reasoning_output (bool | None | Unset):
        text_outputs (bool | None | Unset):
        image_outputs (bool | None | Unset):
        audio_outputs (bool | None | Unset):
        video_outputs (bool | None | Unset):
        tool_calling (bool | None | Unset):
        tool_choice (bool | None | Unset):
        tool_call_streaming (bool | None | Unset):
        structured_output (bool | None | Unset):
        attachment (bool | None | Unset):
        temperature (bool | None | Unset):
    """

    name: None | str | Unset = UNSET
    status: None | str | Unset = UNSET
    release_date: None | str | Unset = UNSET
    last_updated: None | str | Unset = UNSET
    open_weights: bool | None | Unset = UNSET
    max_input_tokens: int | None | Unset = UNSET
    text_inputs: bool | None | Unset = UNSET
    image_inputs: bool | None | Unset = UNSET
    image_url_inputs: bool | None | Unset = UNSET
    pdf_inputs: bool | None | Unset = UNSET
    audio_inputs: bool | None | Unset = UNSET
    video_inputs: bool | None | Unset = UNSET
    image_tool_message: bool | None | Unset = UNSET
    pdf_tool_message: bool | None | Unset = UNSET
    max_output_tokens: int | None | Unset = UNSET
    reasoning_output: bool | None | Unset = UNSET
    text_outputs: bool | None | Unset = UNSET
    image_outputs: bool | None | Unset = UNSET
    audio_outputs: bool | None | Unset = UNSET
    video_outputs: bool | None | Unset = UNSET
    tool_calling: bool | None | Unset = UNSET
    tool_choice: bool | None | Unset = UNSET
    tool_call_streaming: bool | None | Unset = UNSET
    structured_output: bool | None | Unset = UNSET
    attachment: bool | None | Unset = UNSET
    temperature: bool | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        status: None | str | Unset
        if isinstance(self.status, Unset):
            status = UNSET
        else:
            status = self.status

        release_date: None | str | Unset
        if isinstance(self.release_date, Unset):
            release_date = UNSET
        else:
            release_date = self.release_date

        last_updated: None | str | Unset
        if isinstance(self.last_updated, Unset):
            last_updated = UNSET
        else:
            last_updated = self.last_updated

        open_weights: bool | None | Unset
        if isinstance(self.open_weights, Unset):
            open_weights = UNSET
        else:
            open_weights = self.open_weights

        max_input_tokens: int | None | Unset
        if isinstance(self.max_input_tokens, Unset):
            max_input_tokens = UNSET
        else:
            max_input_tokens = self.max_input_tokens

        text_inputs: bool | None | Unset
        if isinstance(self.text_inputs, Unset):
            text_inputs = UNSET
        else:
            text_inputs = self.text_inputs

        image_inputs: bool | None | Unset
        if isinstance(self.image_inputs, Unset):
            image_inputs = UNSET
        else:
            image_inputs = self.image_inputs

        image_url_inputs: bool | None | Unset
        if isinstance(self.image_url_inputs, Unset):
            image_url_inputs = UNSET
        else:
            image_url_inputs = self.image_url_inputs

        pdf_inputs: bool | None | Unset
        if isinstance(self.pdf_inputs, Unset):
            pdf_inputs = UNSET
        else:
            pdf_inputs = self.pdf_inputs

        audio_inputs: bool | None | Unset
        if isinstance(self.audio_inputs, Unset):
            audio_inputs = UNSET
        else:
            audio_inputs = self.audio_inputs

        video_inputs: bool | None | Unset
        if isinstance(self.video_inputs, Unset):
            video_inputs = UNSET
        else:
            video_inputs = self.video_inputs

        image_tool_message: bool | None | Unset
        if isinstance(self.image_tool_message, Unset):
            image_tool_message = UNSET
        else:
            image_tool_message = self.image_tool_message

        pdf_tool_message: bool | None | Unset
        if isinstance(self.pdf_tool_message, Unset):
            pdf_tool_message = UNSET
        else:
            pdf_tool_message = self.pdf_tool_message

        max_output_tokens: int | None | Unset
        if isinstance(self.max_output_tokens, Unset):
            max_output_tokens = UNSET
        else:
            max_output_tokens = self.max_output_tokens

        reasoning_output: bool | None | Unset
        if isinstance(self.reasoning_output, Unset):
            reasoning_output = UNSET
        else:
            reasoning_output = self.reasoning_output

        text_outputs: bool | None | Unset
        if isinstance(self.text_outputs, Unset):
            text_outputs = UNSET
        else:
            text_outputs = self.text_outputs

        image_outputs: bool | None | Unset
        if isinstance(self.image_outputs, Unset):
            image_outputs = UNSET
        else:
            image_outputs = self.image_outputs

        audio_outputs: bool | None | Unset
        if isinstance(self.audio_outputs, Unset):
            audio_outputs = UNSET
        else:
            audio_outputs = self.audio_outputs

        video_outputs: bool | None | Unset
        if isinstance(self.video_outputs, Unset):
            video_outputs = UNSET
        else:
            video_outputs = self.video_outputs

        tool_calling: bool | None | Unset
        if isinstance(self.tool_calling, Unset):
            tool_calling = UNSET
        else:
            tool_calling = self.tool_calling

        tool_choice: bool | None | Unset
        if isinstance(self.tool_choice, Unset):
            tool_choice = UNSET
        else:
            tool_choice = self.tool_choice

        tool_call_streaming: bool | None | Unset
        if isinstance(self.tool_call_streaming, Unset):
            tool_call_streaming = UNSET
        else:
            tool_call_streaming = self.tool_call_streaming

        structured_output: bool | None | Unset
        if isinstance(self.structured_output, Unset):
            structured_output = UNSET
        else:
            structured_output = self.structured_output

        attachment: bool | None | Unset
        if isinstance(self.attachment, Unset):
            attachment = UNSET
        else:
            attachment = self.attachment

        temperature: bool | None | Unset
        if isinstance(self.temperature, Unset):
            temperature = UNSET
        else:
            temperature = self.temperature

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if name is not UNSET:
            field_dict["name"] = name
        if status is not UNSET:
            field_dict["status"] = status
        if release_date is not UNSET:
            field_dict["release_date"] = release_date
        if last_updated is not UNSET:
            field_dict["last_updated"] = last_updated
        if open_weights is not UNSET:
            field_dict["open_weights"] = open_weights
        if max_input_tokens is not UNSET:
            field_dict["max_input_tokens"] = max_input_tokens
        if text_inputs is not UNSET:
            field_dict["text_inputs"] = text_inputs
        if image_inputs is not UNSET:
            field_dict["image_inputs"] = image_inputs
        if image_url_inputs is not UNSET:
            field_dict["image_url_inputs"] = image_url_inputs
        if pdf_inputs is not UNSET:
            field_dict["pdf_inputs"] = pdf_inputs
        if audio_inputs is not UNSET:
            field_dict["audio_inputs"] = audio_inputs
        if video_inputs is not UNSET:
            field_dict["video_inputs"] = video_inputs
        if image_tool_message is not UNSET:
            field_dict["image_tool_message"] = image_tool_message
        if pdf_tool_message is not UNSET:
            field_dict["pdf_tool_message"] = pdf_tool_message
        if max_output_tokens is not UNSET:
            field_dict["max_output_tokens"] = max_output_tokens
        if reasoning_output is not UNSET:
            field_dict["reasoning_output"] = reasoning_output
        if text_outputs is not UNSET:
            field_dict["text_outputs"] = text_outputs
        if image_outputs is not UNSET:
            field_dict["image_outputs"] = image_outputs
        if audio_outputs is not UNSET:
            field_dict["audio_outputs"] = audio_outputs
        if video_outputs is not UNSET:
            field_dict["video_outputs"] = video_outputs
        if tool_calling is not UNSET:
            field_dict["tool_calling"] = tool_calling
        if tool_choice is not UNSET:
            field_dict["tool_choice"] = tool_choice
        if tool_call_streaming is not UNSET:
            field_dict["tool_call_streaming"] = tool_call_streaming
        if structured_output is not UNSET:
            field_dict["structured_output"] = structured_output
        if attachment is not UNSET:
            field_dict["attachment"] = attachment
        if temperature is not UNSET:
            field_dict["temperature"] = temperature

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        def _parse_status(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        status = _parse_status(d.pop("status", UNSET))

        def _parse_release_date(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        release_date = _parse_release_date(d.pop("release_date", UNSET))

        def _parse_last_updated(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        last_updated = _parse_last_updated(d.pop("last_updated", UNSET))

        def _parse_open_weights(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        open_weights = _parse_open_weights(d.pop("open_weights", UNSET))

        def _parse_max_input_tokens(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        max_input_tokens = _parse_max_input_tokens(d.pop("max_input_tokens", UNSET))

        def _parse_text_inputs(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        text_inputs = _parse_text_inputs(d.pop("text_inputs", UNSET))

        def _parse_image_inputs(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        image_inputs = _parse_image_inputs(d.pop("image_inputs", UNSET))

        def _parse_image_url_inputs(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        image_url_inputs = _parse_image_url_inputs(d.pop("image_url_inputs", UNSET))

        def _parse_pdf_inputs(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        pdf_inputs = _parse_pdf_inputs(d.pop("pdf_inputs", UNSET))

        def _parse_audio_inputs(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        audio_inputs = _parse_audio_inputs(d.pop("audio_inputs", UNSET))

        def _parse_video_inputs(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        video_inputs = _parse_video_inputs(d.pop("video_inputs", UNSET))

        def _parse_image_tool_message(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        image_tool_message = _parse_image_tool_message(d.pop("image_tool_message", UNSET))

        def _parse_pdf_tool_message(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        pdf_tool_message = _parse_pdf_tool_message(d.pop("pdf_tool_message", UNSET))

        def _parse_max_output_tokens(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        max_output_tokens = _parse_max_output_tokens(d.pop("max_output_tokens", UNSET))

        def _parse_reasoning_output(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        reasoning_output = _parse_reasoning_output(d.pop("reasoning_output", UNSET))

        def _parse_text_outputs(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        text_outputs = _parse_text_outputs(d.pop("text_outputs", UNSET))

        def _parse_image_outputs(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        image_outputs = _parse_image_outputs(d.pop("image_outputs", UNSET))

        def _parse_audio_outputs(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        audio_outputs = _parse_audio_outputs(d.pop("audio_outputs", UNSET))

        def _parse_video_outputs(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        video_outputs = _parse_video_outputs(d.pop("video_outputs", UNSET))

        def _parse_tool_calling(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        tool_calling = _parse_tool_calling(d.pop("tool_calling", UNSET))

        def _parse_tool_choice(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        tool_choice = _parse_tool_choice(d.pop("tool_choice", UNSET))

        def _parse_tool_call_streaming(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        tool_call_streaming = _parse_tool_call_streaming(d.pop("tool_call_streaming", UNSET))

        def _parse_structured_output(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        structured_output = _parse_structured_output(d.pop("structured_output", UNSET))

        def _parse_attachment(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        attachment = _parse_attachment(d.pop("attachment", UNSET))

        def _parse_temperature(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        temperature = _parse_temperature(d.pop("temperature", UNSET))

        model_capability_profile = cls(
            name=name,
            status=status,
            release_date=release_date,
            last_updated=last_updated,
            open_weights=open_weights,
            max_input_tokens=max_input_tokens,
            text_inputs=text_inputs,
            image_inputs=image_inputs,
            image_url_inputs=image_url_inputs,
            pdf_inputs=pdf_inputs,
            audio_inputs=audio_inputs,
            video_inputs=video_inputs,
            image_tool_message=image_tool_message,
            pdf_tool_message=pdf_tool_message,
            max_output_tokens=max_output_tokens,
            reasoning_output=reasoning_output,
            text_outputs=text_outputs,
            image_outputs=image_outputs,
            audio_outputs=audio_outputs,
            video_outputs=video_outputs,
            tool_calling=tool_calling,
            tool_choice=tool_choice,
            tool_call_streaming=tool_call_streaming,
            structured_output=structured_output,
            attachment=attachment,
            temperature=temperature,
        )

        return model_capability_profile
