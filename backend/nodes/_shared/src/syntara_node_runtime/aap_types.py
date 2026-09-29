"""AAP-related type definitions and enums."""

from enum import StrEnum


class AAPResourceType(StrEnum):
    """AAP resource types with display names for error messages.

    Uses the MultiValueEnum pattern to associate each resource type with
    its API endpoint path, field name prefix, and user-friendly display name.
    """

    JOB_TEMPLATES = "job_templates"
    WORKFLOW_JOB_TEMPLATES = "workflow_job_templates"
    INVENTORIES = "inventories"
    INSTANCE_GROUPS = "instance_groups"

    @property
    def display_name(self) -> str:
        """Get singularized display name for error messages.

        Returns:
            Human-readable singular form (e.g., "job template", "inventory")

        """
        if self == AAPResourceType.JOB_TEMPLATES:
            return "job template"
        if self == AAPResourceType.WORKFLOW_JOB_TEMPLATES:
            return "workflow job template"
        if self == AAPResourceType.INSTANCE_GROUPS:
            return "instance group"
        # INVENTORIES
        return "inventory"

    @property
    def display_name_plural(self) -> str:
        """Get pluralized display name for error messages.

        Returns:
            Human-readable plural form (e.g., "job templates", "inventories")

        """
        return self.value.replace("_", " ")

    @property
    def field_prefix(self) -> str:
        """Get field name prefix for validation.

        Returns:
            Singular field prefix (e.g., "job_template", "inventory")

        """
        if self == AAPResourceType.JOB_TEMPLATES:
            return "job_template"
        if self == AAPResourceType.WORKFLOW_JOB_TEMPLATES:
            return "workflow_job_template"
        if self == AAPResourceType.INSTANCE_GROUPS:
            return "instance_group"
        # INVENTORIES
        return "inventory"
