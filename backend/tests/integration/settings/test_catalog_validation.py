"""Integration tests validating SETTINGS_CATALOG entries.

Ensures every catalog entry's validation_schema is compatible with its
value_type and that default_value passes validation. Catches developer
mistakes before they reach production.
"""

from __future__ import annotations

from syntara.settings.catalog import SETTINGS_CATALOG
from syntara.settings.validators import check_schema_compatibility, validate_setting_value


def test_all_catalog_schemas_are_compatible_with_value_types() -> None:
    """Every SETTINGS_CATALOG entry's validation_schema must be compatible with its value_type."""
    for defn in SETTINGS_CATALOG:
        if defn.validation_schema is None:
            continue
        # Should not raise for any real catalog entry
        check_schema_compatibility(
            key=defn.key,
            value_type=defn.value_type,
            schema=defn.validation_schema,
        )


def test_all_catalog_default_values_pass_validation() -> None:
    """Every SETTINGS_CATALOG entry's default_value must pass its own validation rules."""
    for defn in SETTINGS_CATALOG:
        if defn.default_value is None:
            continue
        # Should not raise for any real catalog entry
        validate_setting_value(
            key=defn.key,
            value=defn.default_value,
            value_type=defn.value_type,
            validation_schema=defn.validation_schema,
        )
