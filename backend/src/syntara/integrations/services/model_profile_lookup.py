"""Look up LLM model capability profiles from LangChain's models.dev registry."""

from __future__ import annotations

import functools
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Private imports: the alternative is instantiating a client with dummy credentials
# and reading .profile, which is heavier and fragile in its own way.  Wrapped in
# try/except so a LangChain rename or removal degrades gracefully (profile lookup
# returns None) instead of crashing the module at import time.
_ANTHROPIC_PROFILES: dict[str, Any] = {}
try:
    from langchain_anthropic.chat_models import _MODEL_PROFILES as _ANTHROPIC_PROFILES
except (ImportError, AttributeError):
    logger.debug("langchain_anthropic profile registry unavailable")

_GOOGLE_PROFILES: dict[str, Any] = {}
try:
    from langchain_google_genai.chat_models import _MODEL_PROFILES as _GOOGLE_PROFILES
except (ImportError, AttributeError):
    logger.debug("langchain_google_genai profile registry unavailable")

_OPENAI_PROFILES: dict[str, Any] = {}
try:
    from langchain_openai.chat_models.base import _MODEL_PROFILES as _OPENAI_PROFILES
except (ImportError, AttributeError):
    logger.debug("langchain_openai profile registry unavailable")

_REGISTRIES: list[dict[str, Any]] = [_OPENAI_PROFILES, _ANTHROPIC_PROFILES, _GOOGLE_PROFILES]


def _search_registries(key: str) -> dict[str, Any] | None:
    for registry in _REGISTRIES:
        profile = registry.get(key)
        if profile is not None:
            return dict(profile)
    return None


@functools.lru_cache(maxsize=256)
def lookup_model_profile(model_id: str) -> dict[str, Any] | None:
    """Return the models.dev profile for *model_id*, or ``None`` if unavailable.

    Searches the OpenAI, Anthropic, and Google profile registries shipped
    with their respective ``langchain`` packages.  When *model_id* contains
    a ``/`` (e.g. ``anthropic/claude-opus-4-8`` from OpenRouter), the
    provider prefix is stripped and the bare model name is looked up.

    This is a pure in-memory dict lookup — no network calls are made.
    """
    try:
        profile = _search_registries(model_id)
        if profile is not None:
            return profile

        if "/" in model_id:
            bare = model_id.split("/", 1)[1]
            return _search_registries(bare)

        return None
    except Exception:  # noqa: BLE001
        logger.warning("model_profile_lookup_failed", model_id=model_id, exc_info=True)
        return None
