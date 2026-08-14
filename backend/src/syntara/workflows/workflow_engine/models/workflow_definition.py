"""Activity executor configuration models for V2 workflows.

This module contains Pydantic models for activity executor configurations.
These are used by V2 workflow activities for config validation.
"""

import json
import re
import uuid
from enum import Enum, IntEnum, StrEnum
from typing import Any, ClassVar, Literal
from urllib.parse import urlparse
from zoneinfo import available_timezones

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator
from pydantic.functional_validators import ModelWrapValidatorHandler

from syntara.aap.models.responses import AAPJobType as AAPJobType  # noqa: PLC0414
from syntara.core.constants import WebhookLimits
from syntara.core.exceptions import SafeValueError
from syntara.workflows.json_schema_validation import validate_json_schema_definition
from syntara.workflows.utils.iso8601_interval import parse_iso8601_repeating_interval
from syntara.workflows.utils.output_mapping import apply_output_mapping
from syntara.workflows.workflow_engine.models.aap_types import AAPResourceType

logger = structlog.stdlib.get_logger(__name__)

# Template expression pattern - matches ${...} expressions
TEMPLATE_PATTERN = re.compile(r"\$\{[^}]+\}")

_CONFIG_VALIDATION_FAILED = "Config validation failed"


def validate_tool_selection_coherence(
    strategy: str | None,
    selections: list[str],
    source: str,
) -> None:
    """Validate that tool_selection_strategy and tool_selections are coherent.

    Shared validation used by both AgenticExecutorParameters and InvocationMetadata.

    Raises SafeValueError if:
    - SELECTED with empty selections
    - NONE/ALL/None with non-empty selections
    """
    if strategy == "SELECTED" and not selections:
        msg = "tool_selections must not be empty when tool_selection_strategy is 'SELECTED'"
        logger.warning(
            _CONFIG_VALIDATION_FAILED,
            source=source,
            field="tool_selection_strategy",
            strategy=strategy,
            reason="empty_tool_selections",
        )
        raise SafeValueError(msg)

    if strategy in ("NONE", "ALL", None) and selections:
        label = f"'{strategy}'" if strategy else "not set"
        msg = f"tool_selections must be empty when tool_selection_strategy is {label}"
        logger.warning(
            _CONFIG_VALIDATION_FAILED,
            source=source,
            field="tool_selection_strategy",
            strategy=strategy,
            tool_count=len(selections),
            reason="unexpected_tool_selections",
        )
        raise SafeValueError(msg)


def validate_uuid_or_template(value: str, field_label: str) -> str:
    """Validate that a string is either a valid UUID or a template expression.

    Raises SafeValueError if neither.
    """
    if TEMPLATE_PATTERN.search(value):
        return value
    try:
        uuid.UUID(value)
    except ValueError as err:
        msg = f"Invalid UUID format for {field_label}: '{value}'. Must be a valid UUID."
        logger.warning(_CONFIG_VALIDATION_FAILED, field=field_label, reason="invalid_uuid")
        raise SafeValueError(msg) from err
    return value


class TemplateAwareBaseModel(BaseModel):
    """Base model that allows template expressions in any field.

    Template expressions like ${input.field} or ${workflow.vars.count} bypass
    type validation and constraints, allowing them to be stored as strings and
    evaluated at runtime during workflow execution.

    Non-template values are validated normally with full type checking and
    Field constraints (ge, le, min_length, etc.).
    """

    model_config = ConfigDict(validate_assignment=True)

    @field_validator("*", mode="wrap")
    @classmethod
    def allow_template_strings(
        cls,
        value: Any,  # noqa: ANN401
        handler: ModelWrapValidatorHandler[Any],
        info: ValidationInfo,  # noqa: ARG003
    ) -> Any:  # noqa: ANN401
        """Allow template expressions to bypass validation for any field."""
        # Template expression - return directly, bypass all validators
        if isinstance(value, str) and TEMPLATE_PATTERN.search(value):
            return value

        # For non-template values, run normal validation
        return handler(value)


class ActivityName(StrEnum):
    """Temporal activity names for V2 workflows."""

    # Triggers
    MANUAL_TRIGGER = "manual_trigger"
    SCHEDULED_TRIGGER = "scheduled_trigger"
    WEBHOOK_TRIGGER = "webhook_trigger"
    EDA_TRIGGER = "eda_trigger"
    # Control nodes
    CONDITION = "condition"
    CONVERGE = "converge"
    LOOP = "loop"
    SWITCH = "switch"
    WAIT = "wait"
    # Executor nodes
    AAP_JOB_TEMPLATE = "execute_aap_job_template_activity"
    AAP_WORKFLOW_JOB_TEMPLATE = "execute_aap_workflow_job_template_activity"
    AGENTIC = "execute_agentic_activity"
    APPROVAL = "execute_approval_activity"
    HTTP_REQUEST = "execute_http_request_activity"
    INTERNAL_ACTIVITY = "execute_internal_activity"
    SCRIPT = "execute_script_activity"
    # Internal
    CREDENTIAL_RESOLUTION = "resolve_workflow_credentials"
    INTEGRATION_RESOLUTION = "resolve_workflow_integration"
    APPROVER_RESOLUTION = "resolve_approvers"
    EXPIRE_APPROVAL = "expire_approval_requests"
    CANCEL_APPROVAL = "cancel_approval_requests"
    ACTIVITY_MONITORING = "register_activity_monitoring"
    COMPLETE_WAIT = "complete_wait"
    FETCH_RUNTIME_SETTINGS = "fetch_workflow_runtime_settings"
    VALIDATE_NODE_REFERENCES = "validate_node_references"


