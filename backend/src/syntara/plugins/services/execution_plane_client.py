"""Async client for dispatching work items to the Execution Plane.

Sends ``work.execute`` commands to the Execution Plane API and polls the
resulting work item until it reaches a terminal status. Used by the
``plugin_action`` activity to run ``custom-runner`` plugin actions (container
workloads) on the Execution Plane instead of the orchestrator host.

The command envelope mirrors the Execution Plane's public
``execution_plane_client`` contracts (``MessageEnvelope`` wrapping one
``work.execute`` command); this module builds the same JSON structure with the
standard library plus ``httpx`` so the orchestrator does not depend on that
package.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import jwt
import structlog

from syntara.core.config.base import get_settings

logger = structlog.stdlib.get_logger(__name__)

# Work-item statuses that end polling (mirrors execution_plane.work_item_client).
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "reconciliation_required"})

_JWT_TTL = timedelta(hours=8)
_JWT_SCOPES = ("work.execute", "work-items:read")
_HTTP_ACCEPTED = 202
_HTTP_OK = 200


class ExecutionPlaneError(RuntimeError):
    """The Execution Plane rejected or failed a work item."""


class ExecutionPlaneClient:
    """Submit one work item per call and wait for its terminal status."""

    def __init__(self) -> None:
        """Bind settings; a fresh client is cheap, so activities construct one per step."""
        self._settings = get_settings()

    def _service_token(self) -> str:
        """Mint an ES256 service JWT accepted by the Execution Plane API.

        Signs with the orchestrator's JWT private key — the same key the
        Execution Plane trusts for ``syntara-orchestration`` in local dev.
        """
        key_path = self._settings.jwt_private_key_path
        if not key_path:
            msg = "APP_JWT_PRIVATE_KEY_PATH must be set to mint Execution Plane service tokens"
            raise ExecutionPlaneError(msg)
        with Path(key_path).open(encoding="utf-8") as handle:
            private_key = handle.read()
        now = datetime.now(UTC)
        claims = {
            "iss": self._settings.execution_plane_jwt_issuer,
            "aud": self._settings.execution_plane_jwt_audience,
            "client_id": self._settings.execution_plane_client_id,
            "scope": " ".join(_JWT_SCOPES),
            "iat": now,
            "exp": now + _JWT_TTL,
        }
        return jwt.encode(claims, private_key, algorithm="ES256")

    def _http_client(self) -> httpx.AsyncClient:
        """Build an AsyncClient verifying against the configured CA (or unverified for dev)."""
        ca_path = self._settings.execution_plane_api_ca_path
        return httpx.AsyncClient(
            timeout=self._settings.execution_plane_request_timeout_seconds,
            verify=ca_path if ca_path else False,
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._service_token()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _build_work_execute_message(
        self,
        *,
        work_id: uuid.UUID,
        image: str,
        step_revision_id: str,
        workflow_run_id: str,
        inputs: dict[str, Any],
        timeout_seconds: int,
        output_config: dict[str, str] | None,
    ) -> dict[str, Any]:
        """Build the ``work.execute`` command envelope (execution_plane_client wire format)."""
        client_id = self._settings.execution_plane_client_id
        occurred_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        return {
            "message_id": str(work_id),
            "message_type": "command.submit",
            "command_id": str(work_id),
            "sequence": 0,
            "source_id": client_id,
            "destination_id": self._settings.execution_plane_jwt_audience,
            "scope": {"client_id": client_id},
            "command": {
                "command_id": str(work_id),
                "parent_command_id": None,
                "command_type": "work.execute",
                "command_revision": 1,
                "payload": {
                    "image": image,
                    "selectors": {},
                    "invocation": {
                        "workflow_run_id": workflow_run_id,
                        "step_revision_id": step_revision_id,
                        "inputs": inputs,
                        "runtime_context": {},
                        "timeout_seconds": timeout_seconds,
                    },
                    "output_config": output_config,
                    "workload_type": "container",
                },
                "occurred_at": occurred_at,
            },
        }

    async def submit_and_wait(
        self,
        *,
        image: str,
        step_revision_id: str,
        workflow_run_id: str,
        inputs: dict[str, Any],
        timeout_seconds: int,
        output_config: dict[str, str] | None = None,
        on_poll: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        """Submit one ``work.execute`` command and poll until the work item is terminal.

        Args:
            image: Digest-pinned workload image reference.
            step_revision_id: Step identity the workload advertises (the plugin action identity).
            workflow_run_id: Correlation id for the invoking workflow run.
            inputs: Step inputs validated against the action's input schema upstream.
            timeout_seconds: Workload execution timeout handed to the Execution Plane.
            output_config: Optional output-field mapping (field name -> output key).
            on_poll: Optional async callback invoked with the latest work-item dict
                after each poll — used by the activity to emit Temporal heartbeats.

        Returns:
            The terminal work-item dict: ``{"id", "status", "result", ...}``.

        Raises:
            ExecutionPlaneError: On submission failure or when polling exceeds the deadline.

        """
        if not self._settings.execution_plane_api_url:
            msg = "APP_EXECUTION_PLANE_API_URL must be set to dispatch to the Execution Plane"
            raise ExecutionPlaneError(msg)

        api_url = self._settings.execution_plane_api_url.rstrip("/")
        work_id = uuid.uuid4()
        body = self._build_work_execute_message(
            work_id=work_id,
            image=image,
            step_revision_id=step_revision_id,
            workflow_run_id=workflow_run_id,
            inputs=inputs,
            timeout_seconds=timeout_seconds,
            output_config=output_config,
        )

        async with self._http_client() as client:
            response = await client.post(
                f"{api_url}/v1/commands",
                headers=self._headers(),
                json=body,
            )
            if response.status_code not in {_HTTP_OK, _HTTP_ACCEPTED}:
                msg = f"Execution Plane submit failed ({response.status_code}): {response.text[:500]}"
                raise ExecutionPlaneError(msg)

            # Poll deadline: workload timeout plus submit/claim/poll overhead.
            deadline_seconds = timeout_seconds + 120.0
            deadline = asyncio.get_running_loop().time() + deadline_seconds
            while asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(self._settings.execution_plane_poll_interval_seconds)
                poll = await client.get(
                    f"{api_url}/v1/work-items/{work_id}",
                    headers=self._headers(),
                )
                if poll.status_code == httpx.codes.NOT_FOUND:
                    continue
                if poll.status_code >= httpx.codes.BAD_REQUEST:
                    msg = f"Execution Plane work-item lookup failed ({poll.status_code}): {poll.text[:500]}"
                    raise ExecutionPlaneError(msg)
                latest: dict[str, Any] = poll.json()
                if on_poll is not None:
                    await on_poll(latest)
                if latest.get("status") in TERMINAL_STATUSES:
                    logger.info(
                        "execution plane work item finished",
                        work_item_id=str(work_id),
                        status=latest.get("status"),
                    )
                    return latest

        msg = f"Timed out waiting for Execution Plane work item {work_id}"
        raise ExecutionPlaneError(msg)
