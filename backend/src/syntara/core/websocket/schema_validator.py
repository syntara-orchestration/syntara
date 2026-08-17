"""Simple JSON schema validation for WebSocket messages.

This module provides lightweight validation of dict messages against AsyncAPI
specifications without using SQLModel or Pydantic.
"""

from pathlib import Path
from typing import Any

import structlog
import yaml

from syntara.core.exceptions import SyntaraError

logger = structlog.stdlib.get_logger(__name__)


class ValidationError(SyntaraError):
    """Raised when message validation fails."""

    def __init__(self, error_type: str, message: str, field: str | None = None) -> None:
        """Initialize validation error.

        Args:
            error_type: Type of validation error (INVALID_REQUEST, VALIDATION_ERROR, etc.)
            message: Human-readable error message
            field: Optional field name that failed validation

        """
        self.error_type = error_type
        self.message = message
        self.field = field
        super().__init__(message)


class SchemaValidator:
    """Validates dicts against AsyncAPI message schemas."""

    def __init__(self) -> None:
        """Initialize the schema validator with empty caches."""
        self._specs: dict[str, dict[str, Any]] = {}

    def validate(self, data: dict[str, Any], message_type: str, spec_path: str | Path) -> None:
        """Validate a dict against an AsyncAPI message schema.

        Args:
            data: Message data to validate
            message_type: Name of the message type (e.g., "ExampleRequest")
            spec_path: Path to the AsyncAPI specification file or component name

        Raises:
            ValidationError: If validation fails

        """
        spec_key = str(spec_path)

        # Load spec if not cached
        if spec_key not in self._specs:
            # Try to load from global cache (for component names)
            # Import here to avoid circular dependency
            try:
                from syntara.core.websocket.endpoint_factory import get_spec_from_cache  # noqa: PLC0415

                cached_spec = get_spec_from_cache(spec_key)
                if cached_spec is not None:
                    self._specs[spec_key] = cached_spec
                    spec = cached_spec
                else:
                    # Fall back to file loading
                    spec_path_obj = Path(spec_path)
                    if not spec_path_obj.exists():
                        msg = f"AsyncAPI spec not found: {spec_path}"
                        raise FileNotFoundError(msg) from None
                    with spec_path_obj.open() as f:
                        self._specs[spec_key] = yaml.safe_load(f)
                        spec = self._specs[spec_key]
            except ImportError:
                # Fall back to file loading if import fails
                spec_path_obj = Path(spec_path)
                if not spec_path_obj.exists():
                    msg = f"AsyncAPI spec not found: {spec_path}"
                    raise FileNotFoundError(msg) from None
                with spec_path_obj.open() as f:
                    self._specs[spec_key] = yaml.safe_load(f)
                    spec = self._specs[spec_key]
        else:
            spec = self._specs[spec_key]

        # Find message definition
        messages = spec.get("components", {}).get("messages", {})
        if message_type not in messages:
            available = ", ".join(messages.keys())
            msg = f"Message type '{message_type}' not found. Available: {available}"
            error_type = "INTERNAL_ERROR"
            raise ValidationError(error_type, msg)

        message_def = messages[message_type]
        schema = message_def.get("payload", {})

        # Validate against schema
        self._validate_schema(data, schema)

    def _validate_schema(self, data: dict[str, Any], schema: dict[str, Any]) -> None:
        """Validate data against a JSON schema.

        Args:
            data: Data to validate
            schema: JSON schema to validate against

        Raises:
            ValidationError: If validation fails

        """
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        # Check required fields
        for field_name in required:
            if field_name not in data:
                # Error type is constant per ValidationError design
                raise ValidationError("VALIDATION_ERROR", f"Field '{field_name}' is required", field_name)  # noqa: EM101

        # Validate each field
        for field_name, value in data.items():
            if field_name not in properties:
                # Skip extra fields (lenient validation)
                logger.debug("Unknown field in message, skipping validation", field_name=field_name)
                continue

            field_schema = properties[field_name]
            self._validate_field(field_name, value, field_schema)

    def _validate_field(self, field_name: str, value: Any, schema: dict[str, Any]) -> None:  # noqa: ANN401 - Validating arbitrary JSON
        """Validate a single field against its schema.

        Args:
            field_name: Name of the field
            value: Value to validate
            schema: Field schema

        Raises:
            ValidationError: If validation fails

        """
        json_type = schema.get("type", "string")

        # Type validation
        if not self._check_type(value, json_type):
            error_type = "VALIDATION_ERROR"
            raise ValidationError(
                error_type,
                f"Field '{field_name}' must be of type {json_type}",
                field_name,
            )

        # Type-specific constraints
        if json_type == "string":
            self._validate_string(field_name, value, schema)
        elif json_type in ("integer", "number"):
            self._validate_number(field_name, value, schema)

    def _check_type(self, value: Any, json_type: str) -> bool:  # noqa: ANN401 - Validating arbitrary JSON
        """Check if value matches JSON schema type.

        Args:
            value: Value to check
            json_type: JSON schema type name

        Returns:
            True if type matches, False otherwise

        """
        type_mapping = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }

        expected_type = type_mapping.get(json_type)
        if expected_type is None:
            return True  # Unknown type, skip validation

        return isinstance(value, expected_type)  # type: ignore[arg-type]

    def _validate_string(self, field_name: str, value: str, schema: dict[str, Any]) -> None:
        """Validate string field constraints.

        Args:
            field_name: Name of the field
            value: String value to validate
            schema: Field schema

        Raises:
            ValidationError: If validation fails

        """
        # minLength
        if "minLength" in schema:
            min_length = schema["minLength"]
            if len(value) < min_length:
                error_type = "VALIDATION_ERROR"
                raise ValidationError(
                    error_type,
                    f"Field '{field_name}' must be at least {min_length} characters",
                    field_name,
                )

        # maxLength
        if "maxLength" in schema:
            max_length = schema["maxLength"]
            if len(value) > max_length:
                error_type = "VALIDATION_ERROR"
                raise ValidationError(
                    error_type,
                    f"Field '{field_name}' must be at most {max_length} characters",
                    field_name,
                )

        # enum
        if "enum" in schema:
            allowed_values = schema["enum"]
            if value not in allowed_values:
                error_type = "VALIDATION_ERROR"
                raise ValidationError(
                    error_type,
                    f"Field '{field_name}' must be one of: {', '.join(allowed_values)}",
                    field_name,
                )

    def _validate_number(self, field_name: str, value: float, schema: dict[str, Any]) -> None:
        """Validate numeric field constraints.

        Args:
            field_name: Name of the field
            value: Numeric value to validate
            schema: Field schema

        Raises:
            ValidationError: If validation fails

        """
        # minimum
        if "minimum" in schema:
            minimum = schema["minimum"]
            if value < minimum:
                error_type = "VALIDATION_ERROR"
                raise ValidationError(
                    error_type,
                    f"Field '{field_name}' must be >= {minimum}",
                    field_name,
                )

        # maximum
        if "maximum" in schema:
            maximum = schema["maximum"]
            if value > maximum:
                error_type = "VALIDATION_ERROR"
                raise ValidationError(
                    error_type,
                    f"Field '{field_name}' must be <= {maximum}",
                    field_name,
                )

    def clear_cache(self) -> None:
        """Clear all cached specs."""
        self._specs.clear()


# Global validator instance
_validator = SchemaValidator()


def validate_message(data: dict[str, Any], message_type: str, spec_path: str | Path) -> None:
    """Validate a message dict against an AsyncAPI specification.

    This is the primary API for message validation.

    Args:
        data: Message data to validate
        message_type: Name of the message type (e.g., "ExampleRequest")
        spec_path: Path to the AsyncAPI specification file

    Raises:
        ValidationError: If validation fails

    Examples:
        >>> from pathlib import Path
        >>> spec = Path("example.yaml")
        >>> validate_message({"input": "hello"}, "ExampleRequest", spec)
        >>> # Raises ValidationError if invalid

    """
    _validator.validate(data, message_type, spec_path)


def clear_validator_cache() -> None:
    """Clear the global validator cache.

    Useful for testing or when specs are updated at runtime.
    """
    _validator.clear_cache()