# Enums
class NodeType(str, Enum):
    """Node types for V2 workflows (used by telemetry)."""

    # Triggers
    MANUAL_TRIGGER = "manual_trigger"
    SCHEDULED_TRIGGER = "scheduled_trigger"
    WEBHOOK_TRIGGER = "webhook_trigger"
    EDA_TRIGGER = "eda_trigger"
    # Control nodes
    CONDITION = "condition"
    CONVERGE = "converge"
    LOOP = "loop"
    SWITCH = "switch"
    WAIT = "wait"
    # Executor nodes
    AAP_JOB_TEMPLATE = "aap_job_template"
    AAP_WORKFLOW_JOB_TEMPLATE = "aap_workflow_job_template"
    AGENTIC = "agentic"
    APPROVAL = "approval"
    HTTP_REQUEST = "http_request"
    INTERNAL_ACTIVITY = "internal_activity"
    SCRIPT = "script"


def resolve_trigger_node(
    workflow_def: dict[str, Any],
    trigger_node_id: str,
) -> tuple[str, dict[str, Any]]:
    """Resolve a trigger node from a workflow definition.

    Args:
        workflow_def: Complete workflow definition dict.
        trigger_node_id: Trigger node ID to look up.

    Returns:
        Tuple of (resolved trigger_node_id, trigger node dict).

    Raises:
        SafeValueError: If no matching trigger is found.

    """
    for trigger in workflow_def.get("triggers", []):
        if trigger.get("id") == trigger_node_id:
            return trigger_node_id, trigger
    msg = f"Specified trigger_node_id '{trigger_node_id}' not found in workflow triggers"
    raise SafeValueError(msg)


class ConvergeStrategy(StrEnum):
    """Convergence strategies for converge nodes."""

    ALL = "all"
    ANY = "any"


class LoopType(StrEnum):
    """Loop sub-types for V2 workflows."""

    FOR_EACH = "for_each"
    DO_WHILE = "do_while"


class ForEachLoopState(BaseModel):
    """State for a for_each loop iteration."""

    model_config = ConfigDict(frozen=False)

    type: LoopType = LoopType.FOR_EACH
    items: list[Any]
    current_index: int = 0


class DoWhileLoopState(BaseModel):
    """State for a do_while loop iteration."""

    model_config = ConfigDict(frozen=False)

    type: LoopType = LoopType.DO_WHILE
    condition: str | None
    max_iterations: int | None = None
    current_index: int = 0


LoopState = ForEachLoopState | DoWhileLoopState


class ActivityTerminalStatus(str, Enum):
    """Terminal activity execution statuses for telemetry events."""

    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class WorkflowTerminalStatus(str, Enum):
    """Terminal workflow execution statuses for telemetry events."""

    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScriptLanguage(str, Enum):
    """Supported script languages for script executor."""

    BASH = "bash"
    PYTHON = "python"


