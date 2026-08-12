"""RuntimeSetting SQLModel and related enums.

Defines the database-backed runtime configuration settings for the Nexus
application. Settings are user-managed key-value pairs that can be
changed without restarting the application (for those with
``requires_restart=False``).

Optimistic locking is enforced via the ``version`` field: every successful
write increments it, and callers must submit the current version to avoid
overwriting concurrent changes.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, ClassVar

from sqlalchemy import Column, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from syntara.core.constants import FieldLimits
from syntara.core.models.base import NamedResource
from syntara.core.utils.sqlmodel import postgres_enum_column

_KEY_MAX_LENGTH = FieldLimits.NAME_MAX_LENGTH


# PostgreSQL ENUM migration note: adding a value is safe (ALTER TYPE … ADD VALUE).
# Renaming or removing requires a multi-step migration; Alembic autogenerate cannot handle it.
class SettingCategory(str, Enum):
    """Logical grouping for runtime settings, used for display and filtering."""

    AI_LLM = "ai_llm"
    WORKFLOW_EXECUTION = "workflow_execution"
    INTEGRATIONS = "integrations"
    SYSTEM = "system"
    CONTEXT_MANAGER = "context_manager"
    APPLICATION = "application"
    AUTHENTICATION = "authentication"
    RATE_LIMITING = "rate_limiting"


# Same PostgreSQL ENUM migration constraints as SettingCategory apply.
class SettingValueType(str, Enum):
    """Expected value type for a runtime setting, used for UI rendering and validation."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    JSON = "json"


class RuntimeSetting(NamedResource, table=True):
    """Database-backed runtime configuration setting.

    Inherits from :class:`NamedResource`, which provides:

    - ``id``: UUID primary key
    - ``created_at`` / ``updated_at``: automatic timestamps
    - ``labels``: JSONB key-value metadata
    - ``name``: human-readable display name (required)
    - ``description``: optional longer description

    The ``key`` field is a dot-namespaced programmatic identifier
    (e.g. ``context_manager.max_total_tokens``) used by application code
    and the seeder. It is globally unique and serves as the primary
    lookup key. It is distinct from ``name`` to allow the display name
    to change without breaking application references.

    Optimistic locking:
        ``version`` starts at 1 and is incremented on every successful
        write. Writers must submit the current ``version``; a mismatch
        is rejected.

    Value resolution:
        The effective value is ``value`` when not ``None``, otherwise
        ``default_value``. Both are stored as native Python types in JSONB
        (no string round-tripping).

    Caching:
        ``cache_ttl_seconds`` controls per-process in-memory TTL for this
        setting. ``None`` delegates to the 60-second default in
        :class:`~syntara.settings.cache.settings_cache.SettingsCache`.

    Attributes:
        key: Setting identifier, e.g. ``model_name``. Unique within category.
        value: User-set override; ``None`` means use ``default_value``.
        default_value: Factory default as a native Python type.
        value_type: Expected type, for UI rendering and validation.
        category: Logical grouping.
        requires_restart: Whether the change takes effect without restart.
        cache_ttl_seconds: Per-setting TTL override in seconds.
        validation_schema: Optional JSONB constraints dict (min, max,
            allowed_values, pattern).
        version: Optimistic lock counter; starts at 1.

    """

    __tablename__ = "runtime_settings"

    __table_args__ = (UniqueConstraint("key", name="uq_runtime_settings_key"),)

    __filterable_fields__: ClassVar[list[str]] = [
        *NamedResource.__filterable_fields__,
        "key",
        "category",
        "group",
        "requires_restart",
    ]

    __sortable_fields__: ClassVar[list[str]] = [
        *NamedResource.__sortable_fields__,
        "key",
        "category",
    ]

    key: str = Field(
        min_length=1,
        max_length=_KEY_MAX_LENGTH,
        sa_type=String(_KEY_MAX_LENGTH),  # type: ignore[call-overload]
        description="Setting key, e.g. 'model_name'. Unique within category.",
        index=True,
    )

    value: Any = Field(
        default=None,
        sa_type=JSONB,
        sa_column_kwargs={"nullable": True},
        description="User-set override; None means use default_value",
    )

    default_value: Any = Field(
        default=None,
        sa_type=JSONB,
        sa_column_kwargs={"nullable": True},
        description="Factory default as a native Python type (int, float, bool, str, list)",
    )

    value_type: SettingValueType = Field(
        sa_column=postgres_enum_column(
            SettingValueType,
            "settingvaluetype",
            index=True,
        ),
        description="Expected value type for UI rendering and validation",
    )

    category: str = Field(
        sa_column=Column(
            String(FieldLimits.NAME_MAX_LENGTH),
            ForeignKey("setting_categories.slug"),
            nullable=False,
            index=True,
        ),
        description="Logical grouping for display and filtering",
    )

    helper_text: str | None = Field(
        default=None,
        max_length=FieldLimits.DESCRIPTION_MAX_LENGTH,
        sa_type=String(FieldLimits.DESCRIPTION_MAX_LENGTH),  # type: ignore[call-overload]
        description="Short inline guidance shown below the setting field in the UI",
    )

    depends_on: str | None = Field(
        default=None,
        max_length=_KEY_MAX_LENGTH,
        sa_type=String(_KEY_MAX_LENGTH),  # type: ignore[call-overload]
        description="Dot-namespaced key of a boolean setting that controls this setting's visibility",
    )

    group: str | None = Field(
        default=None,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="Display group within the category (e.g. 'Token limits')",
    )

    requires_restart: bool = Field(
        default=False,
        description="Whether changing this setting takes effect without a restart",
    )

    cache_ttl_seconds: int | None = Field(
        default=None,
        description="Per-setting in-memory cache TTL in seconds; None uses the 60s default",
    )

    validation_schema: dict[str, Any] | None = Field(
        default=None,
        sa_type=JSONB,
        description="Optional validation constraints: min, max, allowed_values, pattern",
    )

    version: int = Field(
        default=1,
        description="Optimistic lock counter; incremented on every successful write",
    )
