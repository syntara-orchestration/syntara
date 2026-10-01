"""Adapt existing TFE workflow contracts to a manifest-selected SDK runtime."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, ClassVar, Protocol

from pydantic import ConfigDict, Field, ValidationError
from sqlmodel import SQLModel

from syntara.step_nodes.contracts import ManifestCatalog, StepContractError, StepResult, StepTransport
from syntara.terraform.errors import TFEError, TFEErrorCode
from syntara.terraform.step_bindings import TFE_STEP_BINDINGS
from syntara.terraform.step_mapping import sdk_inputs, workflow_output
from syntara.workflows.workflow_engine.activities.tfe_common import data_attrs, extract_bearer_token

if TYPE_CHECKING:
    from collections.abc import Mapping


class TFEStepExecutor(Protocol):
    """Workflow-facing port; receives already resolved integration and credentials."""

    async def execute(
        self, node_type: str, input_config: dict[str, Any], outputs: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Return the existing workflow output contract, not an SDK envelope."""
        ...


class TFERuntimeResult(SQLModel):
    """Version-one TFE SDK Result payload."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", strict=True)  # type: ignore[assignment]
    operation: str
    data: dict[str, Any] | list[dict[str, Any]] | None
    related: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)
    http_status: int = Field(ge=200, lt=300)


_CONTROL_FLAGS = {
    "apply_run": "is-confirmable",
    "discard_run": "is-discardable",
    "cancel_run": "is-cancelable",
    "force_cancel_run": "is-force-cancelable",
}
_READ_OPERATIONS = frozenset(
    binding.operation
    for binding in TFE_STEP_BINDINGS.values()
    if binding.operation.startswith(("list_", "get_", "fetch_"))
)


class SDKTFEStepExecutor:
    """Manifest and transport injection; never import or launch the SDK implicitly."""

    def __init__(self, catalog: ManifestCatalog, transport: StepTransport) -> None:
        """Bind a trusted catalog and an execution-plane implementation."""
        self._catalog = catalog
        self._transport = transport

    async def _dispatch(self, operation: str, inputs: dict[str, Any], token: str) -> dict[str, Any]:
        try:
            invocation = self._catalog.invocation("tfe_" + operation, inputs, {"token": token})
        except StepContractError:
            message = "TFE SDK manifest or input contract mismatch"
            raise TFEError(message, error_code=TFEErrorCode.VALIDATION) from None
        try:
            async with asyncio.timeout(invocation.execution_timeout_seconds):
                raw = await self._transport.execute(invocation)
        except Exception:  # noqa: BLE001 -- transport exceptions may contain credentials; sanitize at this boundary
            # A transport may include credentials in its exception text. Never
            # reflect it into Temporal history. Cancellation is not caught.
            code = TFEErrorCode.TRANSIENT if operation in _READ_OPERATIONS else TFEErrorCode.OUTCOME_UNKNOWN
            message = "TFE SDK transport failed; verify mutations before retrying"
            raise TFEError(message, error_code=code, retryable=False) from None
        return self._decode(operation, raw)

    @staticmethod
    def _decode(operation: str, raw: Mapping[str, Any]) -> dict[str, Any]:
        try:
            envelope = StepResult.from_payload(raw)
            if envelope.StatusCode != 0:
                code = TFEErrorCode.TRANSIENT if operation in _READ_OPERATIONS else TFEErrorCode.OUTCOME_UNKNOWN
                # The current SDK does not provide structured remote error codes.
                # Do not parse ErrorMessage strings or infer mutation retryability.
                message = "TFE SDK node reported failure"
                raise TFEError(message, error_code=code, retryable=False)
            result = TFERuntimeResult.model_validate(envelope.Result)
        except (StepContractError, ValidationError):
            message = "Invalid TFE SDK result contract"
            raise TFEError(message, error_code=TFEErrorCode.VALIDATION) from None
        if result.operation != operation:
            message = "Unexpected SDK operation result"
            raise TFEError(message, error_code=TFEErrorCode.VALIDATION)
        return result.model_dump()

    async def execute(
        self, node_type: str, input_config: dict[str, Any], outputs: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Resolve compatibility mappings and preserve existing output selection."""
        try:
            binding = TFE_STEP_BINDINGS[node_type]
            parameters = binding.parameters.model_validate(input_config)
        except (KeyError, ValidationError):
            message = "Invalid TFE workflow parameters"
            raise TFEError(message, error_code=TFEErrorCode.VALIDATION) from None
        integration = input_config.get("_resolved_integration")
        if not isinstance(integration, dict) or not integration.get("base_url") or not integration.get("organization"):
            message = "Missing resolved TFE integration"
            raise TFEError(message, error_code=TFEErrorCode.CONFIG_MISSING)
        token = extract_bearer_token(input_config.get("_resolved_credentials"))
        values = parameters.model_dump()
        if "sensitive" not in parameters.model_fields_set:
            # Preserve the PATCH semantics: an omitted flag must leave the
            # existing TFE variable setting unchanged.
            values.pop("sensitive", None)
        inputs = sdk_inputs(binding.operation, values, integration)

        if binding.operation in _CONTROL_FLAGS:
            run = await self._dispatch(
                "get_run_status",
                {
                    "base_url": inputs["base_url"],
                    "credential_id": inputs["credential_id"],
                    "run_id": inputs["run_id"],
                    "include_plan": False,
                },
                token,
            )
            actions = data_attrs({"data": run["data"]}).get("actions") or {}
            if not actions.get(_CONTROL_FLAGS[binding.operation]):
                message = "TFE run action is not currently available"
                raise TFEError(message, error_code=TFEErrorCode.STATE_CONFLICT)
        if binding.operation == "link_vcs_to_workspace":
            installation = await self._dispatch(
                "get_installation_details",
                {
                    "base_url": inputs["base_url"],
                    "credential_id": inputs["credential_id"],
                    "github_app_installation_id": inputs["github_app_installation_id"],
                },
                token,
            )
            attrs = data_attrs({"data": installation["data"]})
            owner = attrs.get("name") or attrs.get("owner")
            if not isinstance(owner, str) or not owner:
                message = "GitHub installation has no owner"
                raise TFEError(message, error_code=TFEErrorCode.NOT_FOUND)
            inputs["repository"] = f"{owner}/{values['repository']}"
            values["repository"] = inputs["repository"]

        result = await self._dispatch(binding.operation, inputs, token)
        try:
            normalized = workflow_output(binding.operation, result, values, integration["organization"])
            return binding.output.model_validate(normalized).dump(outputs)
        except (ValidationError, KeyError, TypeError, AttributeError):
            message = "Invalid TFE SDK resource payload"
            raise TFEError(message, error_code=TFEErrorCode.VALIDATION) from None
