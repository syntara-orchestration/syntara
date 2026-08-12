r"""Response models for AAP proxy endpoints.

Backend Compatibility Notes
---------------------------
The AAPJobTemplateDetail model extracts default values from AAP's job template
response. Default values come from two sources:

1. Related resources (from summary_fields):
   - inventory, execution_environment, credentials, labels
   These are extracted by the Pydantic validator and flattened to default_* fields.

2. Scalar defaults (direct fields from AAP):
   - job_type, verbosity, forks, limit, job_tags, skip_tags, diff_mode,
     job_slice_count, timeout, extra_vars
   These are passed through directly from AAP's response.

AAP Controller API returns job template details with a nested summary_fields
structure:
    {
      "id": 123,
      "name": "Deploy App",
      "description": "Deploy application to production",
      "url": "https://controller.example.com/#/templates/job_template/123",
      "ask_job_type_on_launch": false,
      "ask_inventory_on_launch": true,
      "ask_credential_on_launch": false,
      "ask_variables_on_launch": true,
      "ask_limit_on_launch": true,
      "ask_tags_on_launch": true,
      "ask_skip_tags_on_launch": true,
      "ask_verbosity_on_launch": true,
      "ask_diff_mode_on_launch": true,
      "ask_forks_on_launch": true,
      "ask_job_slice_count_on_launch": true,
      "ask_execution_environment_on_launch": false,
      "ask_instance_groups_on_launch": false,
      "ask_labels_on_launch": true,
      "ask_timeout_on_launch": true,
      "ask_scm_branch_on_launch": false,
      "survey_enabled": false,
      "job_type": "run",
      "verbosity": 0,
      "forks": 5,
      "diff_mode": false,
      "limit": "webservers",
      "job_tags": "deploy,config",
      "skip_tags": "slow",
      "job_slice_count": 4,
      "timeout": 3600,
      "extra_vars": "---\nkey: value",
      "summary_fields": {
        "inventory": {"id": 1, "name": "Default Inventory"},
        "execution_environment": {"id": 2, "name": "Default EE"},
        "credentials": [
          {"id": 3, "name": "SSH Credential"},
          {"id": 4, "name": "AWS Credential"}
        ],
        "labels": {
          "count": 2,
          "results": [
            {"id": 1, "name": "production"},
            {"id": 2, "name": "us-east"}
          ]
        }
      }
    }

Our Pydantic validator flattens summary_fields into top-level default_* fields:
    {
      "id": 123,
      "name": "Deploy App",
      "description": "Deploy application to production",
      "url": "https://controller.example.com/#/templates/job_template/123",
      "ask_job_type_on_launch": false,
      "ask_inventory_on_launch": true,
      "ask_credential_on_launch": false,
      "ask_variables_on_launch": true,
      "ask_limit_on_launch": true,
      "ask_tags_on_launch": true,
      "ask_skip_tags_on_launch": true,
      "ask_verbosity_on_launch": true,
      "ask_diff_mode_on_launch": true,
      "ask_forks_on_launch": true,
      "ask_job_slice_count_on_launch": true,
      "ask_execution_environment_on_launch": false,
      "ask_instance_groups_on_launch": false,
      "ask_labels_on_launch": true,
      "ask_timeout_on_launch": true,
      "ask_scm_branch_on_launch": false,
      "survey_enabled": false,
      "job_type": "run",
      "verbosity": 0,
      "forks": 5,
      "diff_mode": false,
      "limit": "webservers",
      "job_tags": "deploy,config",
      "skip_tags": "slow",
      "job_slice_count": 4,
      "timeout": 3600,
      "extra_vars": "---\nkey: value",
      "default_inventory": {"id": 1, "name": "Default Inventory"},
      "default_execution_environment": {"id": 2, "name": "Default EE"},
      "default_credentials": [
        {"id": 3, "name": "SSH Credential"},
        {"id": 4, "name": "AWS Credential"}
      ],
      "default_labels": [
        {"id": 1, "name": "production"},
        {"id": 2, "name": "us-east"}
      ]
    }

This approach:
- Keeps the frontend contract clean and predictable
- Handles AAP API changes in one place (the validator)
- Validates that summary_fields contain properly structured data
- Gracefully handles missing or malformed summary_fields
- Exposes all default values (both scalar and related resources) to the frontend
"""

