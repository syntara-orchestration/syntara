"""Versioned HTTP client for the standalone Execution Plane service."""

from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, Self, cast
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
import jwt

if TYPE_CHECKING:
    from collections.abc import Mapping

from syntara.auth.services.token_service import get_key_manager
from syntara.core.config.base import get_settings
from syntara.core.tls.http_client import build_internal_http_client

EP_CLIENT_ID = "syntara-orchestration"
EP_AUDIENCE = "execution-plane"
EP_TOKEN_LIFETIME_SECONDS = 300
EP_SCOPES = (
    "work-items:submit work-items:read work-items:cancel execution-targets:read "
    "cluster-bindings:write cluster-bindings:read"
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

    def __init__(self, message: str = "Execution Plane rejected the request") -> None:
        """Describe a non-retryable request failure."""
        super().__init__(message)


def create_ep_service_token(project_id: UUID | None, *, all_projects: bool = False) -> str:
    """Create a short-lived, audience-bound AO assertion scoped to one project."""
    if project_id is None and not all_projects:
        msg = "A project ID is required unless AO authorized all-project access"
        raise ValueError(msg)
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
    if project_id is not None:
        claims["project_id"] = str(project_id)
    if all_projects:
        claims["all_projects"] = True
    return jwt.encode(
        claims,
        key_manager.get_private_key(),
        algorithm="ES256",
        headers={"kid": key_manager.key_id},
    )


class ExecutionPlaneHttpClient:
    """HTTP transport that gives each operation a fresh signed project grant."""

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

    async def submit_work_item(
        self,
        *,
        project_id: UUID,
        request_id: str,
        work_correlation_id: UUID,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Submit work using EP's stable idempotency key."""
        response = await self._request(
            "POST",
            "/v1/work-items",
            project_id=project_id,
            json_body={
                "request_id": request_id,
                "work_correlation_id": str(work_correlation_id),
                "workload_type": "script",
                "payload": payload,
            },
        )
        return self._as_object(response)

    async def get_work_item(self, *, project_id: UUID, request_id: str) -> dict[str, Any]:
        """Read accepted work by its stable request ID."""
        response = await self._request(
            "GET",
            f"/v1/work-items/by-request/{quote(request_id, safe='')}",
            project_id=project_id,
        )
        return self._as_object(response)

    async def cancel_work_item_by_request_id(
        self,
        *,
        project_id: UUID,
        request_id: str,
        work_correlation_id: UUID,
    ) -> dict[str, Any]:
        """Request cancellation by stable key, including before AO receives an EP ID."""
        response = await self._request(
            "POST",
            f"/v1/work-items/by-request/{quote(request_id, safe='')}/cancel",
            project_id=project_id,
            json_body={"work_correlation_id": str(work_correlation_id)},
        )
        return self._as_object(response)

    async def list_work_items(
        self,
        *,
        project_id: UUID | None = None,
        all_projects: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List a bounded page of work items in the signed AO authorization scope."""
        response = await self._request(
            "GET",
            "/v1/work-items",
            project_id=project_id,
            all_projects=all_projects,
            params={"limit": limit},
        )
        return self._as_list(response)

    async def list_execution_targets(
        self,
        *,
        project_id: UUID | None = None,
        all_projects: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List a bounded page of safe target metadata."""
        response = await self._request(
            "GET",
            "/v1/execution-targets",
            project_id=project_id,
            all_projects=all_projects,
            params={"limit": limit},
        )
        return self._as_list(response)

    async def upsert_cluster_binding(
        self,
        *,
        source_integration_id: UUID,
        revision: int,
        name: str,
        endpoint: str,
        namespace: str,
        credential: str,
        ca_certificate: str | None = None,
        insecure_skip_tls_verify: bool = False,
        project_ids: list[UUID] | None,
        labels: dict[str, str],
        enabled: bool,
    ) -> dict[str, Any]:
        """Send a versioned integration desired state to EP over mTLS."""
        response = await self._request(
            "PUT",
            f"/v1/cluster-bindings/{source_integration_id}",
            project_id=None,
            all_projects=True,
            json_body={
                "revision": revision,
                "name": name,
                "endpoint": endpoint,
                "namespace": namespace,
                "credential": credential,
                "ca_certificate": ca_certificate,
                "insecure_skip_tls_verify": insecure_skip_tls_verify,
                "project_ids": [str(project_id) for project_id in project_ids] if project_ids is not None else None,
                "labels": labels,
                "enabled": enabled,
            },
        )
        if response is None or isinstance(response, list):
            msg = "Execution Plane returned an invalid cluster-binding response"
            raise ExecutionPlaneRejectedError(msg)
        return response

    async def get_cluster_binding(self, *, source_integration_id: UUID) -> dict[str, Any]:
        """Read the safe observed state of an integration binding from EP."""
        response = await self._request(
            "GET",
            f"/v1/cluster-bindings/{source_integration_id}",
            project_id=None,
            all_projects=True,
        )
        if response is None or isinstance(response, list):
            msg = "Execution Plane returned an invalid cluster-binding response"
            raise ExecutionPlaneRejectedError(msg)
        return response

    async def _request(
        self,
        method: str,
        path: str,
        *,
        project_id: UUID | None,
        all_projects: bool = False,
        json_body: Mapping[str, Any] | None = None,
        params: Mapping[str, str | int] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        token = create_ep_service_token(project_id, all_projects=all_projects)
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
            detail = "Execution Plane rejected the request"
            with suppress(ValueError, AttributeError):
                error_body = exc.response.json()
                if isinstance(error_body, dict):
                    detail = str(error_body.get("detail", detail))
            raise ExecutionPlaneRejectedError(detail) from exc
        except httpx.RequestError as exc:
            raise ExecutionPlaneUnavailableError from exc
        if response.status_code == HTTPStatus.NO_CONTENT:
            return None
        body = response.json()
        if isinstance(body, list):
            return cast("list[dict[str, Any]]", body)
        return cast("dict[str, Any]", body)

    @staticmethod
    def _as_object(response: dict[str, Any] | list[dict[str, Any]] | None) -> dict[str, Any]:
        """Require an object response for single-resource endpoints."""
        if response is None or isinstance(response, list):
            msg = "Execution Plane returned an invalid object response"
            raise ExecutionPlaneRejectedError(msg)
        return response

    @staticmethod
    def _as_list(response: dict[str, Any] | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        """Require an array response for list endpoints."""
        if not isinstance(response, list):
            msg = "Execution Plane returned an invalid list response"
            raise ExecutionPlaneRejectedError(msg)
        return response
