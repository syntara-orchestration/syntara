"""Utilities for detecting breaking changes in SubWorkflow output schemas."""

from typing import Any


class OutputSchemaChange:
    """Represents a change in a SubWorkflow output schema."""

    def __init__(
        self,
        change_type: str,
        field_path: str,
        old_type: str | None = None,
        new_type: str | None = None,
        description: str | None = None,
        *,
        is_breaking: bool = True,
    ) -> None:
        """Initialize an output schema change.

        Args:
            change_type: Type of change (removed_output, type_change, new_required_output)
            field_path: Dotted path to the field (e.g., "artifact_url", "result.status")
            old_type: Previous field type (for type changes)
            new_type: New field type (for type changes)
            description: Human-readable description of the change
            is_breaking: Whether the change can break a parent contract

        """
        self.change_type = change_type
        self.field_path = field_path
        self.old_type = old_type
        self.new_type = new_type
        self.description = description or self._build_description()
        self.is_breaking = is_breaking

    def _build_description(self) -> str:
        """Build a human-readable description of the change."""
        if self.change_type == "removed_output":
            return f"Removed output: {self.field_path}"
        if self.change_type == "type_change":
            return f"Type changed: {self.field_path} ({self.old_type} → {self.new_type})"
        if self.change_type == "new_required_output":
            return f"New required output: {self.field_path}"
        if self.change_type == "added_output":
            return f"Added optional output: {self.field_path}"
        if self.change_type == "optional_output":
            return f"Output is now optional: {self.field_path}"
        return f"Changed: {self.field_path}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "change_type": self.change_type,
            "field_path": self.field_path,
            "old_type": self.old_type,
            "new_type": self.new_type,
            "description": self.description,
            "is_breaking": self.is_breaking,
        }


def _schema_type_label(schema: dict[str, Any]) -> str:
    raw_type = schema.get("type", "unknown")
    if isinstance(raw_type, str):
        return raw_type
    if isinstance(raw_type, list):
        return " | ".join(str(value) for value in raw_type)
    return "unknown"


def _extract_properties_flat(
    schema: dict[str, Any], prefix: str = "", *, required_ancestors: bool = True
) -> dict[str, tuple[str, bool]]:
    """Extract all properties from a JSON Schema into a flat dictionary.

    Args:
        schema: JSON Schema object
        prefix: Current dotted path prefix
        required_ancestors: Whether every ancestor object is itself required

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
        field_type = _schema_type_label(field_schema)
        is_required = required_ancestors and field_name in required_fields

        result[field_path] = (field_type, is_required)

        # Recursively process nested objects
        if isinstance(field_schema.get("properties"), dict):
            nested = _extract_properties_flat(field_schema, prefix=field_path, required_ancestors=is_required)
            result.update(nested)

    return result


def _removed_output_changes(
    old_fields: dict[str, tuple[str, bool]], new_fields: dict[str, tuple[str, bool]]
) -> list[OutputSchemaChange]:
    return [
        OutputSchemaChange(change_type="removed_output", field_path=path, old_type=field_type)
        for path, (field_type, _required) in old_fields.items()
        if path not in new_fields
    ]


def _changed_output_changes(
    old_fields: dict[str, tuple[str, bool]], new_fields: dict[str, tuple[str, bool]]
) -> list[OutputSchemaChange]:
    changes: list[OutputSchemaChange] = []
    for path, (old_type, old_required) in old_fields.items():
        new_field = new_fields.get(path)
        if not new_field:
            continue
        new_type, new_required = new_field
        if old_type != new_type:
            changes.append(OutputSchemaChange("type_change", path, old_type=old_type, new_type=new_type))
        if new_required and not old_required:
            changes.append(
                OutputSchemaChange(
                    "required_output",
                    path,
                    old_type=old_type,
                    new_type=new_type,
                    description=f"Output is now required: {path}",
                )
            )
        elif old_required and not new_required:
            changes.append(
                OutputSchemaChange("optional_output", path, old_type=old_type, new_type=new_type, is_breaking=False)
            )
    return changes


def _added_output_changes(
    old_fields: dict[str, tuple[str, bool]],
    new_fields: dict[str, tuple[str, bool]],
    *,
    first_declaration: bool,
) -> list[OutputSchemaChange]:
    changes = []
    for path, (new_type, is_required) in new_fields.items():
        if path in old_fields:
            continue
        change_type = "new_required_output" if is_required else "added_output"
        changes.append(
            OutputSchemaChange(
                change_type,
                path,
                new_type=new_type,
                is_breaking=is_required and not first_declaration,
            )
        )
    return changes


def detect_output_schema_changes(
    old_schema: dict[str, Any] | None,
    new_schema: dict[str, Any] | None,
) -> list[OutputSchemaChange]:
    """Detect all public output contract changes between two schemas."""
    old_fields = _extract_properties_flat(old_schema) if old_schema is not None else {}
    new_fields = _extract_properties_flat(new_schema) if new_schema is not None else {}
    first_declaration = old_schema is None
    return [
        *_removed_output_changes(old_fields, new_fields),
        *_changed_output_changes(old_fields, new_fields),
        *_added_output_changes(old_fields, new_fields, first_declaration=first_declaration),
    ]


def detect_output_schema_breaking_changes(
    old_schema: dict[str, Any] | None,
    new_schema: dict[str, Any] | None,
) -> list[OutputSchemaChange]:
    """Detect only output schema changes that can break existing consumers."""
    return [change for change in detect_output_schema_changes(old_schema, new_schema) if change.is_breaking]


def detect_workflow_breaking_changes(
    old_definition: dict[str, Any] | None,
    new_definition: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Detect breaking output contract changes in a workflow definition."""
    contract_changes = detect_workflow_contract_changes(old_definition, new_definition)
    breaking_changes: dict[str, list[dict[str, Any]]] = {}
    for trigger_id, changes in contract_changes.items():
        breaking = [change for change in changes if change["is_breaking"]]
        if breaking:
            breaking_changes[trigger_id] = breaking
    return breaking_changes


