"""Versioned HTTP client for the standalone Execution Plane service.

List requests mirror execution_plane.api.pagination and the filter controls in
execution_plane.api.list_queries. EP owns filter/sort validation and cursor
interpretation; this transport forwards their wire values unchanged.
"""

from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, Self, cast
from uuid import UUID, uuid4

import httpx
import jwt
from execution_plane_client.commands.control import CancelCommand
from execution_plane_client.protocol import MessageEnvelope, TransportReceipt

if TYPE_CHECKING:
    from collections.abc import Mapping

from syntara.auth.services.token_service import get_key_manager
from syntara.core.config.base import get_settings
from syntara.core.tls.http_client import build_internal_http_client

EP_CLIENT_ID = "syntara-orchestration"
EP_AUDIENCE = "execution-plane"
EP_TOKEN_LIFETIME_SECONDS = 300
EP_SCOPES = (
    "work.execute command.cancel cluster.register cluster.update cluster.delete "
    "execution_target.register execution_target.update execution_target.delete "
    "work-items:read execution-targets:read clusters:read"
)


class ExecutionPlaneError(RuntimeError):
    """Base exception for failed Execution Plane requests."""


class ExecutionPlaneUnavailableError(ExecutionPlaneError):
    """Raised when EP cannot accept or answer a request temporarily."""

    def __init__(self, message: str = "Execution Plane is unavailable") -> None:
        """Describe a retryable communication failure."""
        super().__init__(message)


class ExecutionPlaneRejectedError(ExecutionPlaneError):
    """Raised when EP rejects an invalid or unauthorized request."""

    def __init__(
        self,
        message: str = "Execution Plane rejected the request",
        *,
        status_code: int | None = None,
        detail: object = None,
    ) -> None:
        """Retain HTTP status so callers can recover existing domain resources."""
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


def create_ep_service_token() -> str:
    """Create a short-lived, audience-bound AO service assertion."""
    settings = get_settings()
    key_manager = get_key_manager()
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": EP_CLIENT_ID,
        "client_id": EP_CLIENT_ID,
        "scope": EP_SCOPES,
        "iss": settings.jwt_issuer,
        "aud": EP_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(seconds=EP_TOKEN_LIFETIME_SECONDS),
        "jti": str(uuid4()),
    }
    return jwt.encode(
        claims,
        key_manager.get_private_key(),
        algorithm="ES256",
        headers={"kid": key_manager.key_id},
    )