from enum import StrEnum
from typing import Any

import structlog
from pydantic import BaseModel, Field, ValidationError, model_validator

logger = structlog.get_logger(__name__)


class AAPOrganization(BaseModel):
    """Ansible Automation Platform organization resource."""

    id: int
    name: str


class AAPJobTemplate(BaseModel):
    """Ansible Automation Platform job template resource."""

    id: int
    name: str
    description: str | None = None


class AAPWorkflowJobTemplate(BaseModel):
    """Ansible Automation Platform workflow job template resource."""

    id: int
    name: str
    description: str | None = None


class AAPSummaryField(BaseModel):
    """Summary field with id and name from Ansible Automation Platform summary_fields."""

    id: int
    name: str


class AAPJobType(StrEnum):
    """Ansible Automation Platform job type values."""

    RUN = "run"
    CHECK = "check"


# AAP API field name for nested default values
AAP_SUMMARY_FIELDS_KEY = "summary_fields"


def _validate_summary_field(field: Any) -> AAPSummaryField | None:  # noqa: ANN401 - accepts arbitrary AAP API data
    """Validate and parse a summary field using Pydantic validation.

    Returns the validated AAPSummaryField or None if validation fails.
    Logs warning for invalid fields to aid debugging.
    """
    try:
        return AAPSummaryField.model_validate(field)
    except ValidationError as e:
        # Log validation failures for debugging (not critical, AAP may send unexpected formats)
        logger.warning("Invalid summary field from AAP", field=field, validation_error=str(e))
        return None


def _extract_summary_field_list(items: Any) -> list[AAPSummaryField]:  # noqa: ANN401 - accepts arbitrary AAP API data
    """Extract and validate a list of summary fields.

    Args:
        items: Either a list of dicts or any other value

    Returns:
        List of validated AAPSummaryField objects

    """
    if not isinstance(items, list):
        return []

    validated_items = []
    for item in items:
        validated = _validate_summary_field(item)
        if validated is not None:
            validated_items.append(validated)
    return validated_items


def _extract_credentials_strict(items: Any) -> list[AAPSummaryField]:  # noqa: ANN401 - accepts arbitrary AAP API data
    """Extract credentials with strict validation - fail on any invalid item.

    Unlike _extract_summary_field_list which silently filters invalid items,
    this raises an exception if ANY credential is malformed.

    Args:
        items: Expected to be a list of credential dicts from AAP API

    Returns:
        List of validated AAPSummaryField objects

    Raises:
        TypeError: If items is not a list
        ValueError: If any credential is invalid (missing id/name)

    """
    if not isinstance(items, list):
        msg = "Credentials must be a list"
        raise TypeError(msg)

    validated_items = []
    invalid_items = []

    for idx, item in enumerate(items):
        validated = _validate_summary_field(item)
        if validated is None:
            invalid_items.append({"index": idx, "data": item})
        else:
            validated_items.append(validated)

    if invalid_items:
        msg = f"Found {len(invalid_items)} invalid credentials in AAP summary_fields"
        logger.error("Invalid credentials from AAP", invalid_count=len(invalid_items), invalid_items=invalid_items)
        raise ValueError(msg)

    return validated_items


def _extract_labels(summary: dict[str, Any]) -> list[AAPSummaryField]:
    """Extract labels from summary_fields.labels.results as list of AAPSummaryField.

    Note: AAP API returns labels in a nested paginated structure:
    {"labels": {"count": 2, "results": [{"id": 1, "name": "prod"}]}}
    Unlike credentials which are a direct array. We extract from labels.results.
    """
    labels_obj = summary.get("labels")
    if not isinstance(labels_obj, dict):
        return []
    return _extract_summary_field_list(labels_obj.get("results"))


def _extract_and_set_field(
    data: dict[str, Any],
    summary: dict[str, Any],
    summary_key: str,
    data_key: str,
) -> None:
    """Extract a summary field and set it in data if not already present.

    Args:
        data: The job template data dict to update
        summary: The summary_fields dict from AAP
        summary_key: Key to look up in summary_fields (e.g., "inventory")
        data_key: Key to set in data (e.g., "default_inventory")

    """
    if data_key not in data:
        field = summary.get(summary_key)
        validated = _validate_summary_field(field)
        if validated is not None:
            data[data_key] = validated


