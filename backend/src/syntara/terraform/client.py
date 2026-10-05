"""Thin Terraform Enterprise v2 API client.

Design rules (SDP):
- Stateless REST client; no cached TFE state in AO
- Read calls retry with exponential backoff (max 3) on 5xx/429
- Mutating calls are never redelivered on network ambiguity → OUTCOME_UNKNOWN
- Tokens and sensitive values are never logged
"""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import quote

import httpx
import structlog

from syntara.core.config.base import get_settings
from syntara.core.lib.tls_utils import build_integration_httpx_verify
from syntara.core.lib.url_validation import validate_url_no_ssrf
from syntara.terraform.errors import TFEError, TFEErrorCode, map_http_status_to_error

logger = structlog.stdlib.get_logger(__name__)

_JSON_API = "application/vnd.api+json"
_API_PREFIX = "/api/v2"
_MAX_READ_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 0.5
_HTTP_NO_CONTENT = 204
_TFE_PAGE_SIZE = 100
# Leave headroom under the activity budget for decode/telemetry before Temporal
# cancels the attempt. Must stay ≤ OrchestratorWorkflow._TEMPORAL_MARGIN.
_CLIENT_TIMEOUT_MARGIN_SECONDS = 10.0
DEFAULT_TFE_HTTP_TIMEOUT_SECONDS = 60.0


def resolve_http_timeout_from_engine(engine_timeout_seconds: float | None) -> float:
    """Derive a per-client HTTP budget from the activity timeout.

    The returned value is the total HTTP budget for the activity (client timeout
    <= activity budget - margin). Callers that retry reads should further divide
    this budget across attempts via :meth:`TFEClient._request_timeout`.
    """
    if engine_timeout_seconds is None:
        return DEFAULT_TFE_HTTP_TIMEOUT_SECONDS
    budget = float(engine_timeout_seconds) - _CLIENT_TIMEOUT_MARGIN_SECONDS
    return max(1.0, budget)


