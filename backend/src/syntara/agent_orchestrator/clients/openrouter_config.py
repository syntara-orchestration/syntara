"""LangChain ChatOpenAI configuration for OpenRouter.

Configures LangChain to use OpenRouter as the LLM provider.
OpenRouter provides API gateway to multiple LLMs (Claude, GPT-4, etc.).
"""

from typing import Any

import httpx
import structlog
from langchain_openai import ChatOpenAI

from syntara.agent_orchestrator.exceptions import LLMConfigurationError
from syntara.core.config.base import get_settings
from syntara.core.lib.tls_utils import build_integration_httpx_verify
from syntara.settings.cache.settings_cache import get_runtime_settings
from syntara.settings.exceptions import SettingError

logger = structlog.stdlib.get_logger(__name__)


async def get_openrouter_llm(
    *,
    api_key: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    base_url: str | None = None,
    insecure_skip_tls_verify: bool = False,
    ca_certificate: str | None = None,
) -> tuple[ChatOpenAI, httpx.AsyncClient | None]:
    """Configure LangChain ChatOpenAI for an LLM provider endpoint.

    Despite the name, this function supports any OpenAI-compatible endpoint —
    not just OpenRouter. It will be renamed as part of a broader refactor of
    the legacy OpenRouter implementation.

    By default, ``temperature`` and ``max_completion_tokens`` are omitted from
    the ``ChatOpenAI`` constructor so that each provider applies its own
    model-appropriate defaults.  Callers may pass explicit values to override
    this behaviour, and an admin may set the ``agentic.max_completion_tokens``
    runtime setting to act as a global cap (0 means no cap).

    Args:
        api_key: API key from credential system (required).
        model: Model name (e.g. 'gpt-4o', 'anthropic/claude-opus-4'). If None, uses settings default.
        temperature: LLM temperature. If None, omitted from the API call so the provider default is used.
        max_tokens: Maximum tokens in response. If None, falls back to the ``agentic.max_completion_tokens``
            runtime setting; a value of 0 (the default) means no cap.
        base_url: Base URL of the LLM provider endpoint. If None, uses settings default.
        insecure_skip_tls_verify: Disable TLS certificate verification.
        ca_certificate: PEM-encoded CA certificate to trust.

    Returns:
        Tuple of (ChatOpenAI instance, optional httpx.AsyncClient that the caller
        must close when the LLM is no longer needed — ``None`` when no custom TLS
        client was created).

    Raises:
        LLMConfigurationError: If no API key is provided

    """
    if not api_key:
        error_msg = "No LLM API key available. Attach an LLM Provider credential to the workflow's agentic node."
        raise LLMConfigurationError(error_msg)

    settings = get_settings()

    kwargs: dict[str, Any] = {
        "model": model or settings.openrouter_model,
        "api_key": api_key,
        "base_url": str(base_url or settings.openrouter_base_url),
        "stream_usage": True,
        "default_headers": {
            "HTTP-Referer": "https://github.com/syntara-orchestration/syntara",
            "X-Title": settings.product_name,
        },
    }

    if temperature is not None:
        kwargs["temperature"] = temperature

    effective_max_tokens = max_tokens
    if effective_max_tokens is None:
        try:
            cap = await get_runtime_settings().get_int("agentic.max_completion_tokens")
            if cap > 0:
                effective_max_tokens = cap
        except (SettingError, OSError, ValueError, RuntimeError):
            logger.warning(
                "Failed to fetch agentic.max_completion_tokens from runtime settings; proceeding without cap",
                exc_info=True,
            )

    if effective_max_tokens is not None and effective_max_tokens > 0:
        kwargs["max_completion_tokens"] = effective_max_tokens

    http_client: httpx.AsyncClient | None = None
    if insecure_skip_tls_verify or ca_certificate:
        verify = build_integration_httpx_verify(
            insecure_skip_tls_verify=insecure_skip_tls_verify,
            ca_certificate=ca_certificate,
        )
        http_client = httpx.AsyncClient(verify=verify)
        kwargs["http_async_client"] = http_client

    logger.info(
        "Initializing OpenRouter LLM",
        model=kwargs["model"],
        temperature=kwargs.get("temperature"),
        max_completion_tokens=kwargs.get("max_completion_tokens"),
    )

    return ChatOpenAI(**kwargs), http_client
