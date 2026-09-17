"""Post-migration seeder for setting categories and runtime settings.

Upserts all entries from :data:`~syntara.settings.catalog.CATEGORY_CATALOG`
and :data:`~syntara.settings.catalog.SETTINGS_CATALOG` into their respective
tables.

Design:
    - Idempotent — safe to run repeatedly.
    - Categories are seeded before settings (FK target must exist first).
    - Uses ``INSERT ... ON CONFLICT DO UPDATE`` to refresh metadata
      fields without ever overwriting user-mutable data (``value``,
      ``version``).
    - Safe under concurrent execution: the upsert is atomic per row at
      the database level.
    - Uses ``RETURNING (xmax = 0)`` to distinguish new inserts from
      metadata refreshes on existing rows (``xmax = 0`` ↔ new insert).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
import structlog
from sqlalchemy.dialects.postgresql import insert

from syntara.core.config.base import get_settings
from syntara.settings.catalog import CATEGORY_CATALOG, SETTINGS_CATALOG
from syntara.settings.models.runtime_setting import RuntimeSetting, SettingValueType
from syntara.settings.models.setting_category import SettingCategoryModel
from syntara.settings.validators import check_schema_compatibility, validate_setting_value

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.settings.catalog import SettingDefinition

logger = structlog.stdlib.get_logger(__name__)

_UPSERT_UPDATE_FIELDS = (
    "name",
    "description",
    "helper_text",
    "depends_on",
    "default_value",
    "value_type",
    "category",
    "group",
    "requires_restart",
    "cache_ttl_seconds",
    "validation_schema",
    "updated_at",
)

_CATEGORY_UPSERT_FIELDS = ("name", "description", "display_order", "updated_at")


# ---------------------------------------------------------------------------
# Shared upsert helper
# ---------------------------------------------------------------------------


async def _upsert(
    session: AsyncSession,
    model: type,
    rows: list[dict[str, object]],
    conflict_on: list[str],
    update_fields: tuple[str, ...],
) -> tuple[int, int]:
    """Insert rows, updating on conflict. Returns ``(inserts, updates)``.

    Uses ``RETURNING (xmax = 0)`` to distinguish new inserts (xmax is the
    transaction ID of the last update; 0 means the row was just inserted).
    """
    if not rows:
        return 0, 0

    upsert = insert(model).values(rows)
    upsert = upsert.on_conflict_do_update(
        index_elements=conflict_on,
        set_={col: upsert.excluded[col] for col in update_fields},
    )
    result = await session.exec(upsert.returning(sa.literal_column("(xmax = 0)")))
    is_insert_flags = list(result.scalars().all())
    inserts = sum(1 for flag in is_insert_flags if flag)
    return inserts, len(is_insert_flags) - inserts


# ---------------------------------------------------------------------------
# Per-table upsert builders
# ---------------------------------------------------------------------------


async def _upsert_categories(session: AsyncSession) -> tuple[int, int]:
    """Upsert category catalog entries. Returns ``(inserts, updates)``."""
    if not CATEGORY_CATALOG:
        return 0, 0

    now = datetime.now(UTC)
    rows: list[dict[str, object]] = [
        {
            "id": uuid4(),
            "slug": cat.slug,
            "name": cat.name,
            "description": cat.description,
            "display_order": cat.display_order,
            "labels": {},
            "created_at": now,
            "updated_at": now,
        }
        for cat in CATEGORY_CATALOG
    ]

    return await _upsert(session, SettingCategoryModel, rows, ["slug"], _CATEGORY_UPSERT_FIELDS)


def _check_depends_on_cycles(catalog_by_key: dict[str, SettingDefinition]) -> None:
    """Raise if any depends_on chain forms a cycle."""
    for defn in catalog_by_key.values():
        visited: set[str] = set()
        key: str | None = defn.key
        while key is not None:
            if key in visited:
                msg = f"Circular depends_on chain detected: {' -> '.join(visited)} -> {key}"
                raise ValueError(msg)
            visited.add(key)
            key = catalog_by_key[key].depends_on if key in catalog_by_key else None


def _validate_catalog() -> None:
    """Validate SETTINGS_CATALOG entries against categories and schemas."""
    valid_category_slugs = {cat.slug for cat in CATEGORY_CATALOG}
    catalog_by_key = {defn.key: defn for defn in SETTINGS_CATALOG}

    for defn in SETTINGS_CATALOG:
        cat_slug = defn.category.value if hasattr(defn.category, "value") else str(defn.category)
        if cat_slug not in valid_category_slugs:
            msg = f"Setting '{defn.key}' references undefined category '{cat_slug}'"
            raise ValueError(msg)
        if defn.validation_schema:
            check_schema_compatibility(defn.key, defn.value_type, defn.validation_schema)
        validate_setting_value(
            key=defn.key,
            value=defn.default_value,
            value_type=defn.value_type,
            validation_schema=defn.validation_schema,
        )
        if defn.depends_on is not None:
            if defn.depends_on == defn.key:
                msg = f"Setting '{defn.key}' cannot depend on itself"
                raise ValueError(msg)
            target = catalog_by_key.get(defn.depends_on)
            if target is None:
                msg = f"Setting '{defn.key}' depends_on unknown key '{defn.depends_on}'"
                raise ValueError(msg)
            if target.value_type != SettingValueType.BOOLEAN:
                msg = (
                    f"Setting '{defn.key}' depends_on '{defn.depends_on}' "
                    f"which is {target.value_type.value}, not boolean"
                )
                raise ValueError(msg)

    _check_depends_on_cycles(catalog_by_key)


def _resolve_default(value: object) -> object:
    """Resolve ``{product_name}`` placeholders in string defaults."""
    if isinstance(value, str) and "{product_name}" in value:
        return value.replace("{product_name}", get_settings().product_name)
    return value


async def _upsert_settings(session: AsyncSession) -> tuple[int, int]:
    """Upsert settings catalog entries. Returns ``(inserts, updates)``."""
    if not SETTINGS_CATALOG:
        return 0, 0

    _validate_catalog()

    now = datetime.now(UTC)
    rows: list[dict[str, object]] = [
        {
            "id": uuid4(),
            "name": defn.name,
            "description": defn.description,
            "helper_text": defn.helper_text,
            "depends_on": defn.depends_on,
            "key": defn.key,
            "category": defn.category,
            "value_type": defn.value_type,
            "default_value": _resolve_default(defn.default_value),
            "value": None,
            "group": defn.group,
            "requires_restart": defn.requires_restart,
            "cache_ttl_seconds": defn.cache_ttl_seconds,
            "validation_schema": defn.validation_schema,
            "version": 1,
            "labels": {},
            "created_at": now,
            "updated_at": now,
        }
        for defn in SETTINGS_CATALOG
    ]

    return await _upsert(session, RuntimeSetting, rows, ["key"], _UPSERT_UPDATE_FIELDS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def seed_settings_with_session(session: AsyncSession) -> None:
    """Seed categories and settings using an externally-provided session.

    Conforms to the unified ``SeederFunc(session)`` interface used by
    :func:`syntara.core.seed.run_seeders`.
    """
    cat_inserts, cat_updates = await _upsert_categories(session)
    if cat_inserts or cat_updates:
        logger.info("settings.categories.seeded", inserted=cat_inserts, updated=cat_updates)

    setting_inserts, setting_updates = await _upsert_settings(session)
    if setting_inserts or setting_updates:
        logger.info("settings.seeder.complete", inserted=setting_inserts, updated=setting_updates)
    else:
        logger.info("settings.seeder.empty_catalog")

    await session.commit()


async def seed_settings(session_factory: Any) -> None:  # noqa: ANN401
    """Upsert categories and settings into their respective tables.

    Seeds categories first (FK target), then settings. Both operations
    are idempotent — safe to run repeatedly.

    Args:
        session_factory: Async session factory (``async_sessionmaker`` or
            compatible callable returning an async context manager that
            yields an :class:`~sqlmodel.ext.asyncio.session.AsyncSession`).

    """
    async with session_factory() as session:
        await seed_settings_with_session(session)
