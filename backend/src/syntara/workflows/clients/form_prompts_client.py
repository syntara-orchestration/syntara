"""REST client for workflow component to connect to the Forms API.

This client provides integration with the Forms service, enabling the
workflow engine to create form prompts, list them by execution, and
batch update status when forms expire or workflows are cancelled.
Uses 3 retries with exponential backoff.

Follows the dict-based interface pattern established by AgentOrchestratorClient
to maintain domain boundary separation between workflows and forms.
"""

import asyncio
import http
from collections.abc import Awaitable, Callable
from types import TracebackType
from typing import Any, NoReturn
from uuid import UUID

import httpx
import structlog

from syntara.core.tls.http_client import build_internal_http_client
from syntara.workflows.exceptions import WorkflowError

logger = structlog.stdlib.get_logger(__name__)


class FormPromptsApiClientError(WorkflowError):
    """Base exception for Forms API client errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        details: str | None = None,
    ) -> None:
        """Initialize with message, optional status code and details."""
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class FormPromptsApiClientConnectionError(FormPromptsApiClientError):
    """Exception raised when connection to Forms API fails after retries."""


class FormPromptsApiClient:
    """HTTP client for Forms API used by the workflow component.

    Supports:
    - Creating a new form prompt (POST /form_prompts)
    - Listing form prompts filtered by execution_id (GET /form_prompts)
    - Batch expiring form prompts (POST /form_prompts/batch)
    - Batch cancelling form prompts (POST /form_prompts/batch)

    Uses 3 retries with exponential backoff for transient failures.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000/api/v1",
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_backoff_base: float = 1.0,
    ) -> None:
        """Initialize Forms API client.

        Args:
            base_url: Forms API base URL.
            timeout: HTTP request timeout in seconds.
            max_retries: Max retry attempts for transient errors.
            retry_backoff_base: Base delay for exponential backoff.

        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff_base = retry_backoff_base

        self.http_client = build_internal_http_client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
        )

        logger.debug("Initialized Forms API client", base_url=self.base_url)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.http_client.aclose()
        logger.debug("Closed Forms API client")

    async def __aenter__(self) -> "FormPromptsApiClient":
        """Enter async context manager."""
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: TracebackType | None,
    ) -> None:
        """Exit async context manager."""
        await self.close()

    def _is_retryable_error(self, error: Exception) -> bool:
        """Check if an error should trigger a retry."""
        if isinstance(error, httpx.ConnectError | httpx.TimeoutException):
            return True
        if isinstance(error, httpx.HTTPStatusError):
            return error.response.status_code >= http.HTTPStatus.INTERNAL_SERVER_ERROR
        return False

    def _handle_error(self, error: Exception) -> NoReturn:
        """Convert errors to FormPromptsApiClientError variants."""
        if isinstance(error, httpx.ConnectError | httpx.TimeoutException):
            msg = f"Failed to connect to Forms API after {self.max_retries} attempts"
            raise FormPromptsApiClientConnectionError(msg, details=str(error)) from error
        if isinstance(error, httpx.HTTPStatusError):
            msg = f"Forms API HTTP {error.response.status_code}"
            raise FormPromptsApiClientError(
                msg, status_code=error.response.status_code, details=error.response.text
            ) from error
        if isinstance(error, FormPromptsApiClientError):
            raise error
        raise FormPromptsApiClientError(str(error), details=str(error)) from error

    async def _request_with_retry[T](  # noqa: RET503
        self,
        operation: str,
        request_fn: Callable[[], Awaitable[T]],
        **log_context: str | int,
    ) -> T:
        """Execute an async request with retry logic.

        Args:
            operation: Name for log messages (e.g. "create", "list", "batch expire")
            request_fn: Async callable that performs the HTTP request and returns parsed result
            **log_context: Extra fields to include in retry warning logs

        Returns:
            Result from request_fn on success.

        Raises:
            FormPromptsApiClientConnectionError: If connection fails after retries
            FormPromptsApiClientError: On 4xx/5xx or invalid response

        """
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return await request_fn()
            except httpx.HTTPError as e:
                last_error = e
                if not self._is_retryable_error(e) or attempt == self.max_retries:
                    self._handle_error(e)
                backoff = self.retry_backoff_base * (2**attempt)
                logger.warning(
                    "Forms API request failed, retrying",
                    operation=operation,
                    attempt=attempt,
                    backoff_seconds=backoff,
                    error=str(e),
                    **log_context,
                )
                await asyncio.sleep(backoff)
            except Exception as e:  # noqa: BLE001
                # Non-HTTP errors (e.g., JSON decode) — wrap and raise immediately
                self._handle_error(e)

        # Defensive: unreachable since _handle_error always raises on final attempt
        self._handle_error(last_error or RuntimeError("Unexpected exit from retry loop"))

    async def create_form_prompt(self, request_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new form prompt.

        Args:
            request_data: Form prompt creation request payload as a dict.

        Returns:
            Created form prompt as a dict.

        Raises:
            FormPromptsApiClientConnectionError: If connection fails after retries
            FormPromptsApiClientError: On 4xx/5xx or invalid response

        """

        async def _do_create() -> dict[str, Any]:
            response = await self.http_client.post("/form_prompts", json=request_data, timeout=self.timeout)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            logger.info(
                "Created form prompt",
                prompt_id=data.get("id"),
                execution_id=request_data.get("execution_id"),
                prompt_node_id=request_data.get("prompt_node_id"),
            )
            return data

        return await self._request_with_retry("create", _do_create)

    async def _get_form_prompts_page(
        self,
        execution_id: UUID,
        status: str | None,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Fetch one page of form prompts (with retries)."""
        params: dict[str, str | int] = {
            "execution_id": str(execution_id),
            "limit": limit,
        }
        if status is not None:
            params["status"] = status
        if cursor is not None:
            params["cursor"] = cursor

        async def _do_list() -> tuple[list[dict[str, Any]], str | None]:
            response = await self.http_client.get("/form_prompts", params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            resources_data: list[dict[str, Any]] = data.get("resources") or []
            next_cursor: str | None = data.get("next")
            return (resources_data, next_cursor)

        return await self._request_with_retry("list", _do_list, execution_id=str(execution_id))

    async def list_form_prompts_by_execution(
        self,
        execution_id: UUID,
        status: str | None = "pending",
        limit_per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch form prompts filtered by execution_id.

        Paginates internally and returns all matching form prompts.

        Args:
            execution_id: Workflow execution ID to filter by
            status: Optional status filter (default 'pending'). None = no filter.
            limit_per_page: Page size for each request.

        Returns:
            List of form prompt dicts.

        """
        resources: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            page, next_cursor = await self._get_form_prompts_page(execution_id, status, limit_per_page, cursor)
            resources.extend(page)
            if not next_cursor:
                break
            cursor = next_cursor

        logger.debug(
            "Listed form prompts by execution",
            execution_id=str(execution_id),
            status=status,
            count=len(resources),
        )
        return resources

    async def batch_cancel(
        self,
        prompt_ids: list[UUID],
        notes: str = "Workflow execution was cancelled",
    ) -> dict[str, Any]:
        """Batch cancel form prompts.

        Used when a workflow execution is cancelled to clean up pending prompts.
        Returns empty result immediately if prompt_ids is empty.

        Args:
            prompt_ids: List of form prompt IDs to cancel
            notes: Note to attach to each cancellation

        Returns:
            Batch response dict with results, total_success, and total_failed.

        """
        if not prompt_ids:
            return {"results": [], "total_success": 0, "total_failed": 0}

        updates = [{"prompt_id": str(pid), "status": "cancelled", "notes": notes} for pid in prompt_ids]
        body = {"updates": updates}

        async def _do_batch() -> dict[str, Any]:
            response = await self.http_client.post("/form_prompts/batch", json=body, timeout=self.timeout)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            logger.info(
                "Batch cancel form prompts completed",
                prompt_count=len(prompt_ids),
                total_success=data.get("total_success"),
                total_failed=data.get("total_failed"),
            )
            return data

        return await self._request_with_retry("batch cancel", _do_batch, prompt_count=len(prompt_ids))

    async def batch_expire(
        self,
        prompt_ids: list[UUID],
        notes: str = "Form prompt response window expired",
    ) -> dict[str, Any]:
        """Batch expire form prompts.

        Used when a form_prompt node's response window times out.
        Returns empty result immediately if prompt_ids is empty.

        Args:
            prompt_ids: List of form prompt IDs to expire
            notes: Note to attach to each expiration

        Returns:
            Batch response dict with results, total_success, and total_failed.

        """
        if not prompt_ids:
            return {"results": [], "total_success": 0, "total_failed": 0}

        updates = [{"prompt_id": str(pid), "status": "expired", "notes": notes} for pid in prompt_ids]
        body = {"updates": updates}

        async def _do_batch() -> dict[str, Any]:
            response = await self.http_client.post("/form_prompts/batch", json=body, timeout=self.timeout)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            logger.info(
                "Batch expire form prompts completed",
                prompt_count=len(prompt_ids),
                total_success=data.get("total_success"),
                total_failed=data.get("total_failed"),
            )
            return data

        return await self._request_with_retry("batch expire", _do_batch, prompt_count=len(prompt_ids))
