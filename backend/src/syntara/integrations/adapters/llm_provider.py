"""LLM provider adapter implementing validate() and discover().

validate(): Hits the provider's model listing endpoint, then (for
  OpenAI-compatible providers) GET {base_url}/key so a public catalog 200
  cannot mark an invalid API key as healthy. The listing body is not parsed.

discover(): Paginated model listing parsed into DiscoveredLLMModel objects.
  Does not persist anything and does not run the /key probe — listing is a
  catalog fetch. Refresh uses this path.

Provider dispatch uses LLMProviderConfiguration.provider_hint to select the
correct provider implementation (OpenAI-compatible, Anthropic, or Gemini).
"""

from __future__ import annotations

import ssl
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable

import httpx
import structlog
from httpx import HTTPStatusError, codes

from syntara.core.lib.tls_utils import build_integration_httpx_verify
from syntara.integrations.adapters.factory import register_health_check_adapter
from syntara.integrations.adapters.protocol import (
    DiscoveredLLMModel,
    DiscoverResult,
    HealthCheckErrorType,
    ValidateResult,
    classify_http_error,
)
from syntara.integrations.adapters.providers import (
    AnthropicProvider,
    GoogleProvider,
    LLMProviderBase,
    OpenAICompatibleProvider,
)
from syntara.integrations.models.integration import IntegrationType
from syntara.integrations.models.integration_configuration import (
    LLMProviderConfiguration,
    LLMProviderHint,
)

logger = structlog.stdlib.get_logger(__name__)

_MAX_PAGINATION_PAGES = 10

# 404/405/501 on the credential probe means the gateway has no /key-style
# endpoint (OpenAI, vLLM). Trust the models listing instead of failing.
_PROBE_ABSENT_STATUSES = frozenset(
    {codes.NOT_FOUND, codes.METHOD_NOT_ALLOWED, codes.NOT_IMPLEMENTED},
)

_PROVIDER_CONSTRUCTORS: dict[LLMProviderHint, Callable[[], LLMProviderBase]] = {
    LLMProviderHint.OPENAI: OpenAICompatibleProvider,
    LLMProviderHint.RED_HAT_AI: lambda: OpenAICompatibleProvider(default_url=None),
    LLMProviderHint.CUSTOM: lambda: OpenAICompatibleProvider(default_url=None),
    LLMProviderHint.ANTHROPIC: AnthropicProvider,
    LLMProviderHint.GEMINI: GoogleProvider,
}


def _get_provider(hint: LLMProviderHint) -> LLMProviderBase:
    """Create a fresh provider instance for the given hint."""
    constructor = _PROVIDER_CONSTRUCTORS.get(hint)
    if constructor is None:
        msg = f"No provider implementation for {hint}"
        raise ValueError(msg)
    return constructor()


def _resolve_base_url(config: LLMProviderConfiguration, provider: LLMProviderBase) -> str:
    """Resolve the effective base URL from config or provider default."""
    if config.base_url:
        return config.base_url
    if provider.default_base_url:
        return provider.default_base_url
    msg = f"base_url is required for {config.provider_hint} provider"
    raise ValueError(msg)


