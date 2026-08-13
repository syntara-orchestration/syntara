"""Audit metadata seeder.

Populates audit_table_metadata and attaches triggers to auditable tables.
This seeder processes all SQLModel classes to discover which tables require
audit triggers based on their __auditable__ configuration.

The setup is idempotent - it can be run multiple times safely.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from sqlalchemy import text

from syntara.core.config.base import get_settings
from syntara.core.database.migrations.models import ALL_MODELS
from syntara.core.models.base.base_resource import AuditLevel, BaseResource

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = structlog.stdlib.get_logger(__name__)


async def seed_audit_metadata(session: AsyncSession) -> None:
    """Populate audit_table_metadata and attach triggers to auditable tables.

    This function uses a clean-slate approach to ensure no orphaned data:
    1. Checks if audit_table_metadata exists (returns early if not)
    2. Deletes all existing audit metadata records and drops all audit triggers
    3. Processes all registered SQLModel classes (imported from migrations/env.py)
    4. Filters to only those with __auditable__ != NONE
    5. Inserts fresh metadata records for each auditable table
    6. Creates all audit triggers at once via audit_triggers_enable()

    The clean-slate approach ensures that if a model is removed from ALL_MODELS,
    its metadata and trigger are automatically cleaned up on the next seeder run.

    Safe to call if audit_table_metadata doesn't exist - will skip gracefully.

    Args:
        session: Database session (caller manages lifecycle).

    """
    # Check if audit_table_metadata exists before proceeding
    # This handles the case where the audit migration hasn't run yet
    table_exists_result = await session.exec(  # type: ignore[call-overload]
        text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'audit_table_metadata'
            )
        """)
    )
    table_exists = table_exists_result.scalar()

    if not table_exists:
        logger.debug(
            "audit.setup.skipped",
            reason="audit_table_metadata_does_not_exist",
            detail="Table not found - likely before audit migration",
        )
        return

    logger.info("audit.setup.start", total_models=len(ALL_MODELS))

    # Clean slate: delete all existing metadata and triggers
    # This ensures we don't have orphaned records for removed models
    await session.exec(text("DELETE FROM audit_table_metadata"))  # type: ignore[call-overload]
    logger.debug("audit.setup.cleanup", action="deleted_all_metadata")

    # Drop all audit triggers (matching our naming convention)
    # This prevents orphaned triggers for removed tables
    drop_triggers_result = await session.exec(  # type: ignore[call-overload]
        text("""
            SELECT t.tgname, c.relname
            FROM pg_trigger t
            JOIN pg_class c ON t.tgrelid = c.oid
            WHERE t.tgname LIKE 'audit_trigger_%'
              AND NOT t.tgisinternal
        """)
    )
    for trigger_name, table_name in drop_triggers_result.all():
        await session.exec(text(f"DROP TRIGGER IF EXISTS {trigger_name} ON {table_name}"))  # type: ignore[call-overload]
        logger.debug("audit.setup.cleanup", action="dropped_trigger", trigger=trigger_name, table=table_name)

    # Skip trigger configuration if Auditing is disabled
    settings = get_settings()
    if not settings.audit_enabled:
        logger.warning("Auditing is disabled. Skipping trigger configuration.")
        return

    # Now recreate from current models
    auditable_count = 0
    skipped_count = 0

    for model_cls in ALL_MODELS:
        # Only process BaseResource subclasses
        if not issubclass(model_cls, BaseResource):
            continue

        # Check __auditable__ setting
        audit_level = getattr(model_cls, "__auditable__", AuditLevel.FULL)
        if audit_level == AuditLevel.NONE:
            skipped_count += 1
            logger.debug(
                "audit.setup.skip_model",
                model=model_cls.__name__,
                reason="audit_level_none",
            )
            continue

        # Extract metadata
        table_name = model_cls.__tablename__
        model_name = model_cls.__name__
        audit_level_str = audit_level.value

        # Build auditable_fields list for META mode
        auditable_fields: list[str] | None = None
        if audit_level == AuditLevel.META:
            base_fields = ["id", "created_at", "updated_at", "labels"]
            model_fields = list(getattr(model_cls, "__auditable_fields__", []))
            auditable_fields = base_fields + model_fields

        # Insert metadata record (we already deleted all, so just insert)
        await session.exec(  # type: ignore[call-overload]
            text("""
                INSERT INTO audit_table_metadata (table_name, model_name, audit_level, auditable_fields)
                VALUES (:table_name, :model_name, :audit_level, :auditable_fields)
            """),
            params={
                "table_name": table_name,
                "model_name": model_name,
                "audit_level": audit_level_str,
                "auditable_fields": auditable_fields,
            },
        )
        logger.debug(
            "audit.setup.insert_metadata",
            table=table_name,
            model=model_name,
            audit_level=audit_level_str,
        )

        auditable_count += 1

    # Create all triggers at once using the management function
    logger.debug("audit.setup.enable_triggers", action="enabling_all_triggers")
    enable_result = await session.exec(  # type: ignore[call-overload]
        text("SELECT * FROM audit_triggers_enable()")
    )
    for table_name, status in enable_result.all():
        logger.debug("audit.setup.trigger_enabled", table=table_name, status=status)

    await session.commit()

    logger.info(
        "audit.setup.complete",
        auditable_count=auditable_count,
        skipped_count=skipped_count,
        total_models=len(ALL_MODELS),
    )
