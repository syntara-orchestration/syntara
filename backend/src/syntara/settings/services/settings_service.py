"""SettingsService: REST API business logic for runtime settings.

Extends :class:`~syntara.core.services.base.BaseService` for consistent
pagination, filtering, and sorting. Provides CRUD operations with
optimistic locking and value validation.

For internal read-only access (e.g. from ``SettingsCache``), use
:class:`~syntara.settings.store.SettingsStore` instead.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

import structlog
from sqlalchemy import update as sa_update
from sqlmodel import select

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.core.services.base import BaseService
from syntara.settings.audit.settings import SettingBulkChangeEvent, SettingChangeEvent
from syntara.settings.cache.settings_cache import get_runtime_settings
from syntara.settings.exceptions import OptimisticLockError, SettingNotFoundError, SettingValidationError
from syntara.settings.models.api_models import (
    CategoriesListResponse,
    RuntimeSettingRead,
    SettingBulkUpdateItem,
    SettingCategoryRead,
    SettingsListResponse,
)
from syntara.settings.models.runtime_setting import RuntimeSetting
from syntara.settings.models.setting_category import SettingCategoryModel
from syntara.settings.validators import validate_setting_value

logger = structlog.stdlib.get_logger(__name__)

_MAX_SETTING_VALUE_BYTES = 65536
_MAX_AUDIT_VALUE_LENGTH = 256


def _format_setting_value(value: Any) -> str | None:  # noqa: ANN401
    """Convert a setting value to a string for audit logging, with truncation."""
    if value is None:
        return None
    str_value = str(value)
    if len(str_value) > _MAX_AUDIT_VALUE_LENGTH:
        return str_value[: _MAX_AUDIT_VALUE_LENGTH - 3] + "..."
    return str_value


async def _invalidate_and_publish(key: str) -> None:
    """Invalidate a cached setting and publish the change via Pub/Sub.

    Safe to call when the cache is not initialised — errors are suppressed.
    """
    with contextlib.suppress(RuntimeError):
        cache = get_runtime_settings()
        await cache.invalidate(key)
        await cache.publish_change(key)


def setting_to_read(setting: RuntimeSetting) -> RuntimeSettingRead:
    """Convert a RuntimeSetting to its API read schema."""
    return RuntimeSettingRead(
        id=setting.id,
        key=setting.key,
        name=setting.name,
        description=setting.description,
        helper_text=setting.helper_text,
        depends_on=setting.depends_on,
        category=setting.category,
        group=setting.group,
        value=setting.value,
        default_value=setting.default_value,
        effective_value=setting.value if setting.value is not None else setting.default_value,
        value_type=setting.value_type,
        requires_restart=setting.requires_restart,
        cache_ttl_seconds=setting.cache_ttl_seconds,
        validation_schema=setting.validation_schema,
        version=setting.version,
        created_at=setting.created_at,
        updated_at=setting.updated_at,
    )


class SettingsService(BaseService):
    """Service for runtime settings REST API operations.

    Extends BaseService for pagination and filtering support. Provides
    get, update, and bulk operations with optimistic locking.
    """

    async def list_categories(self) -> CategoriesListResponse:
        """List all setting categories with their group names.

        Queries the ``setting_categories`` table ordered by
        ``display_order`` and enriches each category with group names
        derived from the settings in that category.

        Returns:
            All categories with display metadata and group names.

        """
        cat_result = await self.session.exec(
            select(SettingCategoryModel).order_by(SettingCategoryModel.display_order)  # type: ignore[arg-type]
        )
        categories = cat_result.all()

        # Fetch distinct group names per category from runtime_settings
        groups_by_category: dict[str, list[str]] = {}
        group_result = await self.session.exec(
            select(RuntimeSetting.category, RuntimeSetting.group)
            .where(RuntimeSetting.group.is_not(None))  # type: ignore[union-attr]
            .distinct()
        )
        for cat_slug, group_name in group_result.all():
            if group_name is not None:
                groups_by_category.setdefault(cat_slug, []).append(group_name)

        return CategoriesListResponse(
            resources=[
                SettingCategoryRead(
                    slug=cat.slug,
                    name=cat.name,
                    description=cat.description,
                    display_order=cat.display_order,
                    group_names=sorted(groups_by_category.get(cat.slug, [])),
                )
                for cat in categories
            ]
        )

    async def list_settings(
        self,
        limit: int = 20,
        cursor: str | None = None,
        sort: str | None = None,
        query_params_items: Iterable[tuple[str, str]] | None = None,
        *,
        include_total: bool = False,
    ) -> SettingsListResponse:
        """List settings with pagination, filtering, and sorting.

        Args:
            limit: Maximum number of settings to return.
            cursor: Cursor token for pagination.
            sort: Sort parameter (e.g. ``'key'``, ``'-updated_at'``).
            query_params_items: Raw query parameter items for filtering.
            include_total: Whether to include total count.

        Returns:
            Paginated list of settings.

        """
        return await self.list_resources(
            model=RuntimeSetting,
            response_type=SettingsListResponse,
            response_type_converter=setting_to_read,
            limit=limit,
            cursor=cursor,
            sort=sort or "key",
            query_params_items=query_params_items,
            include_total=include_total,
        )

    async def get(self, key: str) -> RuntimeSettingRead:
        """Get a single setting by its dot-namespaced key.

        Args:
            key: Dot-namespaced setting key.

        Returns:
            The setting read schema.

        Raises:
            SettingNotFoundError: If the key does not exist.

        """
        setting = await self._get_by_key(key)
        return setting_to_read(setting)

    async def update(
        self,
        *,
        key: str,
        value: Any,  # noqa: ANN401
        expected_version: int | None = None,
    ) -> RuntimeSettingRead:
        """Update a setting's value with optional optimistic locking.

        Args:
            key: Dot-namespaced setting key.
            value: New value (native Python type).
            expected_version: Version the caller last read. When provided,
                the update is rejected if the stored version does not match.
                When omitted, the update is applied unconditionally.

        Returns:
            The updated setting.

        Raises:
            SettingNotFoundError: If the key does not exist.
            SettingValidationError: If the value fails validation.
            OptimisticLockError: If the version does not match.

        """
        snapshot: RuntimeSettingRead | None = None
        try:
            current = await self._get_by_key(key)
            snapshot = setting_to_read(current)
            result = await self._apply_update(key=key, value=value, expected_version=expected_version, current=current)
            await self.session.commit()
            AuditEventDispatcher.dispatch(
                SettingChangeEvent(
                    setting=key,
                    old_value=_format_setting_value(snapshot.effective_value),
                    new_value=_format_setting_value(value),
                    category=snapshot.category,
                    value_type=snapshot.value_type.value,
                    version=result.version,
                    resource_name=snapshot.name,
                )
            )
            await _invalidate_and_publish(key)
        except Exception as exc:
            await self.session.rollback()
            AuditEventDispatcher.dispatch(
                SettingChangeEvent(
                    setting=key,
                    old_value=_format_setting_value(snapshot.effective_value) if snapshot else None,
                    new_value=_format_setting_value(value),
                    category=snapshot.category if snapshot else None,
                    value_type=snapshot.value_type.value if snapshot else None,
                    version=snapshot.version if snapshot else 0,
                    resource_name=snapshot.name if snapshot else None,
                    error_type=type(exc).__name__,
                )
            )
            raise
        return result

    async def bulk_update(self, updates: list[SettingBulkUpdateItem]) -> list[RuntimeSettingRead]:
        """Update multiple settings atomically.

        All updates are validated and applied before committing. If any
        update fails validation or version check, no changes are persisted.

        Args:
            updates: List of setting updates with key, value, and expected_version.

        Returns:
            List of updated settings.

        Raises:
            SettingNotFoundError: If any key does not exist.
            SettingValidationError: If any value fails validation.
            OptimisticLockError: If any version does not match.

        """
        if not updates:
            return []
        try:
            fetched: dict[str, RuntimeSetting] = {}
            snapshots: dict[str, RuntimeSettingRead] = {}
            for item in updates:
                current = await self._get_by_key(item.key)
                fetched[item.key] = current
                snapshots[item.key] = setting_to_read(current)

            results = []
            for item in updates:
                result = await self._apply_update(
                    key=item.key,
                    value=item.value,
                    expected_version=item.expected_version,
                    current=fetched[item.key],
                )
                results.append(result)
            await self.session.commit()
            for item, result in zip(updates, results, strict=True):
                snap = snapshots[item.key]
                AuditEventDispatcher.dispatch(
                    SettingChangeEvent(
                        setting=item.key,
                        old_value=_format_setting_value(snap.effective_value),
                        new_value=_format_setting_value(item.value),
                        category=snap.category,
                        value_type=snap.value_type.value,
                        version=result.version,
                        resource_name=snap.name,
                    )
                )
            AuditEventDispatcher.dispatch(
                SettingBulkChangeEvent(
                    settings=[item.key for item in updates],
                    change_count=len(updates),
                )
            )
            for item in updates:
                await _invalidate_and_publish(item.key)
        except Exception as exc:
            await self.session.rollback()
            AuditEventDispatcher.dispatch(
                SettingBulkChangeEvent(
                    settings=[item.key for item in updates],
                    change_count=len(updates),
                    error_type=type(exc).__name__,
                )
            )
            raise
        return results

    async def _apply_update(
        self,
        *,
        key: str,
        value: Any,  # noqa: ANN401
        expected_version: int | None = None,
        current: RuntimeSetting | None = None,
    ) -> RuntimeSettingRead:
        """Validate and apply a setting update without committing.

        Used by both single and bulk operations. The caller is
        responsible for committing the transaction.

        When ``expected_version`` is provided, the update uses optimistic
        locking and raises ``OptimisticLockError`` on mismatch.  When
        omitted, the update is applied unconditionally (version is still
        incremented).

        Args:
            key: Dot-namespaced setting key.
            value: New value (native Python type).
            expected_version: Version the caller last read.
            current: Pre-fetched setting to avoid a redundant query.

        """
        if value is None:
            raise SettingValidationError(
                key, "value cannot be null; to reset, set value to the setting's default_value"
            )

        # Reject excessively large values to prevent DoS via payload size
        import json  # noqa: PLC0415

        try:
            if len(json.dumps(value)) > _MAX_SETTING_VALUE_BYTES:
                raise SettingValidationError(key, "value exceeds maximum size (64KB)")
        except (TypeError, ValueError) as exc:
            raise SettingValidationError(key, f"value is not JSON-serializable: {exc}") from exc

        if current is None:
            current = await self._get_by_key(key)

        validate_setting_value(
            key=key,
            value=value,
            value_type=current.value_type,
            validation_schema=current.validation_schema,
        )

        stmt = sa_update(RuntimeSetting).where(RuntimeSetting.key == key)  # type: ignore[arg-type]

        if expected_version is not None:
            # Optimistic locking: only update if version matches
            stmt = stmt.where(RuntimeSetting.version == expected_version)  # type: ignore[arg-type]
            stmt = stmt.values(
                value=value,
                version=expected_version + 1,
                updated_at=datetime.now(UTC),
            )
        else:
            # No locking: increment version unconditionally
            stmt = stmt.values(
                value=value,
                version=RuntimeSetting.version + 1,
                updated_at=datetime.now(UTC),
            )

        result = await self.session.exec(stmt)

        if result.rowcount == 0:
            if expected_version is not None:
                raise OptimisticLockError(key, current.version, expected_version)
            # rowcount=0 without locking means key not found (already checked above)
            raise SettingNotFoundError(key)

        # Expire the stale ORM instance so the next query returns fresh data
        # after the raw UPDATE that bypassed ORM change tracking.
        self.session.expire(current)
        updated = await self._get_by_key(key)
        logger.info("settings.updated", key=key, new_version=updated.version)
        return setting_to_read(updated)

    async def _get_by_key(self, key: str) -> RuntimeSetting:
        """Fetch a setting by key, raising SettingNotFoundError if missing."""
        result = await self.session.exec(select(RuntimeSetting).where(RuntimeSetting.key == key))
        setting = result.one_or_none()
        if setting is None:
            raise SettingNotFoundError(key)
        return setting
