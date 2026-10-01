"""Compatibility models extracted from workflow_definition at the migration baseline.

Schema parity tests guard these portable copies while legacy activities coexist.
"""

from __future__ import annotations

import json
import re
import uuid
from enum import Enum, IntEnum, StrEnum
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlparse

import structlog
from pydantic import Field, ValidationInfo, field_validator, model_validator
from sqlmodel import SQLModel as BaseModel

from .aap_types import AAPResourceType
from .json_schema_validation import validate_json_schema_definition

if TYPE_CHECKING:
    from pydantic.functional_validators import ModelWrapValidatorHandler

SafeValueError = ValueError
logger = structlog.get_logger(__name__)
TEMPLATE_PATTERN = re.compile(r"\$\{[^}]+\}")
_CONFIG_VALIDATION_FAILED = "Config validation failed"


class AAPJobType(StrEnum):
    """Ansible Automation Platform job type values."""

    RUN = "run"
    CHECK = "check"


class NodeOutput(BaseModel):
    """Raw node output before control-plane mapping."""

    def dump(self, _output_config: dict[str, str] | None = None) -> dict[str, Any]:
        """Return raw fields; the caller owns workflow output mapping."""
        return self.model_dump()


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

    Template expressions like ${trigger.field} or ${step_1.count} bypass
    type validation and constraints, allowing them to be stored as strings and
    evaluated at runtime during workflow execution.

    Non-template values are validated normally with full type checking and
    Field constraints (ge, le, min_length, etc.).
    """

    model_config = {"validate_assignment": True}

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


class ScriptExecutorParameters(TemplateAwareBaseModel):
    """Parameters for script executor."""

    language: ScriptLanguage
    code: str = Field(min_length=1, description="Script code to execute")
    environment: dict[str, str] = Field(default_factory=dict, description="Environment variables")

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
        description="Orchestrator credential UUID for authentication or Secret URL.",
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
        description="Orchestrator credential UUID for execution calls (distinct from management credential)"
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
        description="Orchestrator credential UUID for LLM provider authentication",
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
    def _validate_tool_selection_coherence(self) -> AgenticExecutorParameters:
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
            "Orchestrator credential UUID for Ansible Automation Platform API authentication. "
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
    def validate_references(self) -> AAPJobTemplateExecutorParameters:
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
    def validate_references(self) -> AAPWorkflowJobTemplateExecutorParameters:
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
