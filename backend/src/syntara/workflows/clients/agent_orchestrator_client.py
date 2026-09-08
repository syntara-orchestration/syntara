"""Agent Orchestrator client for agent invocation.

This client provides integration with the Agent Orchestrator service (spec 002),
enabling agentic activity execution within workflows.
"""

import asyncio
import http
from enum import Enum
from types import TracebackType
from typing import Any
from uuid import uuid4

import httpx
import structlog

from syntara.core.tls.http_client import build_internal_http_client
from syntara.workflows.exceptions import WorkflowError

# Configure logger
logger = structlog.stdlib.get_logger(__name__)


class ErrorCode(str, Enum):
    """Structured error codes for programmatic error handling."""

    # Connection errors
    CONNECTION_FAILED = "CONNECTION_FAILED"
    TIMEOUT = "TIMEOUT"

    # HTTP errors
    HTTP_CLIENT_ERROR = "HTTP_CLIENT_ERROR"  # 4xx
    HTTP_SERVER_ERROR = "HTTP_SERVER_ERROR"  # 5xx

    # Response validation errors
    MISSING_FIELD = "MISSING_FIELD"
    INVALID_STATUS = "INVALID_STATUS"
    MISSING_RESULT = "MISSING_RESULT"
    MISSING_ERROR_MESSAGE = "MISSING_ERROR_MESSAGE"

    # Other errors
    INVALID_RESPONSE = "INVALID_RESPONSE"
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"


class AgentOrchestratorClientError(WorkflowError):
    """Base exception for Agent Orchestrator client errors.

    Attributes:
        code: Structured error code for programmatic handling
        message: Human-readable error message
        details: Optional additional error details

    """

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.UNEXPECTED_ERROR,
        details: str | None = None,
    ) -> None:
        """Initialize error with code and details.

        Args:
            message: Human-readable error message
            code: Structured error code
            details: Optional error details

        """
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


class AgentOrchestratorClientConnectionError(AgentOrchestratorClientError):
    """Exception raised when connection to Agent Orchestrator fails."""

    def __init__(self, message: str, details: str | None = None) -> None:
        """Initialize connection error.

        Args:
            message: Human-readable error message
            details: Optional error details

        """
        super().__init__(message, code=ErrorCode.CONNECTION_FAILED, details=details)