class HTTPMethod(str, Enum):
    """Supported HTTP methods for API requests."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"
    CONNECT = "CONNECT"
    TRACE = "TRACE"


# Node-level settings models


class RetryPolicyParameters(BaseModel):
    """Retry policy parameters for a node.

    Only applies to nodes whose settings class is NodeSettingsFull
    (http_request, aap_job_template, aap_workflow_job_template).

    All fields default to None — the engine merges with global catalog values
    (workflow_engine.retry_*) for any unset field. Set max_retries=0 to
    explicitly disable retry, overriding global defaults.
    """

    max_retries: int | None = Field(default=None, ge=0, description="Retries after initial attempt. 0 = no retry.")
    initial_interval: int | None = Field(default=None, ge=1, description="Initial retry interval in seconds.")
    max_interval: int | None = Field(default=None, ge=1, description="Maximum retry interval in seconds.")
    backoff_coefficient: float | None = Field(
        default=None, ge=1.0, description="Multiplier per retry. 1.0 = fixed, >1.0 = exponential."
    )


class NodeSettingsBase(BaseModel):
    """Base node settings — no user-configurable fields."""

    model_config = ConfigDict(extra="forbid")


class NodeSettingsCof(NodeSettingsBase):
    """Settings with continue_on_failure only (converge, loop)."""

    continue_on_failure: bool | None = None


class NodeSettingsCofDisabled(NodeSettingsCof):
    """Settings with disabled and continue_on_failure (wait)."""

    disabled: bool | None = None


class NodeSettingsNoRetry(NodeSettingsCofDisabled):
    """Settings with disabled, continue_on_failure, and timeout (script, agentic, approval)."""

    timeout: int | None = Field(default=None, ge=1)


class NodeSettingsFull(NodeSettingsNoRetry):
    """Full settings with retry_policy (http_request, aap_job_template, aap_workflow_job_template)."""

    retry_policy: RetryPolicyParameters | None = None


# Executor configuration models
class ScriptExecutorParameters(TemplateAwareBaseModel):
    """Parameters for script executor."""

    language: ScriptLanguage
    code: str = Field(min_length=1, description="Script code to execute")
    environment: dict[str, str] = Field(default_factory=dict, description="Environment variables")
    credential_id: str | None = Field(default=None, description="Nexus credential UUID for credential scrubbing")

    @field_validator("environment", mode="before")
    @classmethod
    def coerce_environment_values_to_str(cls, v: Any) -> Any:  # noqa: ANN401
        """Coerce environment variable values to strings.

        Template-resolved values like return_code may arrive as int/float/bool
        after namespace resolution, but environment variables are always strings.
        Uses json.dumps for non-string types to produce valid JSON (lowercase
        booleans, double-quoted strings in dicts/lists).
        """
        if isinstance(v, dict):
            return {k: val if isinstance(val, str) else json.dumps(val) for k, val in v.items()}
        return v


class APIExecutorParameters(TemplateAwareBaseModel):
    """Parameters for API executor (http_request activity)."""

    method: HTTPMethod = Field(description="HTTP method")
    url: str | None = Field(default=None, description="Request URL (optional when a Secret URL credential provides it)")
    headers: dict[str, Any] = Field(default_factory=dict)
    body: dict[str, Any] | str | None = None
    query_params: dict[str, Any] = Field(default_factory=dict)
    credential_id: str | None = Field(
        default=None,
        description="Nexus credential UUID for authentication or Secret URL.",
    )

    @field_validator("url")
    @classmethod
    def validate_url_scheme(cls, v: str | None) -> str | None:
        """Restrict URL to http/https schemes to prevent SSRF."""
        if v is None:
            return v
        if TEMPLATE_PATTERN.search(v):
            return v
        parsed = urlparse(v)
        if parsed.scheme and parsed.scheme not in ("http", "https"):
            msg = f"URL scheme '{parsed.scheme}' is not allowed. Only http:// and https:// are supported."
            raise SafeValueError(msg)
        return v


class IntegrationConnectionConfig(BaseModel):
    """Execution credential override for one integration.

    When included in AgenticExecutorParameters.integration_connections, this credential
    is used for calls against that integration instead of the integration's
    management credential.
    """

    integration_id: str = Field(description="UUID of the integration")
    credential_id: str = Field(
        description="Nexus credential UUID for execution calls (distinct from management credential)"
    )

    @field_validator("integration_id", "credential_id")
    @classmethod
    def validate_uuid_format(cls, v: str, info: ValidationInfo) -> str:
        """Validate that each ID is a valid UUID or a template expression."""
        return validate_uuid_or_template(v, info.field_name or "unknown")


class AgenticExecutorParameters(TemplateAwareBaseModel, populate_by_name=True):
    """Parameters for agentic executor."""

    prompt: str = Field(description="Prompt template for the agent")
    agent: str | None = None
    llm_model_id: str | None = Field(
        default=None,
        description="UUID of the LLMModel record identifying the provider integration and model.",
    )
    credential_id: str | None = Field(
        default=None,
        description="Nexus credential UUID for LLM provider authentication",
    )
    file_ids: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="File IDs for agent context",
    )
    response_schema: dict[str, Any] | str | None = Field(
        default=None,
        alias="responseSchema",
        description="JSON Schema for structured output. When defined, agent output conforms to this schema.",
    )
    integration_connections: list[IntegrationConnectionConfig] | None = Field(
        default=None,
        description=(
            "Per-integration execution credentials. "
            "Each entry overrides the management credential for that integration. "
            "Integrations not listed fall back to their management credential."
        ),
    )
    tool_selection_strategy: Literal["ALL", "NONE", "SELECTED"] | None = Field(
        default=None,
        description="ALL (all enabled tools), NONE (no tools), or SELECTED (specific tools from tool_selections)",
    )
    tool_selections: list[str] = Field(
        default_factory=list,
        description="Tool UUIDs to make available when tool_selection_strategy is SELECTED",
    )

    @field_validator("llm_model_id", "credential_id")
    @classmethod
    def validate_uuid_fields(cls, v: str | None, info: ValidationInfo) -> str | None:
        """Validate that UUID fields are valid UUIDs or template expressions."""
        if v is not None:
            validate_uuid_or_template(v, info.field_name or "unknown")
        return v

    @field_validator("tool_selections")
    @classmethod
    def validate_tool_selections_format(cls, v: list[str]) -> list[str]:
        """Validate each tool_selection is a valid UUID (unless it's a template expression)."""
        for i, tool_id in enumerate(v):
            validate_uuid_or_template(tool_id, f"tool_selections[{i}]")
        return v

    @field_validator("prompt")
    @classmethod
    def validate_prompt_security(cls, v: str) -> str:
        """Validate prompt content for security.

        Prompt length is validated at runtime by the agentic activity
        against the ``workflow_engine.max_prompt_length`` setting.
        """
        if "\0" in v:
            msg = "Prompt contains null bytes"
            raise SafeValueError(msg)
        return v

    @field_validator("file_ids")
    @classmethod
    def validate_file_ids_format(cls, v: list[str]) -> list[str]:
        """Validate each file_id is a valid UUID format (unless it's a template expression)."""
        for i, file_id in enumerate(v):
            validate_uuid_or_template(file_id, f"file_ids[{i}]")
        return v

    @field_validator("response_schema")
    @classmethod
    def validate_response_schema_structure(cls, v: dict[str, Any] | str | None) -> dict[str, Any] | str | None:
        """Validate response_schema against JSON Schema Draft-07 with security hardening.

        Checks structural validity, rejects $ref (SSRF prevention), and detects
        ReDoS-vulnerable regex patterns. Uses the same validation as webhook
        input_schema for consistency.

        Template expressions (str matching ${...}) bypass this validator via
        TemplateAwareBaseModel's wrap validator and arrive here as str.
        Non-template values arrive as dict or None.
        """
        if v is None or isinstance(v, str):
            return v
        try:
            validate_json_schema_definition(v)
        except ValueError as e:
            msg = f"response_schema: {e}"
            logger.warning(
                _CONFIG_VALIDATION_FAILED, source="AgenticExecutorParameters", field="response_schema", reason=str(e)
            )
            raise SafeValueError(msg) from None
        return v

    @model_validator(mode="after")
    def _validate_tool_selection_coherence(self) -> "AgenticExecutorParameters":
        """Validate that tool_selection_strategy and tool_selections are coherent."""
        strategy = self.tool_selection_strategy

        if isinstance(strategy, str) and TEMPLATE_PATTERN.search(strategy):
            return self

        validate_tool_selection_coherence(strategy, self.tool_selections, "AgenticExecutorParameters")
        return self


class AAPVerbosity(IntEnum):
    """Ansible Automation Platform job verbosity levels (0-5)."""

    NORMAL = 0
    VERBOSE = 1
    MORE_VERBOSE = 2
    DEBUG = 3
    CONNECTION_DEBUG = 4
    WINRM_DEBUG = 5


class AAPResourceReferenceMixin(BaseModel):
    """Mixin for AAP executor configs with common fields and resource reference validation.

    Provides shared fields used by both AAP job template and workflow job template configs,
    including authentication, organization/inventory references, prompt-on-launch overrides,
    and label support.
    """

    # Authentication
    credential_id: str | None = Field(
        default=None,
        description=(
            "Nexus credential UUID for Ansible Automation Platform API authentication. "
            "Separate from legacy credentials list."
        ),
    )
    integration_id: str | None = Field(
        default=None,
        description="UUID of the Ansible Automation Platform Gateway integration for connection URL resolution.",
    )

    # Organization and inventory references
    organization_id: int | None = Field(
        default=None,
        ge=1,
        description="Ansible Automation Platform organization ID (takes precedence over organization_name)",
        alias="organizationId",
    )
    organization_name: str | None = Field(
        default=None,
        description="Ansible Automation Platform organization name (used with template_name or inventory_name)",
    )
    inventory_id: int | None = Field(
        default=None,
        ge=1,
        description="Override default inventory by ID (mutually exclusive with inventory_name)",
    )
    inventory_name: str | None = Field(
        default=None,
        description="Override default inventory by name (requires organization_name)",
    )

    # Prompt-on-launch overrides (common to both job and workflow job templates)
    extra_vars: dict[str, Any] = Field(
        default_factory=dict,
        description="Extra variables to pass to job/workflow job",
    )
    limit: str | None = Field(
        default=None,
        description="Limit job execution to specific hosts",
    )
    tags: str | None = Field(
        default=None,
        description="Ansible tags to run (comma-separated)",
    )
    skip_tags: str | None = Field(
        default=None,
        description="Ansible tags to skip (comma-separated)",
    )
    labels: list[str] | None = Field(
        default=None,
        description=(
            "Ansible Automation Platform label names to append to template's default labels. "
            "Names are resolved to IDs at launch time. "
            "New labels that don't exist in Ansible Automation Platform will be created automatically. "
            "Note: Labels are APPENDED to template defaults, not replaced."
        ),
    )

    @field_validator("integration_id", "credential_id")
    @classmethod
    def validate_uuid_fields(cls, v: str | None, info: ValidationInfo) -> str | None:
        """Validate that UUID fields are valid UUIDs or template expressions."""
        if v is not None:
            validate_uuid_or_template(v, info.field_name or "unknown")
        return v

    def _validate_id_or_name_reference(
        self,
        id_value: int | str | None,
        name_value: str | None,
        org_value: str | None,
        resource_type: str,
        *,
        required: bool = True,
    ) -> None:
        """Validate resource reference by ID or name."""
        # Skip validation if any value is a template expression
        is_id_template = isinstance(id_value, str) and TEMPLATE_PATTERN.search(id_value)
        is_name_template = isinstance(name_value, str) and TEMPLATE_PATTERN.search(name_value)
        is_org_template = isinstance(org_value, str) and TEMPLATE_PATTERN.search(org_value)

        if is_id_template or is_name_template or is_org_template:
            return

        has_id = id_value is not None
        has_name = bool(name_value)

        # Name requires organization (when ID not provided)
        if not has_id and has_name and not org_value:
            msg = f"organization_name is required when using {resource_type}_name"
            raise SafeValueError(msg)

        # Require either ID or name
        if required and not has_id and not has_name:
            msg = f"Either {resource_type}_id or {resource_type}_name must be specified"
            raise SafeValueError(msg)


class AAPJobTemplateExecutorParameters(AAPResourceReferenceMixin, TemplateAwareBaseModel):
    """Parameters for Ansible Automation Platform Job Template executor.

    Inherits common Ansible Automation Platform fields from AAPResourceReferenceMixin (credential_id, organization,
    inventory, extra_vars, limit, tags, skip_tags, labels, timeout).
    """

    # Job template reference
    job_template_id: int | None = Field(
        default=None,
        ge=1,
        description="Ansible Automation Platform job template ID to launch",
    )
    job_template_name: str | None = Field(
        default=None,
        description="Ansible Automation Platform job template name (used with organization_name)",
    )

    # Job-specific credentials (workflow jobs don't support this)
    job_credentials: list[int] | None = Field(
        default=None,
        description=(
            "List of Ansible Automation Platform credential IDs to use (takes precedence over credential_names)"
        ),
    )
    credential_names: list[str] | None = Field(
        default=None,
        description=(
            "List of Ansible Automation Platform credential names to use "
            "(requires organization_name, resolved at launch time)"
        ),
        alias="credentialNames",
    )

    # Job-specific prompt-on-launch fields
    verbosity: AAPVerbosity = Field(
        default=AAPVerbosity.NORMAL,
        description="Job verbosity level (0-5)",
    )
    job_type: AAPJobType | None = Field(
        default=None,
        description="Job type override: 'run' or 'check' (dry run)",
    )
    forks: int | None = Field(
        default=None,
        ge=0,
        description="Number of parallel forks for job execution",
    )
    job_slicing: int | None = Field(
        default=None,
        ge=1,
        description="Number of job slices",
    )
    diff_mode: bool | None = Field(
        default=None,
        description="Enable diff mode for playbook runs",
    )

    # Deferred prompt-on-launch fields (require ID resolution)
    execution_environment: str | None = Field(
        default=None,
        description="Execution environment override (deferred — requires ID resolution)",
    )
    instance_group_id: int | None = Field(
        default=None,
        ge=1,
        description="Override instance group by ID (takes precedence over instance_group_name)",
    )
    instance_group_name: str | None = Field(
        default=None,
        description="Override instance group by name (requires organization_name for lookup)",
    )

    @model_validator(mode="after")
    def validate_references(self) -> "AAPJobTemplateExecutorParameters":
        """Validate job template and inventory references."""
        # Validate job template reference
        self._validate_id_or_name_reference(
            self.job_template_id,
            self.job_template_name,
            self.organization_name,
            AAPResourceType.JOB_TEMPLATES.field_prefix,
            required=True,
        )

        # Validate inventory reference (optional)
        self._validate_id_or_name_reference(
            self.inventory_id,
            self.inventory_name,
            self.organization_name,
            AAPResourceType.INVENTORIES.field_prefix,
            required=False,
        )

        return self


class AAPWorkflowJobTemplateExecutorParameters(AAPResourceReferenceMixin, TemplateAwareBaseModel):
    """Parameters for Ansible Automation Platform Workflow Job Template executor.

    Inherits common Ansible Automation Platform fields from AAPResourceReferenceMixin (credential_id, organization,
    inventory, extra_vars, limit, tags, skip_tags, labels, timeout).
    """

    # Workflow job template reference
    workflow_job_template_id: int | None = Field(
        default=None,
        ge=1,
        description="Ansible Automation Platform workflow job template ID to launch",
    )
    workflow_job_template_name: str | None = Field(
        default=None,
        description="Ansible Automation Platform workflow job template name (used with organization_name)",
    )

    # Workflow-specific prompt-on-launch field (not available for regular job templates)
    scm_branch: str | None = Field(
        default=None,
        description="SCM branch override for projects in workflow",
    )

    @model_validator(mode="after")
    def validate_references(self) -> "AAPWorkflowJobTemplateExecutorParameters":
        """Validate workflow job template and inventory references."""
        # Validate workflow job template reference
        self._validate_id_or_name_reference(
            self.workflow_job_template_id,
            self.workflow_job_template_name,
            self.organization_name,
            AAPResourceType.WORKFLOW_JOB_TEMPLATES.field_prefix,
            required=True,
        )

        # Validate inventory reference (optional)
        self._validate_id_or_name_reference(
            self.inventory_id,
            self.inventory_name,
            self.organization_name,
            AAPResourceType.INVENTORIES.field_prefix,
            required=False,
        )

        return self


# ---------------------------------------------------------------------------
# Control node parameters models
# ---------------------------------------------------------------------------


class ConditionNodeParameters(BaseModel):
    """Parameters for condition (if/then/else) control nodes."""

    condition: str = Field(min_length=1, description="Expression that evaluates to boolean")


class SwitchCase(BaseModel):
    """A single case in a switch node."""

    port: str = Field(min_length=1, description="Port identifier for this case")
    label: str = Field(min_length=1, description="Display label for this case")
    condition: str = Field(min_length=1, description="Boolean expression to evaluate")


class SwitchNodeParameters(BaseModel):
    """Parameters for switch (multi-branch) control nodes."""

    cases: list[SwitchCase] = Field(min_length=1, description="Ordered list of cases")
    default_port: str | None = Field(default=None, description="Port to route to when no case matches")


class ConvergeNodeParameters(BaseModel):
    """Parameters for converge (synchronization) control nodes."""

    strategy: ConvergeStrategy | None = Field(default=None, description="Convergence strategy")
    n_required: int | None = Field(default=None, ge=1, description="Branches required when strategy is 'any'")
    wait_duration: int | None = Field(default=None, ge=1, description="Wait timeout in seconds")


class ForEachLoopParameters(BaseModel):
    """Parameters for for_each loop nodes."""

    type: Literal["for_each"]
    items: str = Field(min_length=1, description="Array expression to iterate over")
    max_iterations: int | None = Field(default=None, ge=1, description="Maximum items to process")


class DoWhileLoopParameters(BaseModel):
    """Parameters for do_while loop nodes."""

    type: Literal["do_while"]
    condition: str = Field(min_length=1, description="Boolean expression evaluated after each iteration")
    max_iterations: int | None = Field(default=None, ge=1, description="Maximum iterations")


class WaitNodeParameters(BaseModel):
    """Parameters for wait (delay) control nodes."""

    duration: int = Field(ge=1, description="Wait duration in seconds")


class ApprovalNodeParameters(BaseModel):
    """Parameters for approval gate nodes."""

    credential_id: str | None = Field(default=None, description="Nexus credential UUID")
    approver_users: list[str] | None = Field(default=None, max_length=100, description="Usernames who can approve")
    approver_groups: list[str] | None = Field(
        default=None, max_length=50, description="Group names whose members can approve"
    )
    prompt: str | None = Field(default=None, description="Message to display to approvers")
    fallback_decision: Literal["approve", "reject"] | None = Field(
        default=None, description="Decision when approval times out with continue_on_failure"
    )
    decision_window: int | None = Field(default=None, ge=1, description="Response timeout in seconds")


class WebhookTriggerParameters(TemplateAwareBaseModel):
    """Parameters for webhook trigger nodes.

    Defines the endpoint configuration for a webhook trigger, including the
    URL path slug, an optional JSON Schema for payload validation, and
    authorized service accounts.

    Attributes:
        webhook_path: Unique URL slug identifying this webhook endpoint
            (e.g., "jira-updates"). Becomes part of the final URL:
            /api/v1/webhooks/{webhook_path}
        input_schema: Optional JSON Schema (Draft-07) for validating incoming
            webhook payloads. If set, requests with non-conforming payloads
            are rejected with 422 Unprocessable Content.
        authorized_service_account_ids: UUIDs of service accounts authorized
            to invoke this trigger endpoint.

    """

    webhook_path: str = Field(
        min_length=WebhookLimits.PATH_MIN_LENGTH,
        max_length=WebhookLimits.PATH_MAX_LENGTH,
        pattern=WebhookLimits.PATH_PATTERN,
        description="Unique URL slug identifying this webhook endpoint",
    )
    input_schema: dict[str, Any] | None = Field(
        default=None,
        description="Optional JSON Schema (Draft-07) for validating incoming webhook payloads",
    )
    authorized_service_account_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="UUIDs of service accounts authorized to invoke this trigger endpoint",
    )

    @field_validator("input_schema")
    @classmethod
    def validate_schema(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        """Validate JSON Schema at definition time.

        Rejects structurally invalid schemas, schemas containing ``$ref``
        references (SSRF risk), and schemas with regex patterns that could
        cause catastrophic backtracking (ReDoS).
        """
        if v is None:
            return v

        validate_json_schema_definition(v)
        return v


# Node output models


class NodeOutput(BaseModel):
    """Base class for all node output models.

    Each node type that defines a resultSchema has a corresponding
    NodeOutput subclass. The dump() method serialises the model and
    optionally applies output-mapping so that Temporal only persists
    the fields the workflow author selected.

    All fields default to None. On success the executor populates every
    field; on failure only the fields available before the error are set,
    the rest stay None. This guarantees a uniform shape so downstream
    nodes never get KeyError on a known field.
    """

    def dump(self, output_config: dict[str, str] | None = None) -> dict[str, Any]:
        """Serialise and apply output mapping."""
        return apply_output_mapping(self.model_dump(), output_config)


class ScriptOutput(NodeOutput):
    """Output model for script executor nodes."""

    return_code: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    stdout_json: Any = None


class HttpRequestOutput(NodeOutput):
    """Output model for HTTP request executor nodes."""

    status_code: int | None = None
    body: Any = None
    headers: dict[str, Any] | None = None
    elapsed: float | None = None


class AAPJobTemplateOutput(NodeOutput):
    """Output model for AAP job template executor nodes."""

    job_id: int | None = None
    job_url: str | None = None
    job_status: str | None = None
    artifacts: dict[str, Any] | None = None
    created: str | None = None
    started: str | None = None
    finished: str | None = None


class AAPWorkflowJobTemplateOutput(NodeOutput):
    """Output model for AAP workflow job template executor nodes."""

    workflow_job_id: int | None = None
    workflow_job_url: str | None = None
    workflow_job_status: str | None = None
    artifacts: dict[str, Any] | None = None
    created: str | None = None
    started: str | None = None
    finished: str | None = None


class AgenticOutput(NodeOutput):
    """Output model for agentic executor nodes."""

    output: str | dict[str, Any] | None = None
    tool_calls: list[Any] | None = None
    used_tools: list[dict[str, Any]] | None = None
    structured_output_metadata: dict[str, Any] | None = None
    integration_ids: list[str] | None = None


class ApprovalOutput(NodeOutput):
    """Output model for approval executor nodes."""

    status: ActivityTerminalStatus | None = None
    decision: str | None = None
    decided_by: str | None = None
    decided_at: str | None = None
    decision_notes: str | None = None


class ConditionOutput(NodeOutput):
    """Output model for condition control nodes."""

    evaluated_result: bool | None = None


class SwitchOutput(NodeOutput):
    """Output model for switch control nodes."""

    matched_port: str | None = None


class ConvergeOutput(NodeOutput):
    """Output model for converge control nodes."""

    branch_count: int | None = None
    completed_count: int | None = None
    completed_branch_node_ids: list[str] | None = None


class LoopOutput(NodeOutput):
    """Output model for loop control nodes."""

    iteration_count: int | None = None
    iteration_results: dict[str, list[Any]] | None = None


class WaitOutput(NodeOutput):
    """Output model for wait control nodes."""


NODE_OUTPUT_MODELS: dict[str, type[NodeOutput]] = {
    NodeType.SCRIPT: ScriptOutput,
    NodeType.HTTP_REQUEST: HttpRequestOutput,
    NodeType.AAP_JOB_TEMPLATE: AAPJobTemplateOutput,
    NodeType.AAP_WORKFLOW_JOB_TEMPLATE: AAPWorkflowJobTemplateOutput,
    NodeType.AGENTIC: AgenticOutput,
    NodeType.APPROVAL: ApprovalOutput,
    NodeType.CONDITION: ConditionOutput,
    NodeType.SWITCH: SwitchOutput,
    NodeType.CONVERGE: ConvergeOutput,
    NodeType.LOOP: LoopOutput,
    NodeType.WAIT: WaitOutput,
}


class ScheduleType(StrEnum):
    """Schedule type for scheduled trigger nodes."""

    INTERVAL = "interval"
    CRON = "cron"


class MissedSchedulePolicy(StrEnum):
    """Policy for handling overlapping and missed schedule executions.

    Determines what happens when a schedule fires while a previous execution
    from the same schedule is still running.
    """

    SKIP = "skip"
    BUFFER_ONE = "buffer_one"
    BUFFER_ALL = "buffer_all"
    ALLOW_ALL = "allow_all"
    CANCEL_OTHER = "cancel_other"


# Standard 5-field cron: minute hour day-of-month month day-of-week
# Each field allows digits, ranges (1-5), lists (1,3,5), steps (*/5), and wildcards (*)
_CRON_FIELD = r"(\*|[0-9]+(?:-[0-9]+)?(?:,[0-9]+(?:-[0-9]+)?)*)(?:/[0-9]+)?"
_CRON_PATTERN = re.compile(rf"^\s*{_CRON_FIELD}\s+{_CRON_FIELD}\s+{_CRON_FIELD}\s+{_CRON_FIELD}\s+{_CRON_FIELD}\s*$")

_CRON_RANGES: list[tuple[str, int, int]] = [
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day-of-month", 1, 31),
    ("month", 1, 12),
    ("day-of-week", 0, 7),
]

_CRON_NUMERIC = re.compile(r"[0-9]+")


def _validate_cron_ranges(expr: str) -> None:
    """Validate that numeric values in each cron field are within allowed ranges."""
    fields = expr.split()
    for field, (name, lo, hi) in zip(fields, _CRON_RANGES, strict=False):
        for m in _CRON_NUMERIC.finditer(field):
            val = int(m.group())
            if val < lo or val > hi:
                msg = f"Invalid cron expression: {name} must be {lo}-{hi}, got {val}"
                raise SafeValueError(msg)


# Lazy-initialised cache of valid IANA timezone names (frozenset for O(1) lookups).
_VALID_TIMEZONES: frozenset[str] | None = None


def _get_valid_timezones() -> frozenset[str]:
    """Return the set of valid IANA timezone names, cached after first call."""
    global _VALID_TIMEZONES  # noqa: PLW0603
    if _VALID_TIMEZONES is None:
        tzs = frozenset(available_timezones())
        if not tzs:
            msg = "No IANA timezone data found. Install the 'tzdata' package: pip install tzdata"
            raise RuntimeError(msg)
        _VALID_TIMEZONES = tzs
    return _VALID_TIMEZONES


class ScheduledTriggerConfig(TemplateAwareBaseModel):
    """Parameters for scheduled trigger nodes.

    Defines the schedule configuration for a scheduled trigger, including
    the schedule type, cron expression or interval, and timezone.

    Attributes:
        schedule_type: Type of schedule (interval or cron).
        interval: ISO 8601 repeating interval string (required when
            schedule_type is "interval"). Format: ``R/<start>/<duration>``
            or ``R/<start>/<duration>/<end>``.
        cron: Standard 5-field cron expression (required when
            schedule_type is "cron"). Example: ``0 9 * * *`` for daily at 9am.
        timezone: IANA timezone name (e.g., "America/New_York").
            Defaults to UTC if not specified.
        missed_schedule_policy: How to handle missed schedule invocations.
            Defaults to "skip".

    """

    schedule_type: ScheduleType = Field(
        description="Type of schedule: interval or cron",
    )
    interval: str | None = Field(
        default=None,
        description=(
            "ISO 8601 repeating interval (e.g., 'R/2024-01-01T10:00:00Z/P1D'). "
            "Required when schedule_type is 'interval'."
        ),
    )
    cron: str | None = Field(
        default=None,
        description=("Standard 5-field cron expression (e.g., '0 9 * * *'). Required when schedule_type is 'cron'."),
    )
    timezone: str | None = Field(
        default=None,
        description="IANA timezone name (e.g., 'America/New_York'). Defaults to UTC.",
    )
    missed_schedule_policy: MissedSchedulePolicy = Field(
        default=MissedSchedulePolicy.SKIP,
        description="How to handle overlapping schedule executions",
    )

    _SCHEDULE_SHAPE_FIELDS: ClassVar[tuple[str, ...]] = ("schedule_type", "interval", "cron", "timezone")

    @model_validator(mode="before")
    @classmethod
    def reject_template_schedule_fields(cls, data: Any) -> Any:  # noqa: ANN401
        """Reject template expressions in schedule-shape fields.

        Unlike other node parameters, ``schedule_type``/``interval``/``cron``/
        ``timezone`` are materialized into a Temporal Schedule once at publish
        time -- there is no per-execution runtime context to resolve
        ``${...}`` expressions against later. Letting
        ``TemplateAwareBaseModel``'s wildcard bypass wave these through would
        let ``collect_findings`` / pre-mutation publish accept a config that
        can never be turned into a schedule, then fail post-commit in
        ``config_to_temporal_schedule``. Runs before field-level validation
        (and before the wildcard bypass) so it can't be skipped.
        """
        if not isinstance(data, dict):
            return data
        for field_name in cls._SCHEDULE_SHAPE_FIELDS:
            value = data.get(field_name)
            if isinstance(value, str) and TEMPLATE_PATTERN.search(value):
                msg = (
                    f"Field '{field_name}' does not support template expressions. "
                    "Scheduled trigger configs are fixed at publish time, not resolved at runtime."
                )
                raise SafeValueError(msg)
        return data

    @field_validator("interval")
    @classmethod
    def validate_interval_expression(cls, v: str | None, info: ValidationInfo) -> str | None:
        """Validate that interval is a well-formed ISO 8601 repeating interval.

        Skipped when ``schedule_type`` is not ``interval``: ``interval`` is
        inactive in that case and ``config_to_temporal_schedule`` never reads
        it, so a stale/invalid leftover value here must not block verify or
        publish. Otherwise delegates to
        ``iso8601_interval.parse_iso8601_repeating_interval``, the same
        parser ``schedule_parser.parse_iso8601_interval`` uses to build
        Temporal Schedule objects, so this model, ``/workflows/validate``,
        publish, and Temporal sync all reject the same set of interval
        strings.
        """
        if v is None:
            return v
        if info.data.get("schedule_type") not in (None, ScheduleType.INTERVAL):
            return v
        parse_iso8601_repeating_interval(v)
        return v

    @field_validator("cron")
    @classmethod
    def validate_cron_expression(cls, v: str | None, info: ValidationInfo) -> str | None:
        """Validate that cron is a standard 5-field expression.

        Skipped when ``schedule_type`` is not ``cron``, mirroring
        ``validate_interval_expression`` -- ``config_to_temporal_schedule``
        never reads ``cron`` for an interval schedule.
        """
        if v is None:
            return v
        if info.data.get("schedule_type") not in (None, ScheduleType.CRON):
            return v
        if not _CRON_PATTERN.match(v):
            msg = (
                f"Invalid cron expression: '{v}'. "
                "Must be a standard 5-field format: minute hour day-of-month month day-of-week"
            )
            raise SafeValueError(msg)
        _validate_cron_ranges(v)
        return v

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str | None) -> str | None:
        """Validate that timezone is a valid IANA timezone name."""
        if v is None:
            return v
        if v not in _get_valid_timezones():
            msg = f"Invalid timezone: '{v}'. Must be a valid IANA timezone name (e.g., 'America/New_York')."
            raise SafeValueError(msg)
        return v

    @model_validator(mode="after")
    def validate_schedule_fields(self) -> "ScheduledTriggerConfig":
        """Validate that required fields are present based on schedule_type."""
        if self.schedule_type == ScheduleType.INTERVAL and not self.interval:
            msg = "Field 'interval' is required when schedule_type is 'interval'"
            raise SafeValueError(msg)

        if self.schedule_type == ScheduleType.CRON and not self.cron:
            msg = "Field 'cron' is required when schedule_type is 'cron'"
            raise SafeValueError(msg)

        return self