class LLMProviderAdapter:
    """Adapter for LLM provider integrations implementing validate() and discover().

    Delegates provider-specific behavior (URL construction, auth headers,
    response parsing) to an LLMProviderBase subclass selected by provider_hint.
    """

    def __init__(self, config: LLMProviderConfiguration) -> None:
        """Initialize with LLM provider configuration.

        Args:
            config: Non-sensitive integration configuration containing
                provider_hint and optional base_url.

        """
        self._config = config
        self._provider = _get_provider(config.provider_hint)

    async def _do_get(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
        params: dict[str, str] | None = None,
        *,
        timeout_seconds: int | None = None,
        allow_absent_statuses: frozenset[int] | None = None,
    ) -> tuple[bool, str | None, HealthCheckErrorType | None, httpx.Response | None]:
        """Execute a single GET request with standardized error handling.

        ``allow_absent_statuses`` HTTP codes are treated as success (used by
        the credential probe when GET /key is not implemented).

        Returns:
            (success, error_msg, error_type, response) tuple.
            On failure, response is None.

        """
        success = True
        error_msg: str | None = None
        error_type: HealthCheckErrorType | None = None
        result_response: httpx.Response | None = None

        try:
            result_response = await client.get(url, headers=headers, params=params)
            result_response.raise_for_status()
            logger.debug(
                "Received LLM HTTP response",
                provider=self._config.provider_hint,
                status_code=result_response.status_code,
                url=url,
            )

        except (TimeoutError, httpx.TimeoutException):
            success = False
            error_msg = f"Connection timed out after {timeout_seconds}s" if timeout_seconds else "Connection timed out"
            error_type = HealthCheckErrorType.TIMEOUT
            logger.warning(
                "LLM request timed out",
                provider=self._config.provider_hint,
                timeout_seconds=timeout_seconds,
            )

        except HTTPStatusError as exc:
            if allow_absent_statuses and exc.response.status_code in allow_absent_statuses:
                logger.debug(
                    "LLM credential probe endpoint absent",
                    provider=self._config.provider_hint,
                    status_code=exc.response.status_code,
                    url=url,
                )
                return True, None, None, exc.response
            success = False
            error_type, error_msg = classify_http_error([exc])
            logger.warning(
                "LLM request HTTP error",
                provider=self._config.provider_hint,
                error_type=error_type.value,
                status_code=exc.response.status_code,
            )

        except (ssl.SSLError, ssl.SSLCertVerificationError):
            success = False
            error_msg = "SSL/TLS verification failed"
            error_type = HealthCheckErrorType.SSL_ERROR
            logger.warning("LLM request SSL error", provider=self._config.provider_hint)

        except (httpx.ConnectError, ConnectionError, OSError):
            success = False
            error_msg = "Unable to connect to service"
            error_type = HealthCheckErrorType.CONNECTION_ERROR
            logger.warning("LLM request connection error", provider=self._config.provider_hint)

        except Exception:
            success = False
            error_msg = "Request failed unexpectedly"
            error_type = HealthCheckErrorType.CONNECTION_ERROR
            logger.exception("Unexpected error during LLM request", provider=self._config.provider_hint)

        return success, error_msg, error_type, result_response if success else None

    async def _confirm_credential(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        headers: dict[str, str],
        *,
        timeout_seconds: int,
    ) -> tuple[bool, str | None, HealthCheckErrorType | None]:
        """Prove the API key on an auth-gated path when the provider has one.

        Called after the models catalog returns 200. A public catalog must
        not mark a rejected key as healthy.
        """
        url = self._provider.build_credential_confirmation_url(base_url)
        if url is None:
            return True, None, None

        logger.debug(
            "Sending LLM credential confirmation request",
            provider=self._config.provider_hint,
            url=url,
        )
        success, error_msg, error_type, _ = await self._do_get(
            client,
            url,
            headers,
            timeout_seconds=timeout_seconds,
            allow_absent_statuses=_PROBE_ABSENT_STATUSES,
        )
        return success, error_msg, error_type

    def _next_page_params(self, response: httpx.Response) -> dict[str, str] | None:
        """Return query params for the next catalog page, or None if done or unparseable."""
        try:
            return self._provider.next_page_params(response.json())
        except (ValueError, KeyError, TypeError):
            return None

    async def _paginate_model_pages(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
        first_response: httpx.Response,
        timeout_seconds: int,
    ) -> tuple[bool, str | None, HealthCheckErrorType | None, list[httpx.Response]]:
        """Fetch remaining catalog pages after a successful first page."""
        responses = [first_response]
        response = first_response
        for page in range(1, _MAX_PAGINATION_PAGES):
            params = self._next_page_params(response)
            if params is None:
                break

            logger.debug(
                "Fetching next page of models",
                provider=self._config.provider_hint,
                page=page + 1,
            )
            success, error_msg, error_type, next_response = await self._do_get(
                client,
                url,
                headers,
                params,
                timeout_seconds=timeout_seconds,
            )
            if not success or next_response is None:
                return success, error_msg, error_type, []
            response = next_response
            responses.append(response)
        else:
            if self._next_page_params(response) is not None:
                logger.warning(
                    "Pagination cap reached, results may be incomplete",
                    provider=self._config.provider_hint,
                    max_pages=_MAX_PAGINATION_PAGES,
                )

        return True, None, None, responses

    async def _fetch_models(
        self,
        resolved_credential: dict[str, Any],
        timeout_seconds: int,
        *,
        paginate: bool = False,
        confirm_credential: bool = False,
    ) -> tuple[bool, str | None, HealthCheckErrorType | None, list[httpx.Response]]:
        """Hit the provider's models endpoint.

        Args:
            resolved_credential: extra_vars dict from InjectorResolver.resolve().
                Expected key is provider-specific (e.g. ``llm_api_key``).
            timeout_seconds: Maximum seconds to wait for the HTTP response.
            paginate: If True, follow pagination until exhausted (up to
                ``_MAX_PAGINATION_PAGES``). If False, make a single request.
            confirm_credential: If True, after the catalog 200 run the
                provider's auth-gated probe once (validate only), before
                any pagination.

        Returns:
            (success, error_msg, error_type, responses) tuple.
            On failure, responses is an empty list.

        """
        api_key = self._provider.resolve_api_key(resolved_credential)
        if not api_key:
            return False, "Authentication configuration is incomplete", HealthCheckErrorType.AUTH_FAILURE, []

        base_url = _resolve_base_url(self._config, self._provider)
        url = self._provider.build_models_url(base_url)
        headers = self._provider.build_headers(api_key)

        logger.debug(
            "Sending LLM models request",
            provider=self._config.provider_hint,
            url=url,
        )

        responses: list[httpx.Response] = []
        params: dict[str, str] | None = None

        verify = build_integration_httpx_verify(
            insecure_skip_tls_verify=self._config.insecure_skip_tls_verify,
            ca_certificate=self._config.ca_certificate,
        )

        async with httpx.AsyncClient(timeout=timeout_seconds, verify=verify) as client:
            success, error_msg, error_type, response = await self._do_get(
                client,
                url,
                headers,
                params,
                timeout_seconds=timeout_seconds,
            )
            if not success or response is None:
                return success, error_msg, error_type, []

            if confirm_credential:
                confirmed, confirm_error, confirm_type = await self._confirm_credential(
                    client,
                    base_url,
                    headers,
                    timeout_seconds=timeout_seconds,
                )
                if not confirmed:
                    return False, confirm_error, confirm_type, []

            if paginate:
                return await self._paginate_model_pages(
                    client,
                    url,
                    headers,
                    response,
                    timeout_seconds,
                )
            responses.append(response)

        return True, None, None, responses

    async def validate(
        self,
        resolved_credential: dict[str, Any],
        timeout_seconds: int,
    ) -> ValidateResult:
        """Check provider reachability and credential acceptance.

        Args:
            resolved_credential: Decrypted credential extra_vars dict.
            timeout_seconds: HTTP request timeout.

        """
        success, error_msg, error_type, _ = await self._fetch_models(
            resolved_credential,
            timeout_seconds,
            confirm_credential=True,
        )
        if success:
            logger.info("LLM validate succeeded", provider=self._config.provider_hint)
        return ValidateResult(
            success=success,
            checked_at=datetime.now(UTC),
            error=error_msg,
            error_type=error_type,
        )

    async def discover(
        self,
        resolved_credential: dict[str, Any],
        timeout_seconds: int,
    ) -> DiscoverResult:
        """Discover available models from the LLM provider.

        Args:
            resolved_credential: Decrypted credential extra_vars dict.
            timeout_seconds: HTTP request timeout.

        """
        success, error_msg, error_type, responses = await self._fetch_models(
            resolved_credential,
            timeout_seconds,
            paginate=True,
        )
        discovered: list[DiscoveredLLMModel] | None = None

        if success and responses:
            try:
                discovered = []
                for response in responses:
                    discovered.extend(self._provider.parse_models_response(response.json()))
            except (ValueError, KeyError, TypeError, AttributeError):
                success = False
                discovered = None
                error_msg = "Invalid JSON response from provider"
                error_type = HealthCheckErrorType.CONNECTION_ERROR
                logger.warning("LLM discover JSON parse error", provider=self._config.provider_hint)
            else:
                logger.info(
                    "LLM discover succeeded",
                    provider=self._config.provider_hint,
                    model_count=len(discovered),
                )

        return DiscoverResult(
            success=success,
            checked_at=datetime.now(UTC),
            error=error_msg,
            error_type=error_type,
            discovered_models=discovered,
        )


register_health_check_adapter(
    IntegrationType.LLM_PROVIDER,
    lambda c: LLMProviderAdapter(cast("LLMProviderConfiguration", c)),
)
