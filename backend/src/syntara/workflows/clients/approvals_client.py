"""REST client for workflow component to connect to the Approvals API.

This client provides integration with the Approvals service, enabling the
workflow engine to create approval requests, list them by execution, and
batch cancel when a workflow is cancelled. Uses 3 retries with exponential
backoff per research.md (Workflow -> Approvals).

Follows the dict-based interface pattern established by AgentOrchestratorClient
to maintain domain boundary separation between workflows and approvals.
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


class ApprovalsApiClientError(WorkflowError):
    """Base exception for Approvals API client errors."""

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


class ApprovalsApiClientConnectionError(ApprovalsApiClientError):
    """Exception raised when connection to Approvals API fails after retries."""


class ApprovalsApiClient:
    """HTTP client for Approvals API used by the workflow component.

    Supports:
    - Creating a new approval request (POST /approvals)
    - Listing approval requests filtered by execution_id (GET /approvals)
    - Batch cancelling approval requests (POST /approvals/batch)

    Uses 3 retries with exponential backoff for transient failures.
    Follows AgentOrchestratorClient patterns (async context manager, retry logic, dict-based interface).
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000/api/v1",
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_backoff_base: float = 1.0,
    ) -> None:
        """Initialize Approvals API client.

        Args:
            base_url: Approvals API base URL.
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

        logger.debug("Initialized Approvals API client", base_url=self.base_url)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.http_client.aclose()
        logger.debug("Closed Approvals API client")

    async def __aenter__(self) -> "ApprovalsApiClient":
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
        """Convert errors to ApprovalsApiClientError variants."""
        if isinstance(error, httpx.ConnectError | httpx.TimeoutException):
            msg = f"Failed to connect to Approvals API after {self.max_retries} attempts"
            raise ApprovalsApiClientConnectionError(msg, details=str(error)) from error
        if isinstance(error, httpx.HTTPStatusError):
            msg = f"Approvals API HTTP {error.response.status_code}"
            raise ApprovalsApiClientError(
                msg, status_code=error.response.status_code, details=error.response.text
            ) from error
        if isinstance(error, ApprovalsApiClientError):
            raise error
        raise ApprovalsApiClientError(str(error), details=str(error)) from error

    async def _request_with_retry[T](  # noqa: RET503
        self,
        operation: str,
        request_fn: Callable[[], Awaitable[T]],
        **log_context: str | int,
    ) -> T:
        """Execute an async request with retry logic.

        Args:
            operation: Name for log messages (e.g. "create", "list", "batch cancel")
            request_fn: Async callable that performs the HTTP request and returns parsed result
            **log_context: Extra fields to include in retry warning logs

        Returns:
            Result from request_fn on success.

        Raises:
            ApprovalsApiClientConnectionError: If connection fails after retries
            ApprovalsApiClientError: On 4xx/5xx or invalid response

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
                    "Approvals API request failed, retrying",
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

    async def create_approval(self, request_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new approval request.

        Args:
            request_data: Approval creation request payload as a dict.

        Returns:
            Created approval request as a dict.

        Raises:
            ApprovalsApiClientConnectionError: If connection fails after retries
            ApprovalsApiClientError: On 4xx/5xx or invalid response

        """

        async def _do_create() -> dict[str, Any]:
            response = await self.http_client.post("/approvals", json=request_data, timeout=self.timeout)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            logger.info(
                "Created approval request",
                approval_id=data.get("id"),
                execution_id=request_data.get("execution_id"),
                approval_node_id=request_data.get("approval_node_id"),
            )
            return data

        return await self._request_with_retry("create", _do_create)

    async def _get_approvals_page(
        self,
        execution_id: UUID,
        status: str | None,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Fetch one page of approvals (with retries)."""
        params: dict[str, str | int] = {
            "execution_id": str(execution_id),
            "limit": limit,
        }
        if status is not None:
            params["status"] = status
        if cursor is not None:
            params["cursor"] = cursor

        async def _do_list() -> tuple[list[dict[str, Any]], str | None]:
            response = await self.http_client.get("/approvals", params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            resources_data: list[dict[str, Any]] = data.get("resources") or []
            next_cursor: str | None = data.get("next")
            return (resources_data, next_cursor)

        return await self._request_with_retry("list", _do_list, execution_id=str(execution_id))

    async def list_approvals_by_execution(
        self,
        execution_id: UUID,
        status: str | None = "pending",
        limit_per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch approval requests filtered by execution_id.

        Paginates internally and returns all matching approvals.

        Args:
            execution_id: Workflow execution ID to filter by
            status: Optional status filter (default 'pending'). None = no filter.
            limit_per_page: Page size for each request.

        Returns:
            List of approval request dicts.

        """
        resources: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            page, next_cursor = await self._get_approvals_page(execution_id, status, limit_per_page, cursor)
            resources.extend(page)
            if not next_cursor:
                break
            cursor = next_cursor

        logger.debug(
            "Listed approvals by execution",
            execution_id=str(execution_id),
            status=status,
            count=len(resources),
        )
        return resources

    async def batch_cancel(
        self,
        approval_ids: list[UUID],
        notes: str = "Workflow execution was cancelled",
    ) -> dict[str, Any]:
        """Batch cancel approval requests.

        Used when a workflow execution is cancelled to clean up pending approvals.
        Returns empty result immediately if approval_ids is empty.

        Args:
            approval_ids: List of approval request IDs to cancel
            notes: Note to attach to each cancellation

        Returns:
            Batch response dict with results, total_success, and total_failed.

        """
        if not approval_ids:
            return {"results": [], "total_success": 0, "total_failed": 0}

        decisions = [{"approval_id": str(aid), "status": "cancelled", "notes": notes} for aid in approval_ids]
        body = {"decisions": decisions}

        async def _do_batch() -> dict[str, Any]:
            response = await self.http_client.post("/approvals/batch", json=body, timeout=self.timeout)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            logger.info(
                "Batch cancel approvals completed",
                approval_count=len(approval_ids),
                total_success=data.get("total_success"),
                total_failed=data.get("total_failed"),
            )
            return data

        return await self._request_with_retry("batch cancel", _do_batch, approval_count=len(approval_ids))

    async def batch_expire(
        self,
        approval_ids: list[UUID],
        notes: str = "Approval decision window expired",
    ) -> dict[str, Any]:
        """Batch expire approval requests.

        Used when an approval node's decision window times out.
        Returns empty result immediately if approval_ids is empty.

        Args:
            approval_ids: List of approval request IDs to expire
            notes: Note to attach to each expiration

        Returns:
            Batch response dict with results, total_success, and total_failed.

        """
        if not approval_ids:
            return {"results": [], "total_success": 0, "total_failed": 0}

        decisions = [{"approval_id": str(aid), "status": "expired", "notes": notes} for aid in approval_ids]
        body = {"decisions": decisions}

        async def _do_batch() -> dict[str, Any]:
            response = await self.http_client.post("/approvals/batch", json=body, timeout=self.timeout)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            logger.info(
                "Batch expire approvals completed",
                approval_count=len(approval_ids),
                total_success=data.get("total_success"),
                total_failed=data.get("total_failed"),
            )
            return data

        return await self._request_with_retry("batch expire", _do_batch, approval_count=len(approval_ids))