class AgentOrchestratorClient:
    """Client for Agent Orchestrator invocation.

    Provides methods to invoke agents and receive completed results.

    Attributes:
        base_url: Base URL for Agent Orchestrator API (e.g., http://localhost:8000/api/v1)
        timeout: Default timeout for HTTP requests in seconds
        max_retries: Maximum number of retry attempts for transient failures
        retry_backoff_base: Base delay for exponential backoff (seconds)

    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000/api/v1",
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_backoff_base: float = 1.0,
        on_behalf_of_user_id: str | None = None,
    ) -> None:
        """Initialize Agent Orchestrator client.

        Args:
            base_url: Base URL for Agent Orchestrator API
            timeout: Default timeout for HTTP requests in seconds
            max_retries: Maximum number of retry attempts
            retry_backoff_base: Base delay for exponential backoff
            on_behalf_of_user_id: Originating user UUID propagated via
                X-On-Behalf-Of header for created_by attribution.

        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff_base = retry_backoff_base

        headers: dict[str, str] = {}
        if on_behalf_of_user_id:
            headers["X-On-Behalf-Of"] = on_behalf_of_user_id
        self.http_client = build_internal_http_client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
            headers=headers,
        )

        logger.info("Initialized Agent Orchestrator client", base_url=self.base_url)

    async def close(self) -> None:
        """Close the HTTP client and clean up resources."""
        await self.http_client.aclose()
        logger.debug("Closed Agent Orchestrator client")

    async def __aenter__(self) -> "AgentOrchestratorClient":
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit."""
        await self.close()

    def _is_retryable_error(self, error: Exception) -> bool:
        """Check if an error should trigger a retry.

        Args:
            error: The exception to check

        Returns:
            True if the error is retryable, False otherwise

        """
        # Retry on connection and timeout errors
        if isinstance(error, httpx.ConnectError | httpx.TimeoutException):
            return True

        # Retry on 5xx server errors (transient), not 4xx client errors (permanent)
        if isinstance(error, httpx.HTTPStatusError):
            return error.response.status_code >= http.HTTPStatus.INTERNAL_SERVER_ERROR

        return False

    def _validate_invocation_response(self, result: dict[str, Any]) -> None:
        """Validate invocation response has required fields and valid state.

        Raises:
            AgentOrchestratorClientError: If response is invalid or incomplete

        """
        # Check required fields exist
        invocation_id = result.get("id")
        if not invocation_id:
            msg = "Agent Orchestrator response missing or invalid 'id'"
            raise AgentOrchestratorClientError(msg, code=ErrorCode.MISSING_FIELD, details=str(result))

        status = result.get("status")
        if not status:
            msg = f"Agent Orchestrator response missing 'status' (invocation_id={invocation_id})"
            raise AgentOrchestratorClientError(msg, code=ErrorCode.MISSING_FIELD, details=str(result))

        # Validate terminal status
        if status not in ("completed", "failed", "cancelled"):
            msg = f"Agent Orchestrator response has non-terminal status '{status}' (invocation_id={invocation_id})"
            raise AgentOrchestratorClientError(msg, code=ErrorCode.INVALID_STATUS, details=str(result))

        # For completed invocations, result should exist
        if status == "completed" and "result" not in result:
            msg = f"Completed invocation missing 'result' (invocation_id={invocation_id})"
            raise AgentOrchestratorClientError(msg, code=ErrorCode.MISSING_RESULT, details=str(result))

        # For failed invocations, error_message should exist
        if status == "failed" and not result.get("error_message"):
            msg = f"Failed invocation missing 'error_message' (invocation_id={invocation_id})"
            raise AgentOrchestratorClientError(msg, code=ErrorCode.MISSING_ERROR_MESSAGE, details=str(result))

    def _build_invocation_payload(
        self,
        prompt: str,
        user_id: str,
        session_id: str,
        agent: str | None,
        model: str | None,
        input_data: dict[str, Any] | None,
        file_ids: list[str] | None,
        metadata: dict[str, Any] | None,
        project_id: str,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Build the request payload for agent invocation.

        Args:
            prompt: Natural language prompt
            user_id: User identifier
            session_id: Session ID
            agent: Optional agent identifier
            model: Optional model identifier
            input_data: Optional input data
            file_ids: Optional list of file IDs
            metadata: Optional metadata (callback_url will be extracted to top level)
            project_id: Project ID to include in the payload
            timeout_seconds: Optional timeout in seconds for the agent execution

        Returns:
            Request payload dictionary

        """
        # Extract correlation data from metadata to put it at top level of contextData
        workflow_id = None
        activity_id = None
        activity_name = None
        execution_id = None
        callback_url = None
        if metadata:
            workflow_id = metadata.pop("workflow_id", None)
            activity_id = metadata.pop("activity_id", None)
            activity_name = metadata.pop("activity_name", None)
            execution_id = metadata.pop("execution_id", None)
            callback_url = metadata.pop("callback_url", None)
            # If metadata is now empty, set it to None so it doesn't appear in contextData
            if not metadata:
                metadata = None

        payload: dict[str, Any] = {
            "prompt": prompt,
            "createdBy": user_id,
            "sessionId": session_id,
            "contextData": {
                k: v
                for k, v in {
                    "input_data": input_data,
                    "file_ids": file_ids,
                    "model": model,
                    "agent": agent,
                    "workflow_id": workflow_id,
                    "activity_id": activity_id,
                    "activity_name": activity_name,
                    "execution_id": execution_id,
                    "callback_url": callback_url,
                    "timeout_seconds": timeout_seconds,
                    "metadata": metadata,
                }.items()
                if v is not None
            },
            "projectId": project_id,
        }
        return payload

    async def _attempt_invocation(
        self,
        payload: dict[str, Any],
        attempt: int,
    ) -> str:
        """Attempt a single invocation request.

        Args:
            payload: Request payload
            attempt: Current attempt number

        Returns:
            Invocation ID

        Raises:
            AgentOrchestratorClientError: If invocation ID is missing
            Exception: For HTTP errors

        """
        logger.debug("Retry attempt", attempt=attempt, max_retries=self.max_retries)

        response = await self.http_client.post(
            "/invocations",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        result = response.json()

        invocation_id = result.get("id")
        if not invocation_id:
            msg = "Agent Orchestrator response missing or invalid 'id'"
            raise AgentOrchestratorClientError(msg, code=ErrorCode.MISSING_FIELD, details=str(result))

        logger.info(
            "Invocation created",
            invocation_id=invocation_id,
            status=result.get("status"),
        )
        return str(invocation_id)

    def _handle_invocation_error(self, error: Exception) -> None:
        """Handle and convert invocation errors to appropriate exceptions.

        Args:
            error: The error to handle

        Raises:
            AgentOrchestratorClientConnectionError: For connection errors
            AgentOrchestratorClientError: For HTTP and other errors

        """
        if isinstance(error, httpx.ConnectError | httpx.TimeoutException):
            msg = f"Failed to connect after {self.max_retries} attempts"
            raise AgentOrchestratorClientConnectionError(msg, details=str(error)) from error

        if isinstance(error, httpx.HTTPStatusError):
            is_server_error = error.response.status_code >= http.HTTPStatus.INTERNAL_SERVER_ERROR
            code = ErrorCode.HTTP_SERVER_ERROR if is_server_error else ErrorCode.HTTP_CLIENT_ERROR
            response_text = error.response.text
            msg = f"HTTP {error.response.status_code} error"
            logger.error(
                "Agent Orchestrator HTTP error",
                status_code=error.response.status_code,
                response_body=response_text,
            )
            raise AgentOrchestratorClientError(msg, code=code, details=response_text) from error

        if isinstance(error, AgentOrchestratorClientError):
            raise error

        # Other errors
        msg = f"{type(error).__name__}: {error}"
        raise AgentOrchestratorClientError(msg, code=ErrorCode.UNEXPECTED_ERROR, details=str(error)) from error

    async def invoke_agent_async(
        self,
        prompt: str,
        user_id: str,
        project_id: str,
        session_id: str | None = None,
        agent: str | None = None,
        model: str | None = None,
        input_data: dict[str, Any] | None = None,
        file_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        timeout_seconds: int | None = None,
    ) -> str:
        """Invoke Agent Orchestrator asynchronously and return immediately with invocation ID.

        Unlike invoke_agent(), this method does not wait for the agent to complete.
        It creates the invocation and returns the invocation ID immediately.
        The agent orchestrator should call a callback URL when the agent completes.

        Args:
            prompt: Natural language prompt for the agent
            user_id: User identifier for authentication and audit
            project_id: Project ID to associate the invocation with
            session_id: Optional session ID for tracking conversation context (auto-generated if not provided)
            agent: Optional agent identifier for routing (included in metadata)
            model: Optional model identifier to use
            input_data: Optional input data for the agent
            file_ids: Optional list of file IDs to include as context
            metadata: Optional additional metadata (should include callback_url)
            timeout_seconds: Optional timeout in seconds for the agent execution

        Returns:
            str: The invocation ID for tracking

        Raises:
            AgentOrchestratorClientConnectionError: If connection fails after retries
            AgentOrchestratorClientError: For other invocation errors

        """
        session_id = session_id or str(uuid4())

        logger.info(
            "Invoking agent asynchronously",
            prompt_length=len(prompt),
            agent=agent,
            model=model,
            file_count=len(file_ids) if file_ids else 0,
        )

        # Build request payload
        payload = self._build_invocation_payload(
            prompt, user_id, session_id, agent, model, input_data, file_ids, metadata, project_id, timeout_seconds
        )

        # Invoke with retry logic for transient failures
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                return await self._attempt_invocation(payload, attempt)

            except Exception as e:  # noqa: BLE001 - Broad exception catch is intentional for retry logic
                # Determine if we should retry
                is_last_attempt = attempt == self.max_retries
                should_retry = self._is_retryable_error(e) and not is_last_attempt

                if not should_retry:
                    self._handle_invocation_error(e)

                # Retry with exponential backoff
                last_error = e
                backoff = self.retry_backoff_base * (2**attempt)
                logger.warning(
                    "Retryable error, retrying with backoff",
                    attempt=attempt,
                    max_retries=self.max_retries,
                    backoff_seconds=backoff,
                    error=str(e),
                )
                await asyncio.sleep(backoff)

        # Safeguard: Should never reach here due to is_last_attempt check above
        msg = "Unexpected error: exited retry loop without returning"
        raise AgentOrchestratorClientError(
            msg,
            code=ErrorCode.UNEXPECTED_ERROR,
            details=str(last_error) if last_error else None,
        ) from last_error

    async def cancel_invocation(self, invocation_id: str, reason: str = "Workflow timeout") -> None:
        """Cancel a running invocation (best-effort).

        Args:
            invocation_id: UUID of the invocation to cancel
            reason: Reason for cancellation

        """
        try:
            response = await self.http_client.post(
                f"/invocations/{invocation_id}/cancel",
                json={"reason": reason},
                timeout=self.timeout,
            )
            response.raise_for_status()
            logger.info("Invocation cancelled", invocation_id=invocation_id, reason=reason)
        except Exception:  # noqa: BLE001
            logger.warning(
                "Failed to cancel invocation (best-effort)",
                invocation_id=invocation_id,
                exc_info=True,
            )
