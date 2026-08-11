"""JSON Schema validation with security hardening.

Provides definition-time and runtime validation of JSON schemas.
Wraps the ``jsonschema`` library and adds guards that it does not
provide natively:

- Structurally invalid schemas (via Draft-07 meta-schema validation)
- SSRF via ``$ref`` keys that cause the validator to fetch remote resources
- ReDoS via ``pattern`` values with nested quantifiers

"""

from __future__ import annotations

import copy
import re
from typing import Any, NoReturn

import jsonschema
from jsonschema import validators
from referencing import Registry
from referencing.exceptions import NoSuchResource

# ---------------------------------------------------------------------------
# ReDoS heuristic
# ---------------------------------------------------------------------------

# Detects nested quantifiers inside groups — the most common ReDoS vector.
# Matches patterns like (a+)+, (x*y*)+, (a|b)*, (a{2,})+, etc.
# This targets group-then-quantifier where the group body also has a quantifier.
_NESTED_QUANTIFIER_RE = re.compile(
    r"\("  # Opening paren
    r"[^)]*"  # Any content inside the group
    r"(?:[+*]|\{\d+,\d*\})"  # A quantifier inside: +, *, or {n,m}
    r"[^)]*"  # More content
    r"\)"  # Closing paren
    r"(?:[+*]|\{\d+,\d*\})",  # Followed by an outer quantifier
)


def _has_dangerous_pattern(pattern: str) -> bool:
    """Check whether a regex pattern contains nested quantifiers.

    This heuristic flags the most common class of ReDoS vulnerability:
    quantified groups whose body also contains quantifiers, e.g.
    ``(a+)+$``, ``(x*y*)*z``.

    Known limitations:
    - Cannot detect nested-group patterns like ``((a+))+`` because
      ``[^)]*`` stops at the inner ``)``
    - Does not catch alternation-based ReDoS like ``(a|a)*``
    - A regex AST analysis library would provide more comprehensive
      detection but is deferred to a follow-up

    Returns:
        True if the pattern looks dangerous.

    """
    return bool(_NESTED_QUANTIFIER_RE.search(pattern))


# ---------------------------------------------------------------------------
# Schema tree walker
# ---------------------------------------------------------------------------


def _walk_schema(schema: dict[str, Any]) -> None:
    """Walk a JSON Schema dict tree, rejecting ``$ref`` and dangerous patterns.

    Raises:
        ValueError: If a ``$ref`` key is found or a ``pattern`` value is
            dangerous or syntactically invalid.

    """
    for key, value in schema.items():
        if key == "$ref":
            msg = "JSON Schema must not contain $ref references. Schemas must be self-contained."
            raise ValueError(msg)

        if key == "pattern" and isinstance(value, str):
            _check_regex_pattern(value, "pattern")
        elif key == "patternProperties" and isinstance(value, dict):
            # patternProperties keys are also regexes compiled by jsonschema
            _check_pattern_properties_keys(value)

        # Recurse into nested dicts and arrays of dicts
        _recurse_schema_value(value)


def _check_pattern_properties_keys(properties: dict[str, Any]) -> None:
    """Check all keys of a ``patternProperties`` dict for regex safety."""
    for pattern_key in properties:
        if isinstance(pattern_key, str):
            _check_regex_pattern(pattern_key, "patternProperties")


def _recurse_schema_value(value: Any) -> None:  # noqa: ANN401
    """Recurse into nested dicts and arrays of dicts."""
    if isinstance(value, dict):
        _walk_schema(value)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                _walk_schema(item)


def _check_regex_pattern(pattern: str, context: str) -> None:
    """Validate a regex pattern for syntax and ReDoS safety.

    Args:
        pattern: The regex pattern string.
        context: Where the pattern was found (e.g. ``"pattern"`` or
            ``"patternProperties"``), used in error messages.

    Raises:
        ValueError: If the pattern has invalid syntax or contains nested
            quantifiers.

    """
    try:
        re.compile(pattern)
    except re.error as e:
        msg = f"Invalid regex in '{context}': {e}"
        raise ValueError(msg) from e

    if _has_dangerous_pattern(pattern):
        msg = (
            f"Potentially unsafe regex in '{context}': '{pattern}'. "
            "Nested quantifiers (e.g. '(a+)+') can cause catastrophic "
            "backtracking and are not allowed."
        )
        raise ValueError(msg)


# ---------------------------------------------------------------------------
# Definition-time validation
# ---------------------------------------------------------------------------


def validate_json_schema_definition(schema: dict[str, Any]) -> None:
    """Validate a JSON Schema at definition time (workflow create/update).

    Checks:
    1. Structural validity against the Draft-07 meta-schema.
    2. No ``$ref`` keys anywhere in the schema tree.
    3. All ``pattern`` values are syntactically valid regexes without
       nested quantifiers.

    Args:
        schema: The JSON Schema dict to validate.

    Raises:
        ValueError: If the schema is invalid, contains ``$ref``, or has
            dangerous regex patterns.

    """
    # 1. Meta-schema validation
    try:
        jsonschema.Draft7Validator.check_schema(schema)
    except jsonschema.SchemaError as e:
        msg = f"Invalid JSON Schema: {e.message}"
        raise ValueError(msg) from e

    # 2 & 3. Walk tree for $ref and pattern checks
    _walk_schema(schema)


# ---------------------------------------------------------------------------
# Runtime payload validation (with $ref resolution disabled)
# ---------------------------------------------------------------------------


def _deny_all_refs(uri: str) -> NoReturn:
    """Registry retrieval function that denies all $ref resolution."""
    raise NoSuchResource(ref=uri)  # type: ignore[call-arg]


_NO_REF_REGISTRY: Registry[Any] = Registry(retrieve=_deny_all_refs)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Default-filling validator
# ---------------------------------------------------------------------------


def _extend_with_defaults(
    validator_class: type[jsonschema.protocols.Validator],
) -> type[jsonschema.protocols.Validator]:
    """Extend a validator class to fill in ``default`` values during validation."""
    validate_properties = validator_class.VALIDATORS["properties"]

    def set_defaults(
        validator: jsonschema.protocols.Validator,
        properties: dict[str, Any],
        instance: Any,  # noqa: ANN401
        schema: dict[str, Any],
    ) -> Any:  # noqa: ANN401
        if isinstance(instance, dict):
            for prop, subschema in properties.items():
                if "default" in subschema:
                    instance.setdefault(prop, copy.deepcopy(subschema["default"]))

        yield from validate_properties(validator, properties, instance, schema)

    return validators.extend(validator_class, {"properties": set_defaults})  # type: ignore[no-untyped-call,no-any-return]


_DefaultFillingDraft7Validator: type[jsonschema.protocols.Validator] = _extend_with_defaults(
    jsonschema.Draft7Validator,
)


def apply_schema_defaults(
    input_data: dict[str, Any],
    schema: dict[str, Any],
) -> None:
    """Fill in ``default`` values from a JSON Schema and validate the result.

    Uses a ``Draft7Validator`` extended with default-filling behaviour so
    that nested object defaults are handled recursively.  Defaults are
    applied first, then the merged result is validated — so a ``required``
    field with a ``default`` will pass validation.

    ``$ref`` resolution is blocked to prevent SSRF.

    Args:
        input_data: User-provided input data (mutated in place).
        schema: JSON Schema dict (Draft-07).

    Raises:
        jsonschema.ValidationError: If input_data does not conform after
            defaults are applied.
        jsonschema.SchemaError: If the schema itself is malformed.

    """
    validator = _DefaultFillingDraft7Validator(schema, registry=_NO_REF_REGISTRY)
    validator.validate(input_data)
