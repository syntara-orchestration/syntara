"""Database-backed setting category for grouping runtime settings.

Each row represents a logical grouping of settings (e.g. "Context Manager").
The ``slug`` matches the string values formerly stored in the ``settingcategory``
PostgreSQL enum, ensuring backward compatibility with existing
``runtime_settings.category`` data.
"""

from __future__ import annotations

from typing import ClassVar

from sqlalchemy import String
from sqlmodel import Field

from syntara.core.constants import FieldLimits
from syntara.core.models.base.named import NamedResource


class SettingCategoryModel(NamedResource, table=True):
    """A setting category with display metadata.

    Attributes:
        slug: Machine key matching ``runtime_settings.category`` values
            (e.g. ``'context_manager'``). Unique and indexed.
        display_order: Sort position for UI rendering (lower = first).

    Inherits from NamedResource:
        id: UUID primary key.
        name: Human-readable display name (e.g. "Context Manager").
        description: Optional longer description shown in the UI.
        created_at / updated_at: Automatic timestamps.
        labels: JSONB key-value metadata.

    """

    __tablename__ = "setting_categories"

    slug: str = Field(
        min_length=1,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="Machine key matching runtime_settings.category values",
        unique=True,
        index=True,
    )

    display_order: int = Field(
        default=0,
        description="Sort position for UI rendering (lower = first)",
    )

    __filterable_fields__: ClassVar[list[str]] = [
        *NamedResource.__filterable_fields__,
        "slug",
    ]

    __sortable_fields__: ClassVar[list[str]] = [
        *NamedResource.__sortable_fields__,
        "slug",
        "display_order",
    ]
