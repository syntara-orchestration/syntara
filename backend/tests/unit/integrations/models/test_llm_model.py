"""Unit tests for LLMModel and ModelCapabilityProfile."""

from typing import Any
from uuid import uuid4

import pytest

from syntara.integrations.models.llm_model import (
    LLMModel,
    LLMModelBulkUpdate,
    LLMModelRead,
    LLMModelUpdate,
    ModelCapabilityProfile,
)

_GPT4O_PROFILE: dict[str, Any] = {
    "name": "GPT-4o",
    "max_input_tokens": 128000,
    "max_output_tokens": 16384,
    "tool_calling": True,
    "structured_output": True,
    "image_inputs": True,
    "audio_inputs": False,
}


class TestModelCapabilityProfile:
    """Tests for the ModelCapabilityProfile SQLModel schema."""

    def test_all_fields_populated(self) -> None:
        cap = ModelCapabilityProfile(
            max_input_tokens=128000,
            max_output_tokens=16384,
            tool_calling=True,
            structured_output=True,
            image_inputs=True,
            audio_inputs=False,
        )
        assert cap.max_input_tokens == 128000
        assert cap.max_output_tokens == 16384
        assert cap.tool_calling is True
        assert cap.structured_output is True
        assert cap.image_inputs is True
        assert cap.audio_inputs is False

    def test_all_fields_default_to_none(self) -> None:
        cap = ModelCapabilityProfile()
        assert cap.max_input_tokens is None
        assert cap.tool_calling is None

    def test_extra_fields_are_ignored(self) -> None:
        cap = ModelCapabilityProfile.model_validate({"max_input_tokens": 128000, "brand_new_field": True})
        assert cap.max_input_tokens == 128000
        assert not hasattr(cap, "brand_new_field")


class TestLLMModelCapabilityProfile:
    """Tests for LLMModel.capability_profile property."""

    def _make_model(self, profile: dict[str, Any] | None = None) -> LLMModel:
        return LLMModel(
            id=uuid4(),
            integration_id=uuid4(),
            model_id="test-model",
            name="Test Model",
            profile=profile,
        )

    def test_returns_none_when_profile_is_none(self) -> None:
        model = self._make_model(profile=None)
        assert model.capability_profile is None

    def test_returns_none_when_profile_is_empty_dict(self) -> None:
        model = self._make_model(profile={})
        assert model.capability_profile is None

    def test_extracts_all_fields_from_full_profile(self) -> None:
        model = self._make_model(profile=_GPT4O_PROFILE)
        cap = model.capability_profile
        assert cap is not None
        assert cap.max_input_tokens == 128000
        assert cap.max_output_tokens == 16384
        assert cap.tool_calling is True
        assert cap.structured_output is True
        assert cap.image_inputs is True
        assert cap.audio_inputs is False

    def test_missing_keys_return_none(self) -> None:
        model = self._make_model(profile={"max_input_tokens": 200000})
        cap = model.capability_profile
        assert cap is not None
        assert cap.max_input_tokens == 200000
        assert cap.max_output_tokens is None
        assert cap.tool_calling is None
        assert cap.structured_output is None
        assert cap.image_inputs is None
        assert cap.audio_inputs is None

    def test_unknown_profile_keys_are_ignored(self) -> None:
        profile = {**_GPT4O_PROFILE, "brand_new_field": "future_value"}
        model = self._make_model(profile=profile)
        cap = model.capability_profile
        assert cap is not None
        assert cap.max_input_tokens == 128000
        assert not hasattr(cap, "brand_new_field")


class TestLLMModelUpdate:
    """Tests for LLMModelUpdate validation."""

    def test_rejects_empty_update(self) -> None:
        with pytest.raises(ValueError, match="At least one field must be provided"):
            LLMModelUpdate()

    def test_accepts_enabled_only(self) -> None:
        update = LLMModelUpdate(enabled=False)
        assert update.enabled is False
        assert update.is_default is None

    def test_accepts_is_default_only(self) -> None:
        update = LLMModelUpdate(is_default=True)
        assert update.is_default is True
        assert update.enabled is None


class TestLLMModelBulkUpdate:
    """Tests for LLMModelBulkUpdate with large model counts (AAP-82457)."""

    def test_accepts_more_than_1000_model_ids(self) -> None:
        ids = [uuid4() for _ in range(1500)]
        update = LLMModelBulkUpdate(model_ids=ids, enabled=True)
        assert len(update.model_ids) == 1500

    def test_accepts_empty_model_ids(self) -> None:
        update = LLMModelBulkUpdate(model_ids=[], enabled=False)
        assert update.model_ids == []


class TestLLMModelRead:
    """Tests for LLMModelRead schema."""

    def test_profile_defaults_to_none(self) -> None:
        read = LLMModelRead(
            id=uuid4(),
            integration_id=uuid4(),
            model_id="test",
            name="Test",
        )
        assert read.profile is None

    def test_profile_round_trips(self) -> None:
        read = LLMModelRead(
            id=uuid4(),
            integration_id=uuid4(),
            model_id="test",
            name="Test",
            profile=ModelCapabilityProfile(max_input_tokens=128000, tool_calling=True),
        )
        assert read.profile is not None
        assert read.profile.max_input_tokens == 128000
        assert read.profile.tool_calling is True

    def test_profile_from_dict(self) -> None:
        read = LLMModelRead.model_validate(
            {
                "id": str(uuid4()),
                "integration_id": str(uuid4()),
                "model_id": "test",
                "name": "Test",
                "profile": _GPT4O_PROFILE,
            }
        )
        assert read.profile is not None
        assert read.profile.max_input_tokens == 128000

    def test_jsonb_stores_extra_fields_but_api_drops_them(self) -> None:
        """JSONB stores all raw profile keys; the API schema only exposes known fields."""
        raw_profile = {**_GPT4O_PROFILE, "future_capability": True}
        model = LLMModel(
            id=uuid4(),
            integration_id=uuid4(),
            model_id="test",
            name="Test",
            profile=raw_profile,
        )
        assert model.profile is not None
        assert model.profile["future_capability"] is True

        read = LLMModelRead.model_validate(model.model_dump())
        assert read.profile is not None
        assert read.profile.max_input_tokens == 128000
        dumped = read.profile.model_dump()
        assert "future_capability" not in dumped