def detect_workflow_contract_changes(
    old_definition: dict[str, Any] | None,
    new_definition: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Detect breaking and non-breaking output contract changes by trigger."""
    old_triggers = {
        trigger.get("id"): trigger
        for trigger in (old_definition or {}).get("triggers", [])
        if isinstance(trigger, dict) and trigger.get("type") == "subworkflow_trigger" and trigger.get("id") is not None
    }
    new_triggers = {
        trigger.get("id"): trigger
        for trigger in new_definition.get("triggers", [])
        if isinstance(trigger, dict) and trigger.get("type") == "subworkflow_trigger" and trigger.get("id") is not None
    }

    result: dict[str, list[dict[str, Any]]] = {}
    for trigger_id in old_triggers.keys() | new_triggers.keys():
        old_trigger = old_triggers.get(trigger_id)
        new_trigger = new_triggers.get(trigger_id)
        old_params = old_trigger.get("parameters", {}) if old_trigger else {}
        new_params = new_trigger.get("parameters", {}) if new_trigger else {}
        old_schema = old_params.get("output_schema") if isinstance(old_params, dict) else None
        new_schema = new_params.get("output_schema") if isinstance(new_params, dict) else None

        changes = detect_output_schema_changes(old_schema, new_schema)
        old_mapping = old_params.get("output_mapping", {}) if isinstance(old_params, dict) else {}
        new_mapping = new_params.get("output_mapping", {}) if isinstance(new_params, dict) else {}
        if isinstance(old_mapping, dict) and isinstance(new_mapping, dict):
            for field_path in old_mapping.keys() | new_mapping.keys():
                if old_mapping.get(field_path) != new_mapping.get(field_path):
                    changes.append(
                        OutputSchemaChange(
                            change_type="mapping_changed",
                            field_path=str(field_path),
                            description=f"Changed the source mapping for output: {field_path}",
                            is_breaking=False,
                        )
                    )
        if old_trigger is not None and new_trigger is None:
            changes.append(
                OutputSchemaChange(
                    change_type="removed_trigger",
                    field_path=str(trigger_id),
                    description=f"Removed SubWorkflow Trigger: {trigger_id}",
                )
            )
        if changes:
            result[str(trigger_id)] = [change.to_dict() for change in changes]

    return result