class ExecutionPlaneHttpClient:
    """HTTP transport for the Execution Plane service."""

    def __init__(self, *, timeout: float | None = None) -> None:
        """Initialize the client from AO's EP URL and mTLS settings."""
        settings = get_settings()
        if not settings.ep_api_url:
            msg = "Execution Plane is enabled for this activity but APP_EP_API_URL is not configured"
            raise ExecutionPlaneUnavailableError(msg)
        self._settings = settings
        self._client = build_internal_http_client(
            base_url=settings.ep_api_url.rstrip("/"),
            timeout=timeout or settings.ep_request_timeout_seconds,
        )

    async def __aenter__(self) -> Self:
        """Return this reusable HTTP client."""
        return self

    async def __aexit__(self, *_: object) -> None:
        """Close the HTTP connection pool."""
        await self._client.aclose()

    async def submit_command(self, message: MessageEnvelope) -> TransportReceipt:
        """Send a shared command and require its matching transport receipt."""
        response = await self._request("POST", "/v1/commands", json_body=message.model_dump(mode="json"))
        try:
            receipt = TransportReceipt.model_validate(response)
        except ValueError:
            msg = "Execution Plane returned an invalid command receipt"
            raise ExecutionPlaneRejectedError(msg) from None
        if receipt.message_id != message.message_id:
            msg = "Execution Plane returned a receipt for a different message"
            raise ExecutionPlaneRejectedError(msg)
        return receipt

    async def get_work_item(self, *, work_item_id: UUID) -> dict[str, Any]:
        """Read accepted work by its UUID."""
        response = await self._request("GET", f"/v1/work-items/{work_item_id}")
        return self._as_object(response)

    async def cancel_work_item(self, *, work_item_id: UUID) -> TransportReceipt:
        """Request cancellation through the shared command contract."""
        message = CancelCommand(target_command_id=work_item_id).to_message(
            source_id=EP_CLIENT_ID,
            destination_id=EP_AUDIENCE,
            client_id=EP_CLIENT_ID,
        )
        return await self.submit_command(message)

    async def list_work_items(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
        sort: str | None = None,
        include_total: bool = False,
        filters: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """List a bounded page of work items for this AO client."""
        return await self._list_resources(
            "/v1/work-items", limit=limit, cursor=cursor, sort=sort, include_total=include_total, filters=filters
        )

    async def list_execution_targets(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
        sort: str | None = None,
        include_total: bool = False,
        filters: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """List a bounded page of safe target metadata."""
        return await self._list_resources(
            "/v1/execution-targets", limit=limit, cursor=cursor, sort=sort, include_total=include_total, filters=filters
        )

    async def get_execution_target(self, *, target_id: UUID) -> dict[str, Any]:
        """Read a caller-owned target without its management credentials."""
        return self._as_object(await self._request("GET", f"/v1/execution-targets/{target_id}"))

    async def list_clusters(self, *, limit: int = 2, filters: Mapping[str, str] | None = None) -> dict[str, Any]:
        """Read bounded client-owned cluster inventory."""
        return await self._list_resources(
            "/v1/clusters", limit=limit, cursor=None, sort=None, include_total=False, filters=filters
        )

    async def _list_resources(
        self,
        path: str,
        *,
        limit: int,
        cursor: str | None,
        sort: str | None,
        include_total: bool,
        filters: Mapping[str, str] | None,
    ) -> dict[str, Any]:
        """Forward EP's list controls and dynamic filters without interpreting cursors.

        Mirrors execution_plane.api.list_queries.list_query_filters: separate
        query controls from filters so filters cannot override those controls.
        """
        params: dict[str, str | int] = {
            key: value
            for key, value in (filters or {}).items()
            if key not in {"limit", "cursor", "sort", "include_total"}
        }
        params["limit"] = limit
        if cursor is not None:
            params["cursor"] = cursor
        if sort is not None:
            params["sort"] = sort
        if include_total:
            params["include_total"] = "true"
        response = await self._request("GET", path, params=params)
        return self._as_page(response)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, Any] | None = None,
        params: Mapping[str, str | int] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        token = create_ep_service_token()
        try:
            response = await self._client.request(
                method,
                path,
                headers={"Authorization": f"Bearer {token}"},
                json=json_body,
                params=params,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if (
                exc.response.status_code == HTTPStatus.TOO_MANY_REQUESTS
                or exc.response.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR
            ):
                raise ExecutionPlaneUnavailableError from exc
            detail_str = "Execution Plane rejected the request"
            raw_detail: object = None
            with suppress(ValueError, AttributeError):
                error_body = exc.response.json()
                if isinstance(error_body, dict) and "detail" in error_body:
                    raw_detail = error_body["detail"]
                    if isinstance(raw_detail, str):
                        detail_str = raw_detail
            raise ExecutionPlaneRejectedError(
                detail_str, status_code=exc.response.status_code, detail=raw_detail
            ) from exc
        except httpx.RequestError as exc:
            raise ExecutionPlaneUnavailableError from exc
        if response.status_code == HTTPStatus.NO_CONTENT:
            return None
        try:
            body = response.json()
        except ValueError as exc:
            msg = "Execution Plane returned invalid JSON"
            raise ExecutionPlaneRejectedError(msg) from exc
        if isinstance(body, list):
            return cast("list[dict[str, Any]]", body)
        return cast("dict[str, Any]", body)

    @staticmethod
    def _as_object(response: dict[str, Any] | list[dict[str, Any]] | None) -> dict[str, Any]:
        """Require an object response for single-resource endpoints."""
        if not isinstance(response, dict):
            msg = "Execution Plane returned an invalid object response"
            raise ExecutionPlaneRejectedError(msg)
        return response

    @staticmethod
    def _as_page(response: dict[str, Any] | list[dict[str, Any]] | None) -> dict[str, Any]:
        """Require a pagination envelope from list endpoints."""
        if not isinstance(response, dict) or not isinstance(response.get("resources"), list):
            msg = "Execution Plane returned an invalid page response"
            raise ExecutionPlaneRejectedError(msg)
        resources = response["resources"]
        total = response.get("total")
        if (
            any(not isinstance(resource, dict) for resource in resources)
            or any(response.get(key) is not None and not isinstance(response[key], str) for key in ("next", "prev"))
            or (total is not None and (type(total) is not int or total < 0))
        ):
            msg = "Execution Plane returned an invalid page response"
            raise ExecutionPlaneRejectedError(msg)
        return response
