"""HTTP request activity owned by the HTTP request domain."""

import base64
import json
import time
from enum import Enum
from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qsl, urlparse, urlsplit, urlunsplit

import httpx
import structlog
from pydantic import BaseModel, Field, ValidationError, field_validator

from syntara.core.lib.url_validation import validate_url_no_ssrf
from syntara.credentials.lib.auth_types import AUTH_TYPE_API_KEY, AUTH_TYPE_BASIC, AUTH_TYPE_BEARER, AUTH_TYPE_URL
from syntara.workflow_runtime.contracts import ActivityContext, ActivityError, Completed

DEFAULT_TIMEOUT_SECONDS = 30
RETRYABLE_HTTP_STATUS_CODES = frozenset({429, 502, 503, 504})


class HTTPMethod(str, Enum):
    """Methods accepted by the HTTP request node."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class APIExecutorParameters(BaseModel):
    """Minimal engine-independent HTTP request configuration."""

    method: HTTPMethod
    url: str | None = None
    headers: dict[str, Any] = Field(default_factory=dict)
    body: dict[str, Any] | str | None = None
    query_params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("url")
    @classmethod
    def validate_url_scheme(cls, value: str | None) -> str | None:
        """Restrict explicit URLs to HTTP(S)."""
        if value is not None and urlparse(value).scheme not in ("", "http", "https"):
            msg = "Only http:// and https:// URLs are supported"
            raise ValueError(msg)
        return value


class HttpRequestOutput(BaseModel):
    """Normalized HTTP response returned by the domain activity."""

    status_code: int | None = None
    body: Any = None
    headers: dict[str, Any] | None = None
    elapsed: float | None = None

    def dump(self, output_config: dict[str, str] | None) -> dict[str, Any]:
        """Serialize the response and apply simple result-field mappings."""
        result = self.model_dump()
        if output_config is None:
            return result
        if not output_config:
            return {}
        mapped: dict[str, Any] = {}
        for output_key, expression in output_config.items():
            field_name = expression.removeprefix("${result.").removesuffix("}")
            mapped[output_key] = result.get(field_name)
        return mapped


logger = structlog.stdlib.get_logger(__name__)


def _ensure_resolved_credentials_dict(value: object) -> dict[str, Any]:
    """Normalize serialized credential payloads without an engine dependency."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _resolve_httpx_params(request_url: str, query_params: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    """Return httpx url/params; empty query_params → None so URL query is preserved."""
    if not query_params:
        return request_url, None

    split = urlsplit(request_url)
    url_params = dict(parse_qsl(split.query, keep_blank_values=True))
    merged = {**url_params, **query_params}
    clean_url = urlunsplit((split.scheme, split.netloc, split.path, "", split.fragment))
    return clean_url, merged


def _add_credential_auth_headers(headers: dict[str, Any], extra_vars: dict[str, Any]) -> None:
    """Apply authentication from Syntara credential system.

    Raises ActivityError if credential values are empty.
    """
    auth_type = extra_vars.get("auth_type", "")

    if auth_type == AUTH_TYPE_BEARER:
        token = extra_vars.get("bearer_token", "")
        if not token:
            msg = "Bearer credential resolved but token is empty. Re-save the credential with a valid token."
            raise ActivityError(msg, code="CredentialError")
        headers["Authorization"] = f"Bearer {token}"

    elif auth_type == AUTH_TYPE_BASIC:
        username = extra_vars.get("basic_username", "")
        password = extra_vars.get("basic_password", "")
        if not username:
            msg = "Basic auth credential resolved but username is empty. Re-save the credential."
            raise ActivityError(msg, code="CredentialError")
        encoded = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
        headers["Authorization"] = f"Basic {encoded}"

    elif auth_type == AUTH_TYPE_API_KEY:
        api_key = extra_vars.get("api_key", "") or extra_vars.get("llm_api_key", "")
        if not api_key:
            msg = "API key credential resolved but key is empty. Re-save the credential."
            raise ActivityError(msg, code="CredentialError")
        headers["X-API-Key"] = api_key

    elif auth_type:
        msg = f"Unknown credential auth_type: '{auth_type}'. Check the credential type configuration."
        raise ActivityError(msg, code="CredentialError")

    else:
        logger.warning("Credential resolved but auth_type is missing from extra_vars — proceeding without auth")


def _resolve_credentials_and_url(
    input_config: dict[str, Any],
    config: APIExecutorParameters,
    headers: dict[str, Any],
) -> tuple[str, bool]:
    """Resolve credentials and determine the request URL.

    For non-URL credential types, mutates ``headers`` in place with auth headers.

    Returns (request_url, url_from_credential).
    """
    request_url = config.url
    url_from_credential = False
    resolved_creds = input_config.get("_resolved_credentials")
    if resolved_creds:
        resolved_creds = _ensure_resolved_credentials_dict(resolved_creds)
        extra_vars = resolved_creds.get("extra_vars", {})
        if extra_vars.get("auth_type") == AUTH_TYPE_URL:
            if config.url:
                msg = (
                    "Conflict: node has an explicit URL in parameters and a Secret URL credential attached. "
                    "Remove the URL from node parameters or use a different credential type."
                )
                raise ActivityError(msg, code="CredentialError")
            secret_url = extra_vars.get("secret_url", "")
            if not secret_url:
                msg = "Secret URL credential resolved but URL is empty. Re-save the credential with a valid URL."
                raise ActivityError(msg, code="CredentialError")
            parsed = urlparse(secret_url)
            if not parsed.scheme or parsed.scheme not in ("http", "https"):
                msg = "Secret URL must use http:// or https:// scheme."
                raise ActivityError(msg, code="CredentialError")
            request_url = secret_url
            url_from_credential = True
        else:
            _add_credential_auth_headers(headers, extra_vars)

    if not request_url:
        msg = "No URL provided. Set a URL in the node configuration or attach a Secret URL credential."
        raise ActivityError(msg, code="ConfigurationError")

    return request_url, url_from_credential


async def execute_http_request_activity(
    input_config: dict[str, Any],
    context: ActivityContext,
) -> Completed:
    """Execute an HTTP request and return a completed domain result.

    Returns normalized structure with output portion (no control needed for executor nodes).
    Output mapping is applied internally before returning to avoid storing suppressed fields in Temporal.

    Args:
        input_config: Resolved node configuration (templates already resolved)
                       The optional ``output_config`` is carried in this mapping.
        context: Runtime identity for the activity invocation.

    Returns:
        Completed containing the normalized HTTP response fields.

    """
    del context  # The request is completed synchronously and needs no runtime state.

    # Validate config via Pydantic model
    try:
        config = APIExecutorParameters.model_validate(input_config)
    except ValidationError as exc:
        # Log full details internally; omit values from user-facing message (may contain credentials)
        logger.warning("HTTP activity config validation failed", error_count=exc.error_count())
        fields = [str(e["loc"]) for e in exc.errors()]
        msg = f"Invalid configuration: {exc.error_count()} error(s) in fields {fields}"
        raise ActivityError(msg, code="ValidationError") from None

    headers = dict(config.headers)
    request_url, url_from_credential = _resolve_credentials_and_url(input_config, config, headers)

    # SSRF validation: reject private/internal IPs and cloud metadata endpoints
    try:
        validate_url_no_ssrf(request_url)
    except ValueError as exc:
        raise ActivityError(str(exc), code="SSRFValidationError") from None

    timeout_seconds = int(input_config.get("_engine_timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    request_url, request_params = _resolve_httpx_params(request_url, config.query_params)

    start_time = time.time()

    try:
        async with httpx.AsyncClient(follow_redirects=False) as client:
            response = await client.request(
                method=config.method.value,
                url=request_url,
                headers=headers,
                params=request_params,
                json=config.body if isinstance(config.body, dict) else None,
                content=config.body if isinstance(config.body, str) else None,
                timeout=float(timeout_seconds),
            )

        elapsed = time.time() - start_time

        # Detect HTTP errors (4xx/5xx)
        if response.status_code >= HTTPStatus.BAD_REQUEST:
            safe_url = "[REDACTED]" if url_from_credential else request_url.split("?")[0]
            msg = f"HTTP {response.status_code} {response.reason_phrase} (url={safe_url}, elapsed={elapsed:.2f}s)"
            max_error_body_length = 4096
            try:
                raw_body = response.text[:max_error_body_length]
                error_body: Any = json.loads(raw_body) if raw_body.strip() else raw_body
            except (json.JSONDecodeError, ValueError):
                error_body = raw_body
            output = HttpRequestOutput(
                status_code=response.status_code,
                body=error_body,
                headers=dict(response.headers),
                elapsed=elapsed,
            )
            raise ActivityError(  # noqa: TRY301
                msg,
                code="HTTPError",
                retryable=response.status_code in RETRYABLE_HTTP_STATUS_CODES,
            )

        # Try to parse JSON response
        try:
            body_data = response.json()
        except Exception:  # noqa: BLE001
            body_data = response.text

        output = HttpRequestOutput(
            status_code=response.status_code,
            body=body_data,
            headers=dict(response.headers),
            elapsed=elapsed,
        )
        return Completed(output.dump(input_config.get("output_config")))
    except ActivityError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("HTTP request activity failed", error_type=type(exc).__name__)
        msg = f"HTTP request failed: {type(exc).__name__}"
        raise ActivityError(msg, code=type(exc).__name__) from None
