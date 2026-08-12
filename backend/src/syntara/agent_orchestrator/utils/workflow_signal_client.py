"""Client for sending signals to Temporal workflows.

This module provides a centralized client for agent orchestrator services
to send activity completion signals (both success and failure) to workflows.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import structlog

from syntara.core.tls.http_client import build_internal_http_client

logger = structlog.stdlib.get_logger(__name__)

_SIGNAL_HTTP_TIMEOUT_SECONDS = 10.0


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
