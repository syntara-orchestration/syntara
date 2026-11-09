"""OpenAPI shape adjustments for workflow response schemas."""

from typing import Any


def compose_workflow_response_schemas(spec: dict[str, Any]) -> None:
    """Render inherited workflow responses using the shared ``allOf`` contracts.

    Pydantic flattens inherited model fields in generated JSON Schema. The
    workflow domain spec composes these response schemas with ``allOf`` to
    avoid duplicating their shared fields. Keep generated OpenAPI documents in
    the same shape without changing response models or payloads.
    """
    schemas = spec.get("components", {}).get("schemas", {})
    if not isinstance(schemas, dict):
        return

    def compose(name: str, base_name: str, properties: tuple[str, ...], required: tuple[str, ...] = ()) -> None:
        schema = schemas.get(name)
        if not isinstance(schema, dict):
            return

        schema_properties = schema.get("properties")
        if not isinstance(schema_properties, dict) or any(
            property_name not in schema_properties for property_name in properties
        ):
            return

        extension: dict[str, Any] = {"type": "object"}
        if required:
            extension["required"] = list(required)
        extension["properties"] = {property_name: schema_properties[property_name] for property_name in properties}

        metadata = {key: value for key, value in schema.items() if key not in {"type", "required", "properties"}}
        schema.clear()
        schema.update(
            {
                **metadata,
                "allOf": [
                    {"$ref": f"#/components/schemas/{base_name}"},
                    extension,
                ],
            }
        )

    compose("WorkflowReadWithVersion", "WorkflowRead", ("version",), required=("version",))
    compose("WorkflowDetailRead", "WorkflowReadWithVersion", ("published_step_metadata",))
    compose("PublishWorkflowVersionResponse", "WorkflowReadWithVersion", ("warning",))
