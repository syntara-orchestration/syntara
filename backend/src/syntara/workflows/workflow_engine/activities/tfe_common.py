"""Shared helpers for Terraform Enterprise workflow activities."""

from __future__ import annotations

from typing import Any

import structlog
from temporalio.exceptions import ApplicationError

from syntara.terraform.client import TFEClient
from syntara.terraform.errors import TFEError, TFEErrorCode
from syntara.workflows.workflow_engine.utils.credential_scrubber import ensure_resolved_credentials_dict

logger = structlog.stdlib.get_logger(__name__)

_BEARER_TOKEN_KEY = "bearer_token"  # noqa: S105


def raise_as_application_error(exc: TFEError) -> None:
    """Convert a TFEError into a Temporal ApplicationError and raise it."""
    raise ApplicationError(
        exc.message,
        exc.to_dict(),
        type=exc.error_code.value,
        non_retryable=not exc.retryable,
    ) from exc


def extract_bearer_token(resolved_credentials: dict[str, Any] | None, _credential_id: str | None = None) -> str:
    """Extract Bearer token from resolved credential injectors.

    ``_resolved_credentials`` is the per-node payload from credential resolution
    (``{extra_vars, env, file, ...}``), not a map keyed by credential ID.
    """
    creds = ensure_resolved_credentials_dict(resolved_credentials)
    extra_vars = creds.get("extra_vars") or {}
    token = (extra_vars.get(_BEARER_TOKEN_KEY) or "").strip()
    if not token:
        msg = "Missing or empty Bearer token credential"
        raise TFEError(msg, error_code=TFEErrorCode.CONFIG_MISSING)
    return token


def build_client_from_resolution(
    integration: dict[str, Any],
    token: str,
    *,
    organization_override: str | None = None,
) -> TFEClient:
    """Build a TFEClient from integration resolution payload + token."""
    base_url = integration.get("base_url")
    organization = organization_override or integration.get("organization")
    if not base_url or not organization:
        msg = "Integration is missing base_url or organization"
        raise TFEError(msg, error_code=TFEErrorCode.CONFIG_MISSING)
    return TFEClient(
        base_url=base_url,
        token=token,
        organization=organization,
        verify_ssl=bool(integration.get("verify_ssl", True)),
        ca_certificate=integration.get("ca_certificate"),
    )


def data_id(payload: dict[str, Any]) -> str | None:
    """Extract JSON:API data.id."""
    data = payload.get("data")
    if isinstance(data, dict):
        return data.get("id")
    return None


def data_attrs(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract JSON:API data.attributes."""
    data = payload.get("data")
    if isinstance(data, dict):
        attrs = data.get("attributes")
        if isinstance(attrs, dict):
            return attrs
    return {}


def list_resources(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize JSON:API list payload to a list of {id, attributes}."""
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    results: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        results.append({"id": item.get("id"), **(item.get("attributes") or {})})
    return results


_PHASE_BY_STATUS: dict[str, str] = {
    **dict.fromkeys(("applied", "errored", "canceled", "force_canceled", "discarded", "planned_and_finished"), ""),
    **dict.fromkeys(("pending", "fetching", "queuing"), "pending"),
    **dict.fromkeys(("planning", "cost_estimating", "policy_checking", "policy_override"), "planning"),
    **dict.fromkeys(("planned", "cost_estimated", "policy_checked"), "planned"),
    **dict.fromkeys(("confirmed", "apply_queued", "applying"), "applying"),
}


def map_run_phase(status: str | None) -> str | None:
    """Map raw TFE run status to a coarse phase."""
    if not status:
        return None
    phase = _PHASE_BY_STATUS.get(status)
    if phase == "":
        return status  # already a final status
    return phase or status
