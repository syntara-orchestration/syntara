"""Emit telemetry for essential Terraform node operational activities (SDP R10.1)."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

import structlog

logger = structlog.stdlib.get_logger(__name__)

# Essential activities from the PRD/SDP
TF_CREATE_WORKSPACE = "tf.create_workspace"
TF_DELETE_WORKSPACE = "tf.delete_workspace"
TF_TRIGGER_RUN = "tf.trigger_run"
TF_APPLY_RUN = "tf.apply_run"
TF_DISCARD_RUN = "tf.discard_run"
TF_LINK_VCS = "tf.link_vcs"
TF_ASSIGN_TEAM_PERMISSIONS = "tf.assign_team_permissions"


@contextmanager
def emit_tfe_activity(
    activity: str,
    *,
    organization: str | None = None,
    workspace_id: str | None = None,
    run_id: str | None = None,
    project_id: str | None = None,
    team_id: str | None = None,
    mode: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Context manager that emits a structured telemetry event on exit.

    Never includes variable values, tokens, artifact contents, comment text,
    or error message bodies. Fire-and-forget: never raises.
    """
    start = time.perf_counter()
    ctx: dict[str, Any] = {"outcome": "success", "error_code": None}
    try:
        yield ctx
    except Exception as exc:
        ctx["outcome"] = "failure"
        error_code = getattr(exc, "error_code", None)
        ctx["error_code"] = getattr(error_code, "value", None) or type(exc).__name__
        raise
    finally:
        try:
            duration_ms = int((time.perf_counter() - start) * 1000)
            properties: dict[str, Any] = {
                "activity": activity,
                "outcome": ctx.get("outcome", "success"),
                "duration_ms": duration_ms,
            }
            if ctx.get("error_code"):
                properties["error_code"] = ctx["error_code"]
            if organization:
                properties["organization"] = organization
            if workspace_id:
                properties["workspace_id"] = workspace_id
            if run_id:
                properties["run_id"] = run_id
            if project_id:
                properties["project_id"] = project_id
            if team_id:
                properties["team_id"] = team_id
            if mode:
                properties["mode"] = mode
            logger.info("tfe_activity_telemetry", **properties)
        except Exception:
            logger.exception("Failed to emit TFE activity telemetry")
