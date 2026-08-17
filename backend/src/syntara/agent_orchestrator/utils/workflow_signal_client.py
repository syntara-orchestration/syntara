"""Client for sending signals to Temporal workflows.

This module provides a centralized client for agent orchestrator services
to send activity completion signals (both success and failure) to workflows.
"""

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import httpx
import structlog

from syntara.core.tls.http_client import build_internal_http_client

logger = structlog.stdlib.get_logger(__name__)

_SIGNAL_HTTP_TIMEOUT_SECONDS = 10.0


def validate_signal_url(callback_url: str) -> None:
    """Validate that callback_url points to a well-formed internal signal endpoint.

    Defense-in-depth against SSRF: validates that the URL path has the
    canonical ``/executions/{id}/activities/{id}/signal`` shape by
    round-tripping through ``generate_activity_signal_url``.  Host-level
    SSRF prevention is handled by ``_sanitize_context_data`` (strips
    ``callback_url`` from non-cert-authenticated requests) and by
    ``build_internal_http_client`` (mTLS CA verification).

    Raises:
        ValueError: If the URL does not match the expected signal endpoint.

    """
    url_parsed = urlparse(callback_url)

    if url_parsed.scheme not in ("https", "http"):
        logger.critical(
            "SECURITY: signal callback URL has invalid scheme",
            callback_url=callback_url,
        )
        msg = "Signal callback URL must use http or https scheme"
        raise ValueError(msg)

    if url_parsed.query or url_parsed.fragment:
        logger.critical(
            "SECURITY: signal callback URL contains query string or fragment",
            callback_url=callback_url,
        )
        msg = "Signal callback URL must not contain query string or fragment"
        raise ValueError(msg)

    parts = url_parsed.path.strip("/").split("/")

    try:
        exec_idx = parts.index("executions")
        act_idx = parts.index("activities")
        sig_idx = parts.index("signal")
    except ValueError:
        logger.critical(
            "SECURITY: signal callback URL path is not a valid signal endpoint — potential SSRF",
            callback_url=callback_url,
        )
        msg = "Signal callback URL path is not a valid signal endpoint"
        raise ValueError(msg) from None

    if act_idx != exec_idx + 2 or sig_idx != act_idx + 2 or sig_idx != len(parts) - 1:
        logger.critical(
            "SECURITY: signal callback URL path structure is invalid",
            callback_url=callback_url,
        )
        msg = "Signal callback URL path is not a valid signal endpoint"
        raise ValueError(msg)

    try:
        UUID(parts[exec_idx + 1])
    except ValueError:
        logger.critical(
            "SECURITY: signal callback URL has invalid execution ID",
            callback_url=callback_url,
        )
        msg = "Signal callback URL path is not a valid signal endpoint"
        raise ValueError(msg) from None

    activity_id = parts[act_idx + 1]
    if not activity_id:
        logger.critical(
            "SECURITY: signal callback URL has empty activity ID",
            callback_url=callback_url,
        )
        msg = "Signal callback URL path is not a valid signal endpoint"
        raise ValueError(msg)


async def _post_signal(callback_url: str, payload: dict[str, Any], invocation_id: UUID) -> None:
    """POST a signal payload to a callback URL with mTLS auth."""
    async with build_internal_http_client(timeout=_SIGNAL_HTTP_TIMEOUT_SECONDS) as client:
        response = await client.post(
            callback_url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        logger.info(
            "Signal HTTP response received",
            invocation_id=invocation_id,
            status_code=response.status_code,
        )
        response.raise_for_status()


class WorkflowSignalClient:
    """Client for sending activity signals to Temporal workflows.

    This client handles both success and failure signals, providing a
    consistent interface for agent orchestrator services to communicate
    activity results back to workflows.
    """

    @staticmethod
    async def send_success_signal(
        callback_url: str,
        invocation_id: UUID,
        result: dict[str, Any],
    ) -> None:
        """Send success signal to workflow with agent execution result.

        Args:
            callback_url: Workflow callback URL
            invocation_id: Invocation UUID
            result: Agent execution result containing content and metadata

        Raises:
            httpx.HTTPStatusError: If workflow rejects the signal
            httpx.RequestError: If connection fails
            httpx.TimeoutException: If request times out

        """
        validate_signal_url(callback_url)

        signal_payload = {
            "signal_data": {
                "id": str(invocation_id),
                "status": "completed",
                "result": {
                    "content": result.get("content"),
                    "response_metadata": result.get("response_metadata", {}),
                    "structured_output_metadata": result.get("structured_output_metadata"),
                    "agent_trace": result.get("agent_trace"),
                    "tools_used": result.get("tools_used"),
                    "tokens_used": result.get("tokens_used"),
                    # Aggregated name/count for the execution UI — do not forward raw
                    # tool_calls (may include args/secrets); agent_trace carries step detail.
                    "used_tools": result.get("used_tools"),
                },
                "timestamp": datetime.now(UTC).isoformat(),
                "agent_type": "GenericAgent",
            }
        }

        logger.info(
            "SUCCESS SIGNAL: Sending to callback",
            callback_url=callback_url,
            invocation_id=invocation_id,
        )

        await _post_signal(callback_url, signal_payload, invocation_id)

        logger.info(
            "SUCCESS SIGNAL: Sent successfully",
            invocation_id=invocation_id,
            callback_url=callback_url,
        )

    @staticmethod
    async def send_failure_signal(
        callback_url: str | None,
        invocation_id: UUID,
        error: Exception,
    ) -> None:
        """Send failure signal to workflow (best-effort).

        This method swallows all exceptions to avoid cascading failures.
        Failure signals are informational and should not block error handling.

        Args:
            callback_url: Workflow callback URL (None to skip)
            invocation_id: Invocation UUID
            error: Exception that caused the failure

        """
        if not callback_url:
            logger.debug(
                "No callback_url for invocation, skipping failure signal",
                invocation_id=invocation_id,
            )
            return

        # Validate URL before the best-effort block so security violations
        # propagate instead of being silently swallowed.
        validate_signal_url(callback_url)

        signal_payload = {
            "signal_data": {
                "id": str(invocation_id),
                "status": "failed",
                "error": {
                    "message": str(error),
                    "error_type": type(error).__name__,
                },
                "timestamp": datetime.now(UTC).isoformat(),
                "agent_type": "GenericAgent",
            }
        }

        logger.info(
            "FAILURE SIGNAL: Sending to callback",
            callback_url=callback_url,
            invocation_id=invocation_id,
            error_type=type(error).__name__,
        )

        try:
            await _post_signal(callback_url, signal_payload, invocation_id)

            logger.info(
                "FAILURE SIGNAL: Sent successfully",
                invocation_id=invocation_id,
                callback_url=callback_url,
            )
        except (httpx.RequestError, httpx.HTTPStatusError, httpx.TimeoutException):
            logger.exception(
                "Failed to send failure signal",
                invocation_id=invocation_id,
                callback_url=callback_url,
            )
        except Exception:
            logger.exception(
                "Unexpected error sending failure signal",
                invocation_id=invocation_id,
            )
