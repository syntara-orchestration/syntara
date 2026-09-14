from enum import Enum


class ValidationCategory(str, Enum):
    APPROVAL_CONFIGURATION = "approval_configuration"
    CONVERGE_CONFIGURATION = "converge_configuration"
    CYCLE_DETECTED = "cycle_detected"
    FORM_PROMPT_CONFIGURATION = "form_prompt_configuration"
    INVALID_REFERENCE = "invalid_reference"
    MISSING_FIELD = "missing_field"
    ORPHANED_NODE = "orphaned_node"
    SCHEMA_VERSION = "schema_version"
    SCHEMA_VIOLATION = "schema_violation"

    def __str__(self) -> str:
        return str(self.value)