class AAPJobTemplateDetail(BaseModel):
    """Ansible Automation Platform job template with prompt-on-launch capabilities and default values."""

    id: int
    name: str
    description: str | None = None
    url: str | None = Field(None, description="Link to the job template in Ansible Automation Platform Controller UI")
    # Prompt-on-launch flags
    ask_job_type_on_launch: bool = False
    ask_inventory_on_launch: bool = False
    ask_credential_on_launch: bool = False
    ask_variables_on_launch: bool = False
    ask_limit_on_launch: bool = False
    ask_tags_on_launch: bool = False
    ask_skip_tags_on_launch: bool = False
    ask_verbosity_on_launch: bool = False
    ask_diff_mode_on_launch: bool = False
    ask_forks_on_launch: bool = False
    ask_job_slice_count_on_launch: bool = False
    ask_execution_environment_on_launch: bool = False
    ask_instance_groups_on_launch: bool = False
    ask_labels_on_launch: bool = False
    ask_timeout_on_launch: bool = False
    ask_scm_branch_on_launch: bool = False
    survey_enabled: bool = False
    # Default values extracted from summary_fields (for related resources)
    default_inventory: AAPSummaryField | None = Field(
        default=None, title="Default Inventory", description="Default inventory from job template summary_fields"
    )
    default_execution_environment: AAPSummaryField | None = Field(
        default=None,
        title="Default Execution Environment",
        description="Default execution environment from job template summary_fields",
    )
    default_credentials: list[AAPSummaryField] = Field(
        default_factory=list,
        title="Default Credentials",
        description="Default credentials from job template summary_fields",
    )
    default_labels: list[AAPSummaryField] = Field(
        default_factory=list,
        title="Default Labels",
        description="Default labels from job template summary_fields",
    )
    # Default values from job template direct fields
    # Note: These fields use AAP's actual field names, not our normalized names
    job_type: AAPJobType | None = Field(default=None, description='Default job type - "run" or "check"')
    verbosity: int | None = Field(default=None, ge=0, le=5, description="Default verbosity level (0-5)")
    forks: int | None = Field(default=None, ge=0, le=10000, description="Default number of forks (max 10,000)")
    limit: str | None = Field(default=None, max_length=2048, description="Default limit pattern")
    job_tags: str | None = Field(default=None, max_length=2048, description="Default job tags")
    skip_tags: str | None = Field(default=None, max_length=2048, description="Default skip tags")
    diff_mode: bool | None = Field(default=None, description="Default diff mode setting")
    job_slice_count: int | None = Field(
        default=None, ge=0, le=10000, description="Default job slice count (max 10,000)"
    )
    timeout: int | None = Field(default=None, ge=0, le=604800, description="Default timeout in seconds (max 7 days)")
    extra_vars: str | None = Field(
        default=None, max_length=1048576, description="Default extra variables (YAML format, max 1MB)"
    )

    @model_validator(mode="before")
    @classmethod
    def extract_summary_fields(cls, data: Any) -> Any:  # noqa: ANN401 - Pydantic validator accepts arbitrary input
        """Extract default values from AAP's summary_fields into top-level fields.

        AAP returns:
        {
          "id": 123,
          "summary_fields": {
            "inventory": {"id": 1, "name": "Default Inventory"},
            "execution_environment": {"id": 2, "name": "Default EE"},
            "credentials": [{"id": 3, "name": "Cred1"}],
            "labels": {"count": 2, "results": [{"id": 1, "name": "label1"}, {"id": 2, "name": "label2"}]}
          }
        }

        We extract these to default_inventory, default_execution_environment, default_credentials,
        and default_labels (as list of AAPSummaryField).
        """
        if not isinstance(data, dict):
            return data

        summary = data.get(AAP_SUMMARY_FIELDS_KEY, {})
        if not isinstance(summary, dict):
            return data

        # Extract single-value summary fields
        _extract_and_set_field(data, summary, "inventory", "default_inventory")
        _extract_and_set_field(data, summary, "execution_environment", "default_execution_environment")

        # Extract credentials list with STRICT validation (security-critical)
        if "default_credentials" not in data:
            try:
                valid_creds = _extract_credentials_strict(summary.get("credentials"))
                if valid_creds:
                    data["default_credentials"] = valid_creds
            except (TypeError, ValueError) as e:
                logger.warning("Skipping invalid credentials", error=str(e))
                # Keep default_credentials as empty list rather than failing entire response
                data["default_credentials"] = []

        # Extract labels from nested labels.results structure
        if "default_labels" not in data:
            labels = _extract_labels(summary)
            if labels:
                data["default_labels"] = labels

        return data


