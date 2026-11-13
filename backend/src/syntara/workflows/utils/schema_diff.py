"""Utilities for detecting breaking changes in SubWorkflow output schemas."""

from typing import Any


class OutputSchemaChange:
    """Represents a breaking change in a SubWorkflow output schema."""

    def __init__(
        self,
        change_type: str,
        field_path: str,
        old_type: str | None = None,
        new_type: str | None = None,
        description: str | None = None,
    ) -> None:
        """Initialize an output schema change.

        Args:
            change_type: Type of change (removed_output, type_change, new_required_output)
            field_path: Dotted path to the field (e.g., "artifact_url", "result.status")
            old_type: Previous field type (for type changes)
            new_type: New field type (for type changes)
            description: Human-readable description of the change

        """
        self.change_type = change_type
        self.field_path = field_path
        self.old_type = old_type
        self.new_type = new_type
        self.description = description or self._build_description()

    def _build_description(self) -> str:
        """Build a human-readable description of the change."""
        if self.change_type == "removed_output":
            return f"Removed output: {self.field_path}"
        if self.change_type == "type_change":
            return f"Type changed: {self.field_path} ({self.old_type} → {self.new_type})"
        if self.change_type == "new_required_output":
            return f"New required output: {self.field_path}"
        return f"Changed: {self.field_path}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "change_type": self.change_type,
            "field_path": self.field_path,
            "old_type": self.old_type,
            "new_type": self.new_type,
            "description": self.description,
        }


def _extract_properties_flat(schema: dict[str, Any], prefix: str = "") -> dict[str, tuple[str, bool]]:
    """Extract all properties from a JSON Schema into a flat dictionary.

    Args:
        schema: JSON Schema object
        prefix: Current path prefix for nested properties

    Returns:
        Dictionary mapping field paths to (type, is_required) tuples

    """
    result: dict[str, tuple[str, bool]] = {}

    if not isinstance(schema, dict):
        return result  # type: ignore[unreachable]

    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return result

    required_fields = set(schema.get("required", []))

    for field_name, field_schema in properties.items():
        if not isinstance(field_schema, dict):
            continue

        field_path = f"{prefix}.{field_name}" if prefix else field_name
        field_type = field_schema.get("type", "unknown")
        is_required = field_name in required_fields

        result[field_path] = (field_type, is_required)

        # Recursively process nested objects
        if field_type == "object" and "properties" in field_schema:
            nested = _extract_properties_flat(field_schema, prefix=field_path)
            result.update(nested)

    return result


def detect_output_schema_breaking_changes(  # noqa: C901
    old_schema: dict[str, Any] | None,
    new_schema: dict[str, Any] | None,
) -> list[OutputSchemaChange]:
    """Detect breaking changes between two output schemas.

    Breaking changes include:
    - Removed outputs (fields present in old but not in new)
    - Type changes (same field, different type)
    - New required outputs (fields that are required in new but didn't exist in old)

    Args:
        old_schema: Previous output_schema (from published version)
        new_schema: New output_schema (from version being published)

    Returns:
        List of detected breaking changes

    """
    changes: list[OutputSchemaChange] = []

    # If old schema is None, this is the first publish - no breaking changes
    if old_schema is None:
        return changes

    # If new schema is None but old existed, all outputs were removed
    if new_schema is None:
        old_fields = _extract_properties_flat(old_schema)
        for field_path, (field_type, _) in old_fields.items():
            changes.append(
                OutputSchemaChange(
                    change_type="removed_output",
                    field_path=field_path,
                    old_type=field_type,
                )
            )
        return changes

    old_fields = _extract_properties_flat(old_schema)
    new_fields = _extract_properties_flat(new_schema)

    # Check for removed outputs
    for field_path in old_fields:
        if field_path not in new_fields:
            old_type, _ = old_fields[field_path]
            changes.append(
                OutputSchemaChange(
                    change_type="removed_output",
                    field_path=field_path,
                    old_type=old_type,
                )
            )

    # Check for type changes
    for field_path in old_fields:
        if field_path in new_fields:
            old_type, _ = old_fields[field_path]
            new_type, _ = new_fields[field_path]
            if old_type != new_type:
                changes.append(
                    OutputSchemaChange(
                        change_type="type_change",
                        field_path=field_path,
                        old_type=old_type,
                        new_type=new_type,
                    )
                )

    # Check for new required outputs
    for field_path in new_fields:
        if field_path not in old_fields:
            _, is_required = new_fields[field_path]
            if is_required:
                new_type, _ = new_fields[field_path]
                changes.append(
                    OutputSchemaChange(
                        change_type="new_required_output",
                        field_path=field_path,
                        new_type=new_type,
                    )
                )

    return changes


def detect_workflow_breaking_changes(
    old_definition: dict[str, Any] | None,
    new_definition: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Detect all breaking changes in a workflow definition.

    Compares SubWorkflow Trigger output schemas between old and new definitions.

    Args:
        old_definition: Previous workflow definition (from published version)
        new_definition: New workflow definition (version being published)

    Returns:
        Dictionary mapping trigger IDs to lists of breaking changes

    """
    result: dict[str, list[dict[str, Any]]] = {}

    if old_definition is None:
        return result

    # Extract triggers from both definitions
    old_triggers = {
        t.get("id"): t
        for t in old_definition.get("triggers", [])
        if isinstance(t, dict) and t.get("type") == "subworkflow_trigger" and t.get("id") is not None
    }

    new_triggers = {
        t.get("id"): t
        for t in new_definition.get("triggers", [])
        if isinstance(t, dict) and t.get("type") == "subworkflow_trigger" and t.get("id") is not None
    }

    # Check each new trigger against its old version
    for trigger_id, new_trigger in new_triggers.items():

        old_trigger = old_triggers.get(trigger_id)
        if old_trigger is None:
            # New trigger - no breaking changes
            continue

        old_params = old_trigger.get("parameters", {})
        new_params = new_trigger.get("parameters", {})

        old_output_schema = old_params.get("output_schema") if isinstance(old_params, dict) else None
        new_output_schema = new_params.get("output_schema") if isinstance(new_params, dict) else None

        changes = detect_output_schema_breaking_changes(old_output_schema, new_output_schema)

        if changes:
            result[trigger_id] = [change.to_dict() for change in changes]

    return result
