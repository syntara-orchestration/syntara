"""Tests for model profile lookup from LangChain's models.dev registry.

Covers:
- Curated set of popular frontier models return valid profiles
- Anthropic and Google models are discoverable
- OpenRouter-style prefixed model IDs are resolved
- Unknown models return None gracefully
- Lookup is a pure in-memory operation (no network calls)
"""

from unittest.mock import patch

import pytest

from syntara.integrations.services.model_profile_lookup import lookup_model_profile

CURATED_OPENAI_MODELS = [
    pytest.param("gpt-5.6-sol", marks=pytest.mark.xfail(reason="Not yet in langchain-openai profiles")),
    "gpt-5.5",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5",
    "gpt-5-mini",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "o4-mini",
    "o3",
    "o3-mini",
    "o1",
    "gpt-4-turbo",
]

CURATED_ANTHROPIC_MODELS = [
    "claude-opus-4-8",
    "claude-sonnet-4-5",
    "claude-sonnet-4-0",
    "claude-haiku-4-5",
    "claude-fable-5",
]

CURATED_GOOGLE_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
]

CURATED_MODELS = CURATED_OPENAI_MODELS + CURATED_ANTHROPIC_MODELS + CURATED_GOOGLE_MODELS

REQUIRED_PROFILE_KEYS = {"max_input_tokens", "max_output_tokens", "tool_calling"}


@pytest.mark.parametrize("model_id", CURATED_MODELS)
def test_curated_models_have_profiles(model_id: str) -> None:
    """Each curated frontier model must return a profile with key capability fields."""
    profile = lookup_model_profile(model_id)

    assert profile is not None, f"No profile found for curated model {model_id!r}"
    for key in REQUIRED_PROFILE_KEYS:
        assert key in profile, f"Profile for {model_id!r} missing required key {key!r}"


# ---------------------------------------------------------------------------
# OpenRouter prefix stripping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model_id", "expected_name"),
    [
        ("anthropic/claude-opus-4-8", "Claude Opus 4.8"),
        ("anthropic/claude-sonnet-4-0", "Claude Sonnet 4 (latest)"),
        ("anthropic/claude-haiku-4-5", "Claude Haiku 4.5 (latest)"),
        ("google/gemini-2.5-flash", "Gemini 2.5 Flash"),
        ("google/gemini-2.0-flash", "Gemini 2.0 Flash"),
        ("openai/gpt-4o", "GPT-4o"),
        ("openai/gpt-5.5", "GPT-5.5"),
    ],
)
def test_openrouter_prefixed_ids_resolve(model_id: str, expected_name: str) -> None:
    """Model IDs with a provider/ prefix (OpenRouter style) resolve to profiles."""
    profile = lookup_model_profile(model_id)

    assert profile is not None, f"No profile found for prefixed model {model_id!r}"
    assert profile["name"] == expected_name


def test_unknown_prefixed_model_returns_none() -> None:
    """A prefixed model not in any registry returns None."""
    assert lookup_model_profile("deepseek/deepseek-chat-v99") is None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_unknown_model_returns_none() -> None:
    """A model not in the registry returns None without raising."""
    assert lookup_model_profile("nonexistent-model-xyz-999") is None


def test_profile_is_cached() -> None:
    """Repeated lookups return the same cached object."""
    p1 = lookup_model_profile("gpt-4o")
    p2 = lookup_model_profile("gpt-4o")
    assert p1 is p2


def test_lookup_does_not_make_network_calls() -> None:
    """Profile lookup is a pure in-memory dict read — no HTTP traffic."""
    with patch("httpx.AsyncClient.send", side_effect=AssertionError("unexpected network call")):
        profile = lookup_model_profile("gpt-4o")

    assert profile is not None


def test_registry_error_returns_none() -> None:
    """If the registry lookup raises, lookup returns None gracefully."""
    lookup_model_profile.cache_clear()
    with patch(
        "syntara.integrations.services.model_profile_lookup._search_registries",
        side_effect=RuntimeError("broken"),
    ):
        assert lookup_model_profile("gpt-4o") is None