class AAPWorkflowJobTemplateDetail(BaseModel):
    """Ansible Automation Platform workflow job template with prompt-on-launch capabilities and default values."""

    id: int
    name: str
    description: str | None = None
    url: str | None = Field(
        None, description="Link to the workflow template in Ansible Automation Platform Controller UI"
    )
    # Prompt-on-launch flags
    ask_inventory_on_launch: bool = False
    ask_credential_on_launch: bool = False
    ask_variables_on_launch: bool = False
    ask_limit_on_launch: bool = False
    ask_scm_branch_on_launch: bool = False
    ask_labels_on_launch: bool = False
    ask_tags_on_launch: bool = False
    ask_skip_tags_on_launch: bool = False
    survey_enabled: bool = False
    # Default values extracted from summary_fields (for related resources)
    default_inventory: AAPSummaryField | None = Field(
        default=None,
        title="Default Inventory",
        description="Default inventory from workflow template summary_fields",
    )
    default_labels: list[AAPSummaryField] = Field(
        default_factory=list,
        title="Default Labels",
        description="Default labels from workflow template summary_fields",
    )
    # Default values from workflow template direct fields
    limit: str | None = Field(default=None, max_length=2048, description="Default limit pattern")
    scm_branch: str | None = Field(default=None, max_length=256, description="Default SCM branch")
    job_tags: str | None = Field(default=None, max_length=2048, description="Default job tags")
    skip_tags: str | None = Field(default=None, max_length=2048, description="Default skip tags")
    extra_vars: str | None = Field(
        default=None, max_length=1048576, description="Default extra variables (YAML format, max 1MB)"
    )

    @model_validator(mode="before")
    @classmethod
    def extract_summary_fields(cls, data: Any) -> Any:  # noqa: ANN401 - Pydantic validator accepts arbitrary input
        """Extract default values from AAP's summary_fields into top-level fields.

        AAP returns:
        {
          "id": 123,
          "summary_fields": {
            "inventory": {"id": 1, "name": "Default Inventory"},
            "labels": {"count": 2, "results": [{"id": 1, "name": "label1"}, {"id": 2, "name": "label2"}]}
          }
        }

        We extract these to default_inventory and default_labels (as list of AAPSummaryField).
        """
        if not isinstance(data, dict):
            return data

        summary = data.get(AAP_SUMMARY_FIELDS_KEY, {})
        if not isinstance(summary, dict):
            return data

        # Extract single-value summary fields
        _extract_and_set_field(data, summary, "inventory", "default_inventory")

        # Extract labels from nested labels.results structure
        if "default_labels" not in data:
            labels = _extract_labels(summary)
            if labels:
                data["default_labels"] = labels

        return data


class AAPInventory(BaseModel):
    """Ansible Automation Platform inventory resource."""

    id: int
    name: str
    description: str | None = None


class AAPExecutionEnvironment(BaseModel):
    """Ansible Automation Platform execution environment resource."""

    id: int
    name: str
    description: str | None = None


class AAPCredential(BaseModel):
    """Ansible Automation Platform credential resource.

    Only ``id`` and ``name`` are exposed — descriptions are omitted to avoid
    leaking infrastructure details (e.g. "prod-aws-root-key") to all users.
    """

    id: int
    name: str


class AAPInstanceGroup(BaseModel):
    """Ansible Automation Platform instance group resource."""

    id: int
    name: str


class AAPLabel(BaseModel):
    """Ansible Automation Platform label resource."""

    id: int
    name: str
    organization: int | None = None


class AAPListResponse[T](BaseModel):
    """Paginated list response from Ansible Automation Platform Controller."""

    count: int
    results: list[T]
