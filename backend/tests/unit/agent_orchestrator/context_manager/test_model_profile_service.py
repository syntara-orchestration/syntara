"""Unit tests for ModelProfileService."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from syntara.agent_orchestrator.context_manager.model_profile_service import (
    _MINIMUM_EFFECTIVE_BUDGET,
    ModelProfileService,
    ModelTokenBudget,
    _normalize_model_name,
    _registries,
    _registries_loaded,
)


@pytest.fixture(autouse=True)
def _clear_registry_cache() -> None:
    """Clear cached registries between tests so lazy loading is re-exercised."""
    _registries.clear()
    _registries_loaded.clear()


class TestProfileResolution:
    """Tests for resolving model profiles from LangChain registries."""

    @pytest.mark.anyio
    async def test_openai_model_with_provider_hint(self) -> None:
        service = ModelProfileService()
        budget = await service.get_token_budget("gpt-4o", provider_hint="openai")

        assert budget.source == "langchain_openai"
        assert budget.max_input_tokens > 0
        assert budget.max_output_tokens > 0
        assert budget.effective_context_budget > 0

    @pytest.mark.anyio
    async def test_anthropic_model_with_provider_hint(self) -> None:
        service = ModelProfileService()
        budget = await service.get_token_budget("claude-opus-4-0", provider_hint="anthropic")

        assert budget.source == "langchain_anthropic"
        assert budget.max_input_tokens >= 200000

    @pytest.mark.anyio
    async def test_google_model_with_provider_hint(self) -> None:
        service = ModelProfileService()
        budget = await service.get_token_budget("gemini-2.5-flash", provider_hint="gemini")

        assert budget.source == "langchain_google_genai"
        assert budget.max_input_tokens > 0

    @pytest.mark.anyio
    async def test_provider_hint_selects_correct_registry(self) -> None:
        """provider_hint='openai' should not find Anthropic models."""
        service = ModelProfileService()
        budget = await service.get_token_budget("claude-opus-4-0", provider_hint="openai")

        assert budget.source == "fallback"

    @pytest.mark.anyio
    async def test_no_provider_hint_searches_all_registries(self) -> None:
        service = ModelProfileService()

        budget_openai = await service.get_token_budget("gpt-4o")
        assert budget_openai.source == "langchain_openai"

        _registries.clear()
        _registries_loaded.clear()

        budget_anthropic = await service.get_token_budget("claude-opus-4-0")
        assert budget_anthropic.source == "langchain_anthropic"

    @pytest.mark.anyio
    async def test_red_hat_ai_hint_searches_all_registries(self) -> None:
        service = ModelProfileService()
        budget = await service.get_token_budget("gpt-4o", provider_hint="red_hat_ai")

        assert budget.source == "langchain_openai"

    @pytest.mark.anyio
    async def test_custom_hint_searches_all_registries(self) -> None:
        service = ModelProfileService()
        budget = await service.get_token_budget("gpt-4o", provider_hint="custom")

        assert budget.source == "langchain_openai"

    @pytest.mark.anyio
    async def test_unknown_model_returns_fallback(self) -> None:
        service = ModelProfileService()
        budget = await service.get_token_budget("nonexistent-model-xyz", provider_hint="openai")

        assert budget.source == "fallback"
        assert budget.max_input_tokens == 0
        assert budget.max_output_tokens == 0
        assert budget.effective_context_budget == 0


class TestOpenRouterNormalization:
    """Tests for OpenRouter-style model name normalization."""

    def test_plain_model_name(self) -> None:
        assert _normalize_model_name("gpt-4o") == ["gpt-4o"]

    def test_openrouter_prefix_stripped(self) -> None:
        candidates = _normalize_model_name("anthropic/claude-sonnet-4")
        assert candidates == ["anthropic/claude-sonnet-4", "claude-sonnet-4"]

    def test_multiple_slashes(self) -> None:
        candidates = _normalize_model_name("provider/org/model")
        assert candidates == ["provider/org/model", "org/model"]

    @pytest.mark.anyio
    async def test_openrouter_model_resolves_via_stripped_name(self) -> None:
        service = ModelProfileService()
        with patch.dict(
            _registries,
            {"langchain_anthropic": {"claude-sonnet-4": {"max_input_tokens": 200000, "max_output_tokens": 8192}}},
        ):
            _registries_loaded.add("langchain_anthropic")
            budget = await service.get_token_budget(
                "anthropic/claude-sonnet-4",
                provider_hint="anthropic",
            )

        assert budget.source == "langchain_anthropic"
        assert budget.max_input_tokens == 200000


class TestBudgetCalculation:
    """Tests for effective context budget computation."""

    @pytest.mark.anyio
    async def test_budget_formula(self) -> None:
        """Effective = int((max_input_tokens - output_reserve) * safety_margin)."""
        service = ModelProfileService()
        budget = await service.get_token_budget(
            "gpt-4o",
            provider_hint="openai",
            output_reserve=4096,
            safety_margin=0.90,
        )

        expected = int((budget.max_input_tokens - 4096) * 0.90)
        assert budget.effective_context_budget == expected

    @pytest.mark.anyio
    async def test_custom_safety_margin(self) -> None:
        service = ModelProfileService()
        budget = await service.get_token_budget(
            "gpt-4o",
            provider_hint="openai",
            output_reserve=4096,
            safety_margin=0.80,
        )

        expected = int((budget.max_input_tokens - 4096) * 0.80)
        assert budget.effective_context_budget == expected

    @pytest.mark.anyio
    async def test_custom_output_reserve(self) -> None:
        service = ModelProfileService()
        budget = await service.get_token_budget(
            "gpt-4o",
            provider_hint="openai",
            output_reserve=8192,
            safety_margin=0.90,
        )

        expected = int((budget.max_input_tokens - 8192) * 0.90)
        assert budget.effective_context_budget == expected

    @pytest.mark.anyio
    async def test_small_context_window_returns_fallback(self) -> None:
        """When output_reserve exceeds max_input_tokens, return fallback."""
        service = ModelProfileService()

        with patch.dict(
            _registries,
            {"langchain_openai": {"tiny-model": {"max_input_tokens": 1000, "max_output_tokens": 500}}},
        ):
            _registries_loaded.add("langchain_openai")
            budget = await service.get_token_budget(
                "tiny-model",
                provider_hint="openai",
                output_reserve=2000,
            )

        assert budget.source == "fallback"
        assert budget.effective_context_budget == 0

    @pytest.mark.anyio
    async def test_context_equal_to_reserve_returns_fallback(self) -> None:
        """When max_input_tokens == output_reserve, return fallback."""
        service = ModelProfileService()

        with patch.dict(
            _registries,
            {"langchain_openai": {"edge-model": {"max_input_tokens": 4096, "max_output_tokens": 2048}}},
        ):
            _registries_loaded.add("langchain_openai")
            budget = await service.get_token_budget(
                "edge-model",
                provider_hint="openai",
                output_reserve=4096,
            )

        assert budget.source == "fallback"
        assert budget.effective_context_budget == 0

    @pytest.mark.anyio
    async def test_minimum_clamp_applied_when_budget_positive_but_small(self) -> None:
        """When budget is positive but below minimum, clamp to _MINIMUM_EFFECTIVE_BUDGET."""
        service = ModelProfileService()

        with patch.dict(
            _registries,
            {"langchain_openai": {"small-model": {"max_input_tokens": 5000, "max_output_tokens": 500}}},
        ):
            _registries_loaded.add("langchain_openai")
            budget = await service.get_token_budget(
                "small-model",
                provider_hint="openai",
                output_reserve=4500,
            )

        assert budget.effective_context_budget == _MINIMUM_EFFECTIVE_BUDGET


class TestFallbackBehavior:
    """Tests for fallback when model data is unavailable."""

    @pytest.mark.anyio
    async def test_none_model_returns_fallback(self) -> None:
        service = ModelProfileService()
        budget = await service.get_token_budget(None)

        assert budget.source == "fallback"
        assert budget.effective_context_budget == 0

    @pytest.mark.anyio
    async def test_zero_max_input_tokens_returns_fallback(self) -> None:
        service = ModelProfileService()

        with patch.dict(
            _registries,
            {"langchain_openai": {"zero-model": {"max_input_tokens": 0, "max_output_tokens": 0}}},
        ):
            _registries_loaded.add("langchain_openai")
            budget = await service.get_token_budget("zero-model", provider_hint="openai")

        assert budget.source == "fallback"

    @pytest.mark.anyio
    async def test_missing_package_degrades_gracefully(self) -> None:
        """If a LangChain provider package is not installed, still return fallback."""
        service = ModelProfileService()

        with patch(
            "syntara.agent_orchestrator.context_manager.model_profile_service._load_registry",
            return_value={},
        ):
            budget = await service.get_token_budget("gpt-4o", provider_hint="openai")

        assert budget.source == "fallback"

    @pytest.mark.anyio
    async def test_attribute_error_degrades_gracefully(self) -> None:
        """If _PROFILES is removed in a future LangChain update, degrade gracefully."""
        service = ModelProfileService()

        with patch(
            "syntara.agent_orchestrator.context_manager.model_profile_service.importlib.import_module",
            side_effect=AttributeError("module has no attribute '_PROFILES'"),
        ):
            budget = await service.get_token_budget("gpt-4o", provider_hint="openai")

        assert budget.source == "fallback"


class TestModelTokenBudget:
    """Tests for the ModelTokenBudget dataclass."""

    def test_frozen_dataclass(self) -> None:
        budget = ModelTokenBudget(
            max_input_tokens=128000,
            max_output_tokens=4096,
            effective_context_budget=111513,
            source="langchain_openai",
        )

        with pytest.raises(AttributeError):
            budget.max_input_tokens = 0  # type: ignore[misc]

    def test_fields(self) -> None:
        budget = ModelTokenBudget(
            max_input_tokens=200000,
            max_output_tokens=8192,
            effective_context_budget=176313,
            source="langchain_anthropic",
        )

        assert budget.max_input_tokens == 200000
        assert budget.max_output_tokens == 8192
        assert budget.effective_context_budget == 176313
        assert budget.source == "langchain_anthropic"