class TFEClient:
    """Async HTTP client for Terraform Enterprise / HCP Terraform v2 API."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        organization: str,
        verify_ssl: bool = True,
        ca_certificate: str | None = None,
        timeout_seconds: float = DEFAULT_TFE_HTTP_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize the client with connection settings.

        ``timeout_seconds`` is the total HTTP budget for the activity. Mutating
        calls and uploads use it as the per-request timeout; read calls divide it
        across retry attempts so the worst case still fits the activity budget.
        """
        self.base_url = base_url.rstrip("/")
        self.organization = organization
        self._token = token
        self._timeout = timeout_seconds
        self._verify = build_integration_httpx_verify(
            insecure_skip_tls_verify=not verify_ssl,
            ca_certificate=ca_certificate,
        )

    def _request_timeout(self, *, mutating: bool) -> float:
        """Per-request httpx timeout that stays within the activity HTTP budget."""
        if mutating:
            return self._timeout
        return max(1.0, self._timeout / _MAX_READ_ATTEMPTS)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": _JSON_API,
            "Accept": _JSON_API,
        }

    def _url(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        return f"{self.base_url}{_API_PREFIX}{path}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        mutating: bool = False,
        content: bytes | None = None,
        content_type: str | None = None,
    ) -> httpx.Response | None:
        """Execute an HTTP request with retry/error mapping.

        Returns None only for successful 204 responses.
        """
        headers = self._headers()
        if content_type:
            headers["Content-Type"] = content_type

        attempts = 1 if mutating else _MAX_READ_ATTEMPTS
        last_error: Exception | None = None

        request_timeout = self._request_timeout(mutating=mutating)
        for attempt in range(1, attempts + 1):
            try:
                async with httpx.AsyncClient(verify=self._verify, timeout=request_timeout) as client:
                    response = await client.request(
                        method,
                        self._url(path),
                        headers=headers,
                        json=json_body,
                        params=params,
                        content=content,
                    )
            except (httpx.TimeoutException, httpx.NetworkError, OSError) as exc:
                last_error = exc
                terminal = _terminal_transport_error(
                    exc,
                    mutating=mutating,
                    attempt=attempt,
                    attempts=attempts,
                )
                if terminal is not None:
                    raise terminal from exc
                await asyncio.sleep(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
                continue

            if response.status_code == _HTTP_NO_CONTENT:
                return None

            if response.is_success:
                return response

            detail = _extract_error_detail(response)
            error = map_http_status_to_error(response.status_code, detail, mutating=mutating)
            if error.retryable and attempt < attempts:
                await asyncio.sleep(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
                last_error = error
                continue
            raise error

        if last_error:
            raise last_error
        msg = "TFE request failed with unknown error"
        raise TFEError(msg, error_code=TFEErrorCode.TRANSIENT)

    async def _json(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        mutating: bool = False,
    ) -> dict[str, Any]:
        response = await self._request(method, path, json_body=json_body, params=params, mutating=mutating)
        if response is None:
            return {}
        data: dict[str, Any] = response.json()
        return data

    @staticmethod
    def _next_page(response: dict[str, Any], page: int) -> int | None:
        metadata = response.get("meta")
        pagination = metadata.get("pagination") if isinstance(metadata, dict) else None
        next_page = pagination.get("next-page") if isinstance(pagination, dict) else None
        if isinstance(next_page, int) and not isinstance(next_page, bool):
            return next_page if next_page > 0 else None

        total_pages = pagination.get("total-pages") if isinstance(pagination, dict) else None
        if isinstance(total_pages, int) and not isinstance(total_pages, bool):
            return page + 1 if page < total_pages else None

        links = response.get("links")
        return page + 1 if isinstance(links, dict) and links.get("next") else None

    @staticmethod
    def _merge_pages(first_response: dict[str, Any], items: list[Any]) -> dict[str, Any]:
        result = dict(first_response)
        result["data"] = items
        # These describe the first page and would be stale after aggregation.
        result.pop("links", None)
        metadata = result.get("meta")
        if isinstance(metadata, dict) and "pagination" in metadata:
            metadata = dict(metadata)
            metadata.pop("pagination", None)
            if metadata:
                result["meta"] = metadata
            else:
                result.pop("meta", None)
        return result

    async def _json_all_pages(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Fetch all pages from a TFE JSON:API list endpoint.

        TFE defaults list responses to 20 records, so explicitly request the
        maximum page size and follow the pagination metadata until exhausted.
        Only relative page numbers are constructed locally; response-provided
        pagination URLs are never used as request destinations.
        """
        page = 1
        seen_pages: set[int] = set()
        items: list[Any] = []
        first_response: dict[str, Any] | None = None

        while page not in seen_pages:
            seen_pages.add(page)
            page_params = {
                **(params or {}),
                "page[number]": page,
                "page[size]": _TFE_PAGE_SIZE,
            }
            response = await self._json("GET", path, params=page_params)
            if first_response is None:
                first_response = response

            data = response.get("data")
            if not isinstance(data, list):
                return response if response is first_response else self._merge_pages(first_response, items)
            items.extend(data)

            next_page = self._next_page(response, page)
            if next_page is None:
                break
            page = next_page

        return self._merge_pages(first_response or {}, items)

    # ── Workspace ──────────────────────────────────────────────────────────

    async def create_workspace(
        self,
        name: str,
        *,
        organization: str | None = None,
        attributes: dict[str, Any] | None = None,
        project_id: str | None = None,
        relationships: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST /organizations/{org}/workspaces."""
        org = quote(organization or self.organization, safe="")
        body: dict[str, Any] = {
            "data": {
                "type": "workspaces",
                "attributes": {"name": name, **(attributes or {})},
            }
        }
        merged_relationships = dict(relationships or {})
        if project_id:
            merged_relationships["project"] = {"data": {"type": "projects", "id": project_id}}
        if merged_relationships:
            body["data"]["relationships"] = merged_relationships
        return await self._json("POST", f"/organizations/{org}/workspaces", json_body=body, mutating=True)

    async def list_workspaces(
        self,
        *,
        organization: str | None = None,
        search: str | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """GET /organizations/{org}/workspaces."""
        org = quote(organization or self.organization, safe="")
        params: dict[str, Any] = {}
        if search:
            params["search[name]"] = search
        if project_id:
            params["filter[project][id]"] = project_id
        return await self._json_all_pages(f"/organizations/{org}/workspaces", params=params or None)

    async def update_workspace(
        self,
        workspace_id: str,
        attributes: dict[str, Any],
        *,
        relationships: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """PATCH /workspaces/{ws}."""
        data: dict[str, Any] = {"type": "workspaces", "id": workspace_id, "attributes": attributes}
        if relationships:
            data["relationships"] = relationships
        body = {"data": data}
        return await self._json("PATCH", f"/workspaces/{quote(workspace_id, safe='')}", json_body=body, mutating=True)

    async def delete_workspace(self, workspace_id: str, *, force: bool = False) -> None:
        """Safely delete a workspace unless force is explicitly requested."""
        path = f"/workspaces/{quote(workspace_id, safe='')}"
        if force:
            await self._request("DELETE", path, mutating=True)
        else:
            await self._request("POST", f"{path}/actions/safe-delete", mutating=True)

    async def get_current_state_version(self, workspace_id: str) -> dict[str, Any] | None:
        """GET /workspaces/{ws}/current-state-version. Returns None on 404."""
        try:
            return await self._json("GET", f"/workspaces/{quote(workspace_id, safe='')}/current-state-version")
        except TFEError as exc:
            if exc.error_code == TFEErrorCode.NOT_FOUND:
                return None
            raise

    async def get_state_version_outputs(self, state_version_id: str) -> dict[str, Any]:
        """GET /state-versions/{id}/outputs."""
        return await self._json_all_pages(f"/state-versions/{quote(state_version_id, safe='')}/outputs")

    # ── Variables ──────────────────────────────────────────────────────────

    async def create_variable(self, workspace_id: str, attributes: dict[str, Any]) -> dict[str, Any]:
        """POST /workspaces/{ws}/vars."""
        body = {"data": {"type": "vars", "attributes": attributes}}
        return await self._json(
            "POST",
            f"/workspaces/{quote(workspace_id, safe='')}/vars",
            json_body=body,
            mutating=True,
        )

    async def list_variables(self, workspace_id: str) -> dict[str, Any]:
        """GET /workspaces/{ws}/vars."""
        return await self._json_all_pages(f"/workspaces/{quote(workspace_id, safe='')}/vars")

    async def update_variable(self, workspace_id: str, variable_id: str, attributes: dict[str, Any]) -> dict[str, Any]:
        """PATCH /workspaces/{ws}/vars/{var}."""
        body = {"data": {"type": "vars", "id": variable_id, "attributes": attributes}}
        path = f"/workspaces/{quote(workspace_id, safe='')}/vars/{quote(variable_id, safe='')}"
        return await self._json("PATCH", path, json_body=body, mutating=True)

    async def delete_variable(self, workspace_id: str, variable_id: str) -> None:
        """DELETE /workspaces/{ws}/vars/{var}."""
        path = f"/workspaces/{quote(workspace_id, safe='')}/vars/{quote(variable_id, safe='')}"
        await self._request("DELETE", path, mutating=True)

    # ── Configuration versions ─────────────────────────────────────────────

    async def create_configuration_version(
        self,
        workspace_id: str,
        *,
        auto_queue_runs: bool = False,
        speculative: bool = False,
    ) -> dict[str, Any]:
        """POST /workspaces/{ws}/configuration-versions."""
        body = {
            "data": {
                "type": "configuration-versions",
                "attributes": {
                    "auto-queue-runs": auto_queue_runs,
                    "speculative": speculative,
                },
            }
        }
        return await self._json(
            "POST",
            f"/workspaces/{quote(workspace_id, safe='')}/configuration-versions",
            json_body=body,
            mutating=True,
        )

    async def upload_configuration_version(self, upload_url: str, content: bytes) -> None:
        """PUT artifact bytes to the TFE-provided upload URL.

        The upload destination is an arbitrary absolute URL from the TFE API
        (often object storage). Validate it against the outbound URL policy and
        never attach the Terraform Bearer token — signed upload URLs authenticate
        via query parameters, and sending the API credential would leak it to a
        third-party or attacker-controlled host.
        """
        try:
            validate_url_no_ssrf(
                upload_url,
                allowed_hosts=get_settings().integration_url_allowed_hosts,
                allow_http=False,
            )
        except ValueError as exc:
            msg = f"TFE upload URL failed outbound URL policy: {exc}"
            raise TFEError(msg, error_code=TFEErrorCode.VALIDATION, retryable=False) from exc

        headers = {"Content-Type": "application/octet-stream"}
        try:
            async with httpx.AsyncClient(verify=self._verify, timeout=self._timeout) as client:
                response = await client.request(
                    "PUT",
                    upload_url,
                    headers=headers,
                    content=content,
                )
        except (httpx.TimeoutException, httpx.NetworkError, OSError) as exc:
            msg = "Network error during TFE configuration upload; verify outcome in TFE before retrying"
            raise TFEError(msg, error_code=TFEErrorCode.OUTCOME_UNKNOWN, retryable=False) from exc

        if response.status_code == _HTTP_NO_CONTENT or response.is_success:
            return

        detail = _extract_error_detail(response)
        raise map_http_status_to_error(response.status_code, detail, mutating=True)

    # ── Runs ───────────────────────────────────────────────────────────────

    async def create_run(
        self,
        attributes: dict[str, Any],
        workspace_id: str,
        *,
        configuration_version_id: str | None = None,
    ) -> dict[str, Any]:
        """POST /runs."""
        body: dict[str, Any] = {
            "data": {
                "type": "runs",
                "attributes": attributes,
                "relationships": {
                    "workspace": {"data": {"type": "workspaces", "id": workspace_id}},
                },
            }
        }
        if configuration_version_id:
            body["data"]["relationships"]["configuration-version"] = {
                "data": {"type": "configuration-versions", "id": configuration_version_id},
            }
        return await self._json("POST", "/runs", json_body=body, mutating=True)

    async def get_run(self, run_id: str) -> dict[str, Any]:
        """GET /runs/{run}."""
        return await self._json("GET", f"/runs/{quote(run_id, safe='')}")

    async def get_plan(self, plan_id: str) -> dict[str, Any]:
        """GET /plans/{plan}."""
        return await self._json("GET", f"/plans/{quote(plan_id, safe='')}")

    async def apply_run(self, run_id: str, comment: str | None = None) -> None:
        """POST /runs/{run}/actions/apply."""
        body = {"comment": comment} if comment else None
        await self._request("POST", f"/runs/{quote(run_id, safe='')}/actions/apply", json_body=body, mutating=True)

    async def discard_run(self, run_id: str, comment: str | None = None) -> None:
        """POST /runs/{run}/actions/discard."""
        body = {"comment": comment} if comment else None
        await self._request("POST", f"/runs/{quote(run_id, safe='')}/actions/discard", json_body=body, mutating=True)

    async def cancel_run(self, run_id: str, comment: str | None = None) -> None:
        """POST /runs/{run}/actions/cancel."""
        body = {"comment": comment} if comment else None
        await self._request("POST", f"/runs/{quote(run_id, safe='')}/actions/cancel", json_body=body, mutating=True)

    async def force_cancel_run(self, run_id: str, comment: str | None = None) -> None:
        """POST /runs/{run}/actions/force-cancel."""
        body = {"comment": comment} if comment else None
        await self._request(
            "POST",
            f"/runs/{quote(run_id, safe='')}/actions/force-cancel",
            json_body=body,
            mutating=True,
        )

    async def list_runs(self, workspace_id: str, *, status: str | None = None) -> dict[str, Any]:
        """GET /workspaces/{ws}/runs."""
        params: dict[str, Any] = {}
        if status:
            params["filter[status]"] = status
        return await self._json_all_pages(f"/workspaces/{quote(workspace_id, safe='')}/runs", params=params or None)

    async def add_run_comment(self, run_id: str, comment: str) -> dict[str, Any]:
        """POST /runs/{run}/comments."""
        body = {"data": {"type": "comments", "attributes": {"body": comment}}}
        return await self._json(
            "POST",
            f"/runs/{quote(run_id, safe='')}/comments",
            json_body=body,
            mutating=True,
        )

    # ── VCS / GitHub App ───────────────────────────────────────────────────

    async def list_github_app_installations(self) -> dict[str, Any]:
        """GET /github-app/installations."""
        return await self._json_all_pages("/github-app/installations")

    async def get_github_app_installation(self, installation_id: str) -> dict[str, Any]:
        """GET /github-app/installation/{id}."""
        return await self._json("GET", f"/github-app/installation/{quote(installation_id, safe='')}")

    async def link_vcs_to_workspace(
        self,
        workspace_id: str,
        *,
        identifier: str,
        branch: str,
        github_app_installation_id: str | None = None,
    ) -> dict[str, Any]:
        """PATCH workspace with vcs-repo attributes."""
        vcs_repo: dict[str, Any] = {"identifier": identifier, "branch": branch}
        if github_app_installation_id:
            vcs_repo["github-app-installation-id"] = github_app_installation_id
        return await self.update_workspace(workspace_id, {"vcs-repo": vcs_repo})

    # ── Projects ───────────────────────────────────────────────────────────

    async def create_project(
        self,
        name: str,
        *,
        organization: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """POST /organizations/{org}/projects."""
        org = quote(organization or self.organization, safe="")
        attrs: dict[str, Any] = {"name": name}
        if description is not None:
            attrs["description"] = description
        body = {"data": {"type": "projects", "attributes": attrs}}
        return await self._json("POST", f"/organizations/{org}/projects", json_body=body, mutating=True)

    async def list_projects(self, *, organization: str | None = None) -> dict[str, Any]:
        """GET /organizations/{org}/projects."""
        org = quote(organization or self.organization, safe="")
        return await self._json_all_pages(f"/organizations/{org}/projects")

    async def get_project(self, project_id: str) -> dict[str, Any]:
        """GET /projects/{prj}."""
        return await self._json("GET", f"/projects/{quote(project_id, safe='')}")

    async def list_project_teams(self, project_id: str) -> dict[str, Any]:
        """GET /projects/{prj}/relationships/teams (team-projects)."""
        return await self._json_all_pages("/team-projects", params={"filter[project][id]": project_id})

    async def update_project(self, project_id: str, attributes: dict[str, Any]) -> dict[str, Any]:
        """PATCH /projects/{prj}."""
        body = {"data": {"type": "projects", "id": project_id, "attributes": attributes}}
        return await self._json("PATCH", f"/projects/{quote(project_id, safe='')}", json_body=body, mutating=True)

    async def delete_project(self, project_id: str) -> None:
        """DELETE /projects/{prj}."""
        await self._request("DELETE", f"/projects/{quote(project_id, safe='')}", mutating=True)

    async def move_workspace_to_project(self, workspace_id: str, project_id: str | None) -> dict[str, Any]:
        """PATCH workspace relationships.project."""
        rel: dict[str, Any] = {"data": {"type": "projects", "id": project_id}} if project_id else {"data": None}
        body = {
            "data": {
                "type": "workspaces",
                "id": workspace_id,
                "relationships": {"project": rel},
            }
        }
        return await self._json(
            "PATCH",
            f"/workspaces/{quote(workspace_id, safe='')}",
            json_body=body,
            mutating=True,
        )

    async def assign_team_permissions(self, project_id: str, team_id: str, access: str) -> dict[str, Any]:
        """POST /team-projects."""
        body = {
            "data": {
                "type": "team-projects",
                "attributes": {"access": access},
                "relationships": {
                    "project": {"data": {"type": "projects", "id": project_id}},
                    "team": {"data": {"type": "teams", "id": team_id}},
                },
            }
        }
        return await self._json("POST", "/team-projects", json_body=body, mutating=True)


def _terminal_transport_error(
    exc: Exception,
    *,
    mutating: bool,
    attempt: int,
    attempts: int,
) -> TFEError | None:
    """Map a transport failure to a terminal error, or None when the caller should retry.

    Mutating calls never retry: a dropped connection may already have applied the change.
    """
    if mutating:
        msg = "Network error during mutating TFE call; verify outcome in TFE before retrying"
        return TFEError(msg, error_code=TFEErrorCode.OUTCOME_UNKNOWN, retryable=False)
    if attempt < attempts:
        return None
    if isinstance(exc, httpx.TimeoutException):
        msg = f"TFE endpoint timed out: {type(exc).__name__}"
    else:
        msg = f"TFE endpoint unreachable: {type(exc).__name__}"
    return TFEError(msg, error_code=TFEErrorCode.UNREACHABLE, retryable=False)


def _extract_error_detail(response: httpx.Response) -> str:
    """Extract a safe human-readable detail from a TFE error response."""
    try:
        payload = response.json()
        errors = payload.get("errors") if isinstance(payload, dict) else None
        if isinstance(errors, list) and errors:
            parts: list[str] = []
            for err in errors:
                if not isinstance(err, dict):
                    continue
                title = err.get("title") or ""
                detail = err.get("detail") or ""
                # Never echo potential secrets from error bodies beyond title/detail
                text = ": ".join(p for p in (title, detail) if p)
                if text:
                    parts.append(text)
            if parts:
                return "; ".join(parts)
    except Exception:  # noqa: BLE001 — best-effort parse of error JSON
        logger.debug("Could not parse TFE error response body", status_code=response.status_code)
    return f"TFE API returned HTTP {response.status_code}"
