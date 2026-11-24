"""Submit AAP workflow job template execution to the Execution Plane.

Dispatches the AAP Workflow container Action instead of launching and polling
the AAP gateway from the control-plane worker. AO still owns the user
integration: the resolved AAP integration is projected into the work item's
runtime context (endpoint and TLS material), and the node's credential
reference is converted into a credential binding for the Action's
``syntara.aap.credential`` recipe. Neither the integration endpoint nor the
credential is author input.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import structlog
from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.workflow_core.models import AAPWorkflowJobTemplateExecutorParameters, AAPWorkflowJobTemplateOutput
from syntara.workflow_runtime.engines.temporal.activities.common import HEARTBEAT_STOP_MONITOR
from syntara.workflow_runtime.engines.temporal.activities.ep.ep_dispatch_activity import _dispatch_to_ep
from syntara.workflow_runtime.engines.temporal.activities.output_mapping import dump_output
from syntara.workflows.audit.aap_job_execution import emit_completed, emit_failed, emit_launched

if TYPE_CHECKING:
    from collections.abc import Callable

logger = structlog.stdlib.get_logger(__name__)

_NODE_TYPE = "aap_workflow_job_template"

# Runtime-context keys consumed by the AAP Workflow container step. The step
# validates the endpoint and TLS settings before touching the credential and
# targets this endpoint only, so the credential cannot be redirected.
_AAP_ENDPOINT_CONTEXT_KEY = "aapEndpoint"
_AAP_VERIFY_SSL_CONTEXT_KEY = "aapVerifySsl"
_AAP_CA_CERTIFICATE_CONTEXT_KEY = "aapCaCertificate"

_RESOLVED_INTEGRATION_FIELD = "_resolved_integration"

_PLUGIN_NAME = "aap-workflow"


def _aap_runtime_context(input_config: dict[str, Any]) -> dict[str, object]:
    """Project the resolved AAP integration into plugin-visible context keys.

    The dispatcher injects the resolved integration (base URL, TLS settings)
    before the executor runs; URL and SSL come exclusively from it, exactly as
    in the in-process activity.
    """
    resolved_integration = input_config.get(_RESOLVED_INTEGRATION_FIELD)
    if not isinstance(resolved_integration, dict) or not resolved_integration:
        msg = "AAP integration not configured. Attach an AAP integration to this node."
        raise ApplicationError(msg, type="ConfigError", non_retryable=True) from None

    base_url = resolved_integration.get("base_url")
    if not base_url:
        msg = "AAP host not configured. Attach an AAP integration to this node."
        raise ApplicationError(msg, type="ConfigError", non_retryable=True) from None

    context: dict[str, object] = {
        _AAP_ENDPOINT_CONTEXT_KEY: base_url,
        _AAP_VERIFY_SSL_CONTEXT_KEY: bool(resolved_integration.get("verify_ssl", True)),
    }
    ca_certificate = resolved_integration.get("ca_certificate")
    if ca_certificate:
        context[_AAP_CA_CERTIFICATE_CONTEXT_KEY] = ca_certificate
    return context


def _parse_optional_uuid(value: str | None, field: str) -> UUID | None:
    """Parse an optional correlation UUID, disabling audit events on bad input."""
    try:
        return UUID(value) if value else None
    except ValueError:
        logger.warning("Invalid identifier, audit events disabled", field=field, value=value)
        return None


@activity.defn
async def execute_aap_workflow_ep_activity(
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
    execution_id: str | None = None,
    created_by_user_id: str | None = None,
) -> dict[str, Any]:
    """Submit one AAP workflow job template Action, then await callback completion.

    The container step launches the workflow job template, observes the parent
    workflow job to a terminal status, and returns the preserved result fields
    as a discriminated union on ``status``. A ``failed`` status is translated
    into the same non-retryable activity error the in-process activity raises,
    so workflow-level error handling is unchanged.

    AAP job audit events are emitted from the projected result. AO does not
    observe the launch moment on the dispatched path, so the launched event is
    emitted together with the terminal event rather than at AAP launch time.
    Template-ID-based events require ``workflow_job_template_id``; name-based
    lookups skip audit events (the emitters no-op without a template ID).
    """
    activity.heartbeat({HEARTBEAT_STOP_MONITOR: True})
    start_time = time.time()

    try:
        config = AAPWorkflowJobTemplateExecutorParameters.model_validate(
            {key: value for key, value in input_config.items() if not key.startswith("_")}
        )
        execution_uuid = _parse_optional_uuid(execution_id, "execution_id")
        actor_id = _parse_optional_uuid(created_by_user_id, "created_by_user_id")
    except Exception:  # noqa: BLE001
        msg = "AAP workflow activity configuration or execution ID is invalid"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True) from None

    if execution_uuid is None:
        msg = "AAP workflow activity requires an execution ID"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True) from None

    runtime_context = _aap_runtime_context(input_config)
    base_url = str(runtime_context[_AAP_ENDPOINT_CONTEXT_KEY])
    template_id = config.workflow_job_template_id

    # ``integration_id`` is an AO-only identifier: the resolved integration is
    # projected into the runtime context above, and the plugin's input schema
    # (additionalProperties: false) rejects it. ``credential_id`` and
    # ``credential_bindings`` are consumed by the invocation builder.
    dispatch_config = {key: value for key, value in input_config.items() if key != "integration_id"}

    result = await _dispatch_to_ep(
        dispatch_config,
        output_config,
        execution_uuid,
        None,
        _PLUGIN_NAME,
        runtime_context_additions=runtime_context,
    )
    if result is None:
        # The work item was accepted; completion arrives through the
        # AO-owned callback path.
        raise_complete_async = cast("Callable[[], Any]", activity.raise_complete_async)
        raise_complete_async()
        return {}

    output = AAPWorkflowJobTemplateOutput(
        workflow_job_id=result.get("workflow_job_id"),
        workflow_job_url=result.get("workflow_job_url"),
        workflow_job_status=result.get("workflow_job_status"),
        artifacts=result.get("artifacts"),
        created=result.get("created"),
        started=result.get("started"),
        finished=result.get("finished"),
    )
    duration_ms = int((time.time() - start_time) * 1000)

    def _emit_launched() -> None:
        if output.workflow_job_id is not None:
            emit_launched(
                execution_uuid,
                template_id,
                job_id=output.workflow_job_id,
                job_url=output.workflow_job_url or "",
                base_url=base_url,
                node_type=_NODE_TYPE,
                job_template_name=config.workflow_job_template_name,
                actor_id=actor_id,
            )

    if result.get("status") == "failed":
        _emit_launched()
        emit_failed(
            execution_uuid,
            template_id,
            job_status=output.workflow_job_status or "failed",
            duration_ms=duration_ms,
            node_type=_NODE_TYPE,
            job_id=output.workflow_job_id,
            job_url=output.workflow_job_url,
            error_message=result.get("error"),
            actor_id=actor_id,
        )
        msg = (
            f"AAP workflow job {result.get('workflow_job_id')} failed with status: {result.get('workflow_job_status')}"
        )
        raise ApplicationError(
            msg,
            {"output": dump_output(output, output_config), "error": result.get("error")},
            type="AAPWorkflowJobExecutionError",
            non_retryable=True,
        )

    _emit_launched()
    emit_completed(
        execution_uuid,
        template_id,
        job_id=output.workflow_job_id or 0,
        job_url=output.workflow_job_url or "",
        final_status=output.workflow_job_status or "successful",
        duration_ms=duration_ms,
        artifacts=output.artifacts,
        node_type=_NODE_TYPE,
        actor_id=actor_id,
    )
    return {"output": dump_output(output, output_config)}
