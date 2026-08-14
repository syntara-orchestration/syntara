"""HTTP request activity for v2 workflows."""

import base64
import json
import time
from http import HTTPStatus
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog
from pydantic import ValidationError
from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.core.lib.url_validation import validate_url_no_ssrf
from syntara.credentials.lib.auth_types import AUTH_TYPE_API_KEY, AUTH_TYPE_BASIC, AUTH_TYPE_BEARER, AUTH_TYPE_URL
from syntara.workflows.workflow_engine import constants
from syntara.workflows.workflow_engine.models.workflow_definition import (
    ActivityName,
    APIExecutorParameters,
    HttpRequestOutput,
)
from syntara.workflows.workflow_engine.utils.credential_scrubber import ensure_resolved_credentials_dict

from .common import HEARTBEAT_STOP_MONITOR, ActivityExecutionError, is_retryable_http_status

logger = structlog.stdlib.get_logger(__name__)


def _add_credential_auth_headers(headers: dict[str, Any], extra_vars: dict[str, Any]) -> None:
    """Apply authentication from Nexus credential system.

    Raises ActivityExecutionError if credential values are empty.
    """
    auth_type = extra_vars.get("auth_type", "")

    if auth_type == AUTH_TYPE_BEARER:
        token = extra_vars.get("bearer_token", "")
        if not token:
            msg = "Bearer credential resolved but token is empty. Re-save the credential with a valid token."
            raise ActivityExecutionError(msg)
        headers["Authorization"] = f"Bearer {token}"

    elif auth_type == AUTH_TYPE_BASIC:
        username = extra_vars.get("basic_username", "")
        password = extra_vars.get("basic_password", "")
        if not username:
            msg = "Basic auth credential resolved but username is empty. Re-save the credential."
            raise ActivityExecutionError(msg)
        encoded = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
        headers["Authorization"] = f"Basic {encoded}"

    elif auth_type == AUTH_TYPE_API_KEY:
        api_key = extra_vars.get("api_key", "") or extra_vars.get("llm_api_key", "")
        if not api_key:
            msg = "API key credential resolved but key is empty. Re-save the credential."
            raise ActivityExecutionError(msg)
        headers["X-API-Key"] = api_key

    elif auth_type:
        msg = f"Unknown credential auth_type: '{auth_type}'. Check the credential type configuration."
        raise ActivityExecutionError(msg)

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
        resolved_creds = ensure_resolved_credentials_dict(resolved_creds)
        extra_vars = resolved_creds.get("extra_vars", {})
        if extra_vars.get("auth_type") == AUTH_TYPE_URL:
            secret_url = extra_vars.get("secret_url", "")
            if not secret_url:
                msg = "Secret URL credential resolved but URL is empty. Re-save the credential with a valid URL."
                raise ActivityExecutionError(msg)
            parsed = urlparse(secret_url)
            if not parsed.scheme or parsed.scheme not in ("http", "https"):
                msg = "Secret URL must use http:// or https:// scheme."
                raise ActivityExecutionError(msg)
            request_url = secret_url
            url_from_credential = True
        else:
            _add_credential_auth_headers(headers, extra_vars)

    if not request_url:
        msg = "No URL provided. Set a URL in the node configuration or attach a Secret URL credential."
        raise ApplicationError(msg, type="ConfigurationError", non_retryable=True)

    return request_url, url_from_credential


@activity.defn(name=ActivityName.HTTP_REQUEST)
async def execute_http_request_activity(
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
) -> dict[str, Any]:
    """Execute HTTP request node for v2 workflows.

    Returns normalized structure with output portion (no control needed for executor nodes).
    Output mapping is applied internally before returning to avoid storing suppressed fields in Temporal.

    Args:
        input_config: Resolved node configuration (templates already resolved)
        output_config: Output mapping configuration (field_name -> template expression)
                       None = return full result, {} = suppress all, {...} = extract specific fields

    Returns:
        {
            "output": {
                "status": "completed",
                "status_code": 200,   # Only if not suppressed by output_config
                "body": {...},        # Only if not suppressed by output_config
                ...
            }
        }

    """
    activity.heartbeat({HEARTBEAT_STOP_MONITOR: True})

    # Validate config via Pydantic model
    try:
        config = APIExecutorParameters.model_validate(input_config)
    except ValidationError as exc:
        # Log full details internally; omit values from user-facing message (may contain credentials)
        logger.warning("HTTP activity config validation failed", error_count=exc.error_count())
        fields = [str(e["loc"]) for e in exc.errors()]
        msg = f"Invalid configuration: {exc.error_count()} error(s) in fields {fields}"
        raise ApplicationError(msg, type="ValidationError", non_retryable=True) from None

    headers = dict(config.headers)
    request_url, url_from_credential = _resolve_credentials_and_url(input_config, config, headers)

    # SSRF validation: reject private/internal IPs and cloud metadata endpoints
    try:
        validate_url_no_ssrf(request_url)
    except ValueError as exc:
        raise ApplicationError(str(exc), type="SSRFValidationError", non_retryable=True) from None

    timeout_seconds = int(input_config.get(constants.ENGINE_TIMEOUT_SECONDS_KEY, 30))

    start_time = time.time()

    try:
        async with httpx.AsyncClient(follow_redirects=False) as client:
            response = await client.request(
                method=config.method.value,
                url=request_url,
                headers=headers,
                params=config.query_params,
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
            raise ApplicationError(  # noqa: TRY301
                msg,
                {"output": output.dump(output_config)},
                type="HTTPError",
                non_retryable=not is_retryable_http_status(response.status_code),
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
        return {"output": output.dump(output_config)}

    except ApplicationError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("HTTP request activity failed", error_type=type(exc).__name__)
        msg = f"HTTP request failed: {type(exc).__name__}"
        raise ApplicationError(msg, type=type(exc).__name__, non_retryable=True) from None
