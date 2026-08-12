"""Model profile service for resolving context window sizes from LangChain registries.

Provides a DB-like interface for looking up model token budgets. The current
implementation reads from LangChain's shipped profile registries; it will be
swapped to a database query once the model-management team populates
max_input_tokens on the llm_models table.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.stdlib.get_logger(__name__)

_MINIMUM_EFFECTIVE_BUDGET = 1024

_PROVIDER_HINT_TO_REGISTRY: dict[str, str] = {
    "openai": "langchain_openai",
    "anthropic": "langchain_anthropic",
    "gemini": "langchain_google_genai",
}

_registries: dict[str, dict[str, dict[str, Any]]] = {}
_registries_loaded: set[str] = set()


_IMPORT_PATHS: dict[str, str] = {
    "langchain_openai": "langchain_openai.data._profiles",
    "langchain_anthropic": "langchain_anthropic.data._profiles",
    "langchain_google_genai": "langchain_google_genai.data._profiles",
}


def _load_registry(registry_key: str) -> dict[str, dict[str, Any]]:
    """Lazily import and return the profile registry for a LangChain provider package."""
    if registry_key in _registries_loaded:
        return _registries.get(registry_key, {})

    _registries_loaded.add(registry_key)

    import_path = _IMPORT_PATHS.get(registry_key)
    if import_path is None:
        return {}

    try:
        module = importlib.import_module(import_path)
        _registries[registry_key] = dict(getattr(module, "_PROFILES", {}))
        return _registries[registry_key]
    except (ImportError, AttributeError):
        logger.warning("LangChain provider package not installed or incompatible", registry=registry_key)
        return {}


def _normalize_model_name(model: str) -> list[str]:
    """Return candidate model names for registry lookup.

    OpenRouter-style names use a ``provider/model`` format (e.g.
    ``"anthropic/claude-sonnet-4"``).  LangChain registries use
    provider-native names (e.g. ``"claude-sonnet-4-0"``).  This function
    returns the original name first, then the stripped suffix so both
    exact and prefix-stripped lookups are attempted.
    """
    candidates = [model]
    if "/" in model:
        stripped = model.split("/", 1)[1]
        candidates.append(stripped)
    return candidates


@dataclass(frozen=True)
class ModelTokenBudget:
    """Resolved token budget for a model.

    Attributes:
        max_input_tokens: Raw context window from the profile registry (0 if unknown).
        max_output_tokens: Raw max output tokens from the profile registry (0 if unknown).
        effective_context_budget: Usable input budget after subtracting
            output reserve and applying tokenizer safety margin.
        source: Where the data came from (e.g. ``"langchain_openai"``,
            ``"langchain_anthropic"``, ``"fallback"``).

    """

    max_input_tokens: int
    max_output_tokens: int
    effective_context_budget: int
    source: str


class ModelProfileService:
    """Resolve model token budgets from LangChain profile registries.

    Designed with a DB-like ``get`` interface so the implementation can be
    swapped to a database query (against ``llm_models.max_input_tokens``) once
    that column is populated by the model-management team.
    """

    async def get_token_budget(
        self,
        model: str | None,
        provider_hint: str | None = None,
        *,
        output_reserve: int = 4096,
        safety_margin: float = 0.90,
    ) -> ModelTokenBudget:
        """Look up a model's context window and compute an effective budget.

        Args:
            model: Provider-native model name (e.g. ``"gpt-4o"``,
                ``"claude-opus-4-6"``). ``None`` triggers fallback.
            provider_hint: Provider hint from ``LLMProviderHint``
                (``"openai"``, ``"anthropic"``, ``"gemini"``,
                ``"red_hat_ai"``, ``"custom"``).
            output_reserve: Tokens to reserve for model output generation.
            safety_margin: Multiplicative safety factor (0.90 = 10%% margin)
                to account for tokenizer mismatch.

        Returns:
            ModelTokenBudget with the resolved budget. When the model is not
            found, ``source`` is ``"fallback"`` and ``effective_context_budget``
            is 0 (the caller should use the existing settings value).

        """
        if model is None:
            logger.info("No model specified, using fallback budget")
            return _fallback_budget()

        profile, source = self._resolve_profile(model, provider_hint)
        if profile is None:
            logger.warning(
                "Model not found in any LangChain profile registry",
                model=model,
                provider_hint=provider_hint,
            )
            return _fallback_budget()

        max_input = profile.get("max_input_tokens", 0)
        max_output = profile.get("max_output_tokens", 0)

        if max_input <= 0:
            logger.warning(
                "Model profile has no max_input_tokens",
                model=model,
                source=source,
            )
            return _fallback_budget()

        if max_input <= output_reserve:
            logger.warning(
                "Model context window too small for output reserve, using fallback",
                model=model,
                source=source,
                max_input_tokens=max_input,
                output_reserve=output_reserve,
            )
            return _fallback_budget()

        effective = int((max_input - output_reserve) * safety_margin)
        effective = max(effective, _MINIMUM_EFFECTIVE_BUDGET)

        logger.info(
            "Model token budget resolved",
            model=model,
            source=source,
            max_input_tokens=max_input,
            max_output_tokens=max_output,
            effective_context_budget=effective,
        )

        return ModelTokenBudget(
            max_input_tokens=max_input,
            max_output_tokens=max_output,
            effective_context_budget=effective,
            source=source,
        )

    def _resolve_profile(
        self,
        model: str,
        provider_hint: str | None,
    ) -> tuple[dict[str, Any], str] | tuple[None, str]:
        """Look up a model in the appropriate LangChain profile registry.

        Uses ``provider_hint`` to select the registry. If no hint is provided
        or the hint maps to an unknown registry (e.g. ``"red_hat_ai"``),
        searches all registries.

        Handles OpenRouter-style model names (e.g. ``"anthropic/claude-sonnet-4"``)
        by stripping the provider prefix before lookup.

        Returns:
            ``(profile_dict, source_label)`` on match, or ``(None, "")`` if
            not found.

        """
        candidates = _normalize_model_name(model)
        registry_key = _PROVIDER_HINT_TO_REGISTRY.get(provider_hint or "")

        if registry_key:
            registry = _load_registry(registry_key)
            for candidate in candidates:
                profile = registry.get(candidate)
                if profile is not None:
                    return profile, registry_key
            return None, ""

        for key in _PROVIDER_HINT_TO_REGISTRY.values():
            registry = _load_registry(key)
            for candidate in candidates:
                profile = registry.get(candidate)
                if profile is not None:
                    return profile, key

        return None, ""


def _fallback_budget() -> ModelTokenBudget:
    return ModelTokenBudget(
        max_input_tokens=0,
        max_output_tokens=0,
        effective_context_budget=0,
        source="fallback",
    )
