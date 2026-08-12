"""Unit tests for SettingsService.

Tests cover:
- get: returns setting, raises SettingNotFoundError
- list_settings: returns paginated response
- update: stores value, increments version, validates, optimistic locking
- update edge cases: None clears override, 0/False/"" are valid
- bulk_update: updates multiple settings
- concurrent update: optimistic locking under asyncio.gather
- audit event dispatch: SettingChangeEvent / SettingBulkChangeEvent
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.settings.audit.settings import SettingBulkChangeEvent, SettingChangeEvent
from syntara.settings.exceptions import OptimisticLockError, SettingNotFoundError, SettingValidationError
from syntara.settings.models.runtime_setting import RuntimeSetting, SettingCategory, SettingValueType
from syntara.settings.services.settings_service import SettingsService

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncEngine


def _make_user() -> User:
    """Create a test user for BaseService."""
    return User(
        id=uuid4(),
        username="test-admin",
        email="admin@test.com",
        first_name="Test",
        last_name="Admin",
        is_active=True,
    )


async def _insert_setting(
    session: AsyncSession,
    *,
    key: str = "test.setting",
    category: SettingCategory = SettingCategory.CONTEXT_MANAGER,
    value_type: SettingValueType = SettingValueType.INTEGER,
    default_value: object = 100,
    value: object = None,
    validation_schema: dict[str, object] | None = None,
    group: str | None = None,
) -> RuntimeSetting:
    """Insert a RuntimeSetting into the test DB."""
    setting = RuntimeSetting(
        id=uuid4(),
        name=f"Test {key}",
        key=key,
        category=category,
        value_type=value_type,
        default_value=default_value,
        value=value,
        validation_schema=validation_schema,
        group=group,
    )
    session.add(setting)
    await session.commit()
    await session.refresh(setting)
    return setting


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_returns_setting(test_db_session: AsyncSession) -> None:
    """get() returns the setting read schema for an existing key."""
    await _insert_setting(test_db_session, key="test.get.existing")
    service = SettingsService(test_db_session, _make_user())

    result = await service.get("test.get.existing")

    assert result.key == "test.get.existing"
    assert result.effective_value == 100


@pytest.mark.asyncio
async def test_get_raises_not_found(test_db_session: AsyncSession) -> None:
    """get() raises SettingNotFoundError for missing key."""
    service = SettingsService(test_db_session, _make_user())

    with pytest.raises(SettingNotFoundError):
        await service.get("test.does.not.exist")


@pytest.mark.asyncio
async def test_get_effective_value_uses_override(test_db_session: AsyncSession) -> None:
    """get() returns value as effective_value when value is set."""
    await _insert_setting(test_db_session, key="test.get.override", value=999, default_value=100)
    service = SettingsService(test_db_session, _make_user())

    result = await service.get("test.get.override")

    assert result.effective_value == 999
    assert result.value == 999
    assert result.default_value == 100


# ---------------------------------------------------------------------------
# list_categories
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_categories_returns_seeded_categories(test_db_session: AsyncSession) -> None:
    """list_categories() returns categories from the database."""
    from syntara.settings.seeder import seed_settings

    async def _session_factory() -> AsyncGenerator:  # type: ignore[type-arg]
        yield test_db_session

    await seed_settings(contextlib.asynccontextmanager(_session_factory))
    service = SettingsService(test_db_session, _make_user())

    result = await service.list_categories()

    assert len(result.resources) > 0
    cm_cat = next((c for c in result.resources if c.slug == "context_manager"), None)
    assert cm_cat is not None
    assert cm_cat.name == "Context Manager"
    assert cm_cat.description is not None
    assert cm_cat.display_order == 20


@pytest.mark.asyncio
async def test_list_categories_includes_group_names(test_db_session: AsyncSession) -> None:
    """list_categories() includes group names from settings in each category."""
    await _insert_setting(test_db_session, key="test.cat.a", group="Group A")
    await _insert_setting(test_db_session, key="test.cat.b", group="Group B")
    await _insert_setting(test_db_session, key="test.cat.c", group=None)
    service = SettingsService(test_db_session, _make_user())

    result = await service.list_categories()

    cm_cat = next((c for c in result.resources if c.slug == "context_manager"), None)
    assert cm_cat is not None
    assert "Group A" in cm_cat.group_names
    assert "Group B" in cm_cat.group_names


@pytest.mark.asyncio
async def test_list_categories_sorts_group_names(test_db_session: AsyncSession) -> None:
    """list_categories() returns group names in sorted order."""
    await _insert_setting(test_db_session, key="test.sort.z", group="Zulu")
    await _insert_setting(test_db_session, key="test.sort.a", group="Alpha")
    service = SettingsService(test_db_session, _make_user())

    result = await service.list_categories()

    cm_cat = next((c for c in result.resources if c.slug == "context_manager"), None)
    assert cm_cat is not None
    zulu_idx = cm_cat.group_names.index("Zulu")
    alpha_idx = cm_cat.group_names.index("Alpha")
    assert alpha_idx < zulu_idx


@pytest.mark.asyncio
async def test_list_categories_ordered_by_display_order(test_db_session: AsyncSession) -> None:
    """list_categories() returns categories ordered by display_order."""
    from syntara.settings.seeder import seed_settings

    async def _session_factory() -> AsyncGenerator:  # type: ignore[type-arg]
        yield test_db_session

    await seed_settings(contextlib.asynccontextmanager(_session_factory))
    service = SettingsService(test_db_session, _make_user())

    result = await service.list_categories()

    orders = [c.display_order for c in result.resources]
    assert orders == sorted(orders)


# ---------------------------------------------------------------------------
# list_settings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_returns_seeded_settings(test_db_session: AsyncSession) -> None:
    """list_settings() returns settings from the catalog after seeding."""
    from syntara.settings.seeder import seed_settings

    async def _session_factory() -> AsyncGenerator:  # type: ignore[type-arg]
        yield test_db_session

    await seed_settings(contextlib.asynccontextmanager(_session_factory))
    service = SettingsService(test_db_session, _make_user())

    result = await service.list_settings(limit=100)

    assert len(result.resources) > 0
    assert all(hasattr(r, "effective_value") for r in result.resources)


@pytest.mark.asyncio
async def test_list_filters_by_category(test_db_session: AsyncSession) -> None:
    """list_settings() filters by category query parameter."""
    await _insert_setting(test_db_session, key="cat_a.setting1", category=SettingCategory.CONTEXT_MANAGER)
    await _insert_setting(test_db_session, key="cat_b.setting1", category=SettingCategory.CONTEXT_MANAGER)
    await _insert_setting(test_db_session, key="other.setting1", category=SettingCategory.SYSTEM)
    service = SettingsService(test_db_session, _make_user())

    result = await service.list_settings(
        limit=100,
        query_params_items=[("category", "context_manager")],
    )

    assert all(r.category == "context_manager" for r in result.resources)
    keys = {r.key for r in result.resources}
    assert "cat_a.setting1" in keys
    assert "cat_b.setting1" in keys
    assert "other.setting1" not in keys


@pytest.mark.asyncio
async def test_list_filters_by_group(test_db_session: AsyncSession) -> None:
    """list_settings() filters by group query parameter."""
    await _insert_setting(test_db_session, key="grp.a", group="Token limits")
    await _insert_setting(test_db_session, key="grp.b", group="Token limits")
    await _insert_setting(test_db_session, key="grp.c", group="Performance")
    service = SettingsService(test_db_session, _make_user())

    result = await service.list_settings(
        limit=100,
        query_params_items=[("group", "Token limits")],
    )

    assert all(r.group == "Token limits" for r in result.resources)
    keys = {r.key for r in result.resources}
    assert "grp.a" in keys
    assert "grp.b" in keys
    assert "grp.c" not in keys


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_stores_value(test_db_session: AsyncSession) -> None:
    """update() persists the new value and increments version."""
    await _insert_setting(test_db_session, key="test.update.store", default_value=100)
    service = SettingsService(test_db_session, _make_user())

    result = await service.update(key="test.update.store", value=200, expected_version=1)

    assert result.value == 200
    assert result.effective_value == 200
    assert result.version == 2


@pytest.mark.asyncio
async def test_update_raises_on_version_mismatch(test_db_session: AsyncSession) -> None:
    """update() raises OptimisticLockError when version doesn't match."""
    await _insert_setting(test_db_session, key="test.update.conflict")
    service = SettingsService(test_db_session, _make_user())

    with pytest.raises(OptimisticLockError) as exc_info:
        await service.update(key="test.update.conflict", value=999, expected_version=99)

    assert exc_info.value.current_version == 1
    assert exc_info.value.submitted_version == 99


@pytest.mark.asyncio
async def test_update_raises_for_missing_key(test_db_session: AsyncSession) -> None:
    """update() raises SettingNotFoundError for unknown key."""
    service = SettingsService(test_db_session, _make_user())

    with pytest.raises(SettingNotFoundError):
        await service.update(key="test.missing", value=1, expected_version=1)


@pytest.mark.asyncio
async def test_update_rejects_wrong_type(test_db_session: AsyncSession) -> None:
    """update() raises SettingValidationError for type mismatch."""
    await _insert_setting(
        test_db_session,
        key="test.update.wrongtype",
        value_type=SettingValueType.INTEGER,
    )
    service = SettingsService(test_db_session, _make_user())

    with pytest.raises(SettingValidationError):
        await service.update(key="test.update.wrongtype", value="not_a_number", expected_version=1)


@pytest.mark.asyncio
async def test_update_rejects_value_below_min(test_db_session: AsyncSession) -> None:
    """update() raises SettingValidationError when value is below min."""
    await _insert_setting(
        test_db_session,
        key="test.update.belowmin",
        value_type=SettingValueType.INTEGER,
        validation_schema={"min": 1},
    )
    service = SettingsService(test_db_session, _make_user())

    with pytest.raises(SettingValidationError):
        await service.update(key="test.update.belowmin", value=0, expected_version=1)


@pytest.mark.asyncio
async def test_update_value_to_none_is_rejected(test_db_session: AsyncSession) -> None:
    """update(value=None) raises SettingValidationError."""
    await _insert_setting(test_db_session, key="test.update.none", value=999, default_value=100)
    service = SettingsService(test_db_session, _make_user())

    with pytest.raises(SettingValidationError, match="cannot be null"):
        await service.update(key="test.update.none", value=None, expected_version=1)


@pytest.mark.asyncio
async def test_update_value_to_zero(test_db_session: AsyncSession) -> None:
    """update(value=0) stores zero, not None."""
    await _insert_setting(
        test_db_session,
        key="test.update.zero",
        value_type=SettingValueType.INTEGER,
        validation_schema={"min": 0},
    )
    service = SettingsService(test_db_session, _make_user())

    result = await service.update(key="test.update.zero", value=0, expected_version=1)

    assert result.value == 0
    assert result.effective_value == 0


@pytest.mark.asyncio
async def test_update_value_to_false(test_db_session: AsyncSession) -> None:
    """update(value=False) stores False, not None."""
    await _insert_setting(
        test_db_session,
        key="test.update.false",
        value_type=SettingValueType.BOOLEAN,
        default_value=True,
    )
    service = SettingsService(test_db_session, _make_user())

    result = await service.update(key="test.update.false", value=False, expected_version=1)

    assert result.value is False
    assert result.effective_value is False


@pytest.mark.asyncio
async def test_update_value_to_empty_string(test_db_session: AsyncSession) -> None:
    """update(value='') stores empty string, not None."""
    await _insert_setting(
        test_db_session,
        key="test.update.empty",
        value_type=SettingValueType.STRING,
        default_value="hello",
    )
    service = SettingsService(test_db_session, _make_user())

    result = await service.update(key="test.update.empty", value="", expected_version=1)

    assert result.value == ""
    assert result.effective_value == ""


# ---------------------------------------------------------------------------
# bulk_update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_update_multiple_settings(test_db_session: AsyncSession) -> None:
    """bulk_update() updates multiple settings."""
    from syntara.settings.models.api_models import SettingBulkUpdateItem

    await _insert_setting(test_db_session, key="test.bulk.a", default_value=1)
    await _insert_setting(test_db_session, key="test.bulk.b", default_value=2)
    service = SettingsService(test_db_session, _make_user())

    results = await service.bulk_update(
        [
            SettingBulkUpdateItem(key="test.bulk.a", value=10, expected_version=1),
            SettingBulkUpdateItem(key="test.bulk.b", value=20, expected_version=1),
        ]
    )

    assert len(results) == 2
    assert results[0].value == 10
    assert results[1].value == 20


@pytest.mark.asyncio
async def test_bulk_update_rolls_back_on_failure(test_db_session: AsyncSession) -> None:
    """bulk_update() does not persist earlier updates when a later one fails."""
    from syntara.settings.models.api_models import SettingBulkUpdateItem

    await _insert_setting(test_db_session, key="test.bulkfail.a", value=5, default_value=1)
    await _insert_setting(test_db_session, key="test.bulkfail.b", value=6, default_value=2)
    service = SettingsService(test_db_session, _make_user())

    with pytest.raises(OptimisticLockError):
        await service.bulk_update(
            [
                SettingBulkUpdateItem(key="test.bulkfail.a", value=10, expected_version=1),
                SettingBulkUpdateItem(key="test.bulkfail.b", value=20, expected_version=99),  # wrong version
            ]
        )

    # Verify first setting was NOT persisted (atomic rollback)
    result = await service.get("test.bulkfail.a")
    assert result.value == 5, "Value should revert to pre-update state"
    assert result.version == 1


@pytest.mark.asyncio
async def test_update_rejects_oversized_value(test_db_session: AsyncSession) -> None:
    """update() raises SettingValidationError for values exceeding 64KB."""
    await _insert_setting(
        test_db_session,
        key="test.update.oversize",
        value_type=SettingValueType.STRING,
        default_value="small",
    )
    service = SettingsService(test_db_session, _make_user())

    huge_value = "x" * 70000  # > 64KB
    with pytest.raises(SettingValidationError, match="maximum size"):
        await service.update(key="test.update.oversize", value=huge_value, expected_version=1)


@pytest.mark.asyncio
async def test_update_rejects_non_serializable_value(test_db_session: AsyncSession) -> None:
    """update() raises SettingValidationError for non-JSON-serializable values."""
    await _insert_setting(
        test_db_session,
        key="test.update.nonserial",
        value_type=SettingValueType.STRING,
        default_value="ok",
    )
    service = SettingsService(test_db_session, _make_user())

    with pytest.raises(SettingValidationError, match="not JSON-serializable"):
        await service.update(key="test.update.nonserial", value=object(), expected_version=1)


# ---------------------------------------------------------------------------
# Concurrent optimistic locking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_update_only_one_succeeds(test_db_engine: AsyncEngine) -> None:
    """Two concurrent updates with the same expected_version: exactly one wins."""
    session_factory = async_sessionmaker(test_db_engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as setup_session:
        await _insert_setting(setup_session, key="test.concurrent.lock")
        await setup_session.commit()

    async def attempt_update() -> object:
        async with session_factory() as session:
            service = SettingsService(session, _make_user())
            return await service.update(key="test.concurrent.lock", value=999, expected_version=1)

    results = await asyncio.gather(attempt_update(), attempt_update(), return_exceptions=True)

    successes = [r for r in results if not isinstance(r, Exception)]
    lock_errors = [r for r in results if isinstance(r, OptimisticLockError)]

    assert len(successes) == 1, "Exactly one concurrent update should succeed"
    assert len(lock_errors) == 1, "Exactly one should raise OptimisticLockError"
    assert lock_errors[0].submitted_version == 1


# ---------------------------------------------------------------------------
# Audit event dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_dispatches_setting_change_event(test_db_session: AsyncSession) -> None:
    """update() dispatches a SettingChangeEvent with correct old/new values."""
    await _insert_setting(test_db_session, key="test.audit.single", value=42, default_value=100)
    user = _make_user()
    service = SettingsService(test_db_session, user)

    with patch("syntara.settings.services.settings_service.AuditEventDispatcher") as mock_dispatcher:
        await service.update(key="test.audit.single", value=99, expected_version=1)

    mock_dispatcher.dispatch.assert_called_once()
    event = mock_dispatcher.dispatch.call_args[0][0]
    assert isinstance(event, SettingChangeEvent)
    assert event.setting == "test.audit.single"
    assert event.old_value == "42"
    assert event.new_value == "99"
    assert event.category == "context_manager"
    assert event.value_type == "integer"
    assert event.version == 2


@pytest.mark.asyncio
async def test_update_uses_effective_value_for_old_value(test_db_session: AsyncSession) -> None:
    """update() uses effective value (default) as old_value when value is None."""
    await _insert_setting(test_db_session, key="test.audit.default", value=None, default_value=100)
    service = SettingsService(test_db_session, _make_user())

    with patch("syntara.settings.services.settings_service.AuditEventDispatcher") as mock_dispatcher:
        await service.update(key="test.audit.default", value=200, expected_version=1)

    event = mock_dispatcher.dispatch.call_args[0][0]
    assert isinstance(event, SettingChangeEvent)
    assert event.old_value == "100", "old_value should fall back to default_value when value is None"
    assert event.new_value == "200"


@pytest.mark.asyncio
async def test_update_dispatches_failure_event(test_db_session: AsyncSession) -> None:
    """update() dispatches a SettingChangeEvent with error_type on failure."""
    await _insert_setting(test_db_session, key="test.audit.fail")
    service = SettingsService(test_db_session, _make_user())

    with (
        patch("syntara.settings.services.settings_service.AuditEventDispatcher") as mock_dispatcher,
        pytest.raises(OptimisticLockError),
    ):
        await service.update(key="test.audit.fail", value=999, expected_version=99)

    mock_dispatcher.dispatch.assert_called_once()
    event = mock_dispatcher.dispatch.call_args[0][0]
    assert isinstance(event, SettingChangeEvent)
    assert event.setting == "test.audit.fail"
    assert event.error_type == "OptimisticLockError"
    assert event.new_value == "999"
    assert event.old_value is not None


@pytest.mark.asyncio
async def test_bulk_update_dispatches_change_and_bulk_events(test_db_session: AsyncSession) -> None:
    """bulk_update() dispatches N SettingChangeEvents + 1 SettingBulkChangeEvent."""
    from syntara.settings.models.api_models import SettingBulkUpdateItem

    await _insert_setting(test_db_session, key="test.audit.bulk.a", default_value=1)
    await _insert_setting(test_db_session, key="test.audit.bulk.b", default_value=2)
    user = _make_user()
    service = SettingsService(test_db_session, user)

    with patch("syntara.settings.services.settings_service.AuditEventDispatcher") as mock_dispatcher:
        await service.bulk_update(
            [
                SettingBulkUpdateItem(key="test.audit.bulk.a", value=10, expected_version=1),
                SettingBulkUpdateItem(key="test.audit.bulk.b", value=20, expected_version=1),
            ]
        )

    assert mock_dispatcher.dispatch.call_count == 3

    events = [call[0][0] for call in mock_dispatcher.dispatch.call_args_list]
    change_events = [e for e in events if isinstance(e, SettingChangeEvent)]
    bulk_events = [e for e in events if isinstance(e, SettingBulkChangeEvent)]

    assert len(change_events) == 2
    assert len(bulk_events) == 1
    assert {e.setting for e in change_events} == {"test.audit.bulk.a", "test.audit.bulk.b"}
    assert bulk_events[0].settings == ["test.audit.bulk.a", "test.audit.bulk.b"]
    assert bulk_events[0].change_count == 2


@pytest.mark.asyncio
async def test_bulk_update_dispatches_failure_event(test_db_session: AsyncSession) -> None:
    """bulk_update() dispatches a SettingBulkChangeEvent with error_type on failure."""
    from syntara.settings.models.api_models import SettingBulkUpdateItem

    await _insert_setting(test_db_session, key="test.audit.bulkfail.a", default_value=1)
    await _insert_setting(test_db_session, key="test.audit.bulkfail.b", default_value=2)
    service = SettingsService(test_db_session, _make_user())

    with (
        patch("syntara.settings.services.settings_service.AuditEventDispatcher") as mock_dispatcher,
        pytest.raises(OptimisticLockError),
    ):
        await service.bulk_update(
            [
                SettingBulkUpdateItem(key="test.audit.bulkfail.a", value=10, expected_version=1),
                SettingBulkUpdateItem(key="test.audit.bulkfail.b", value=20, expected_version=99),
            ]
        )

    mock_dispatcher.dispatch.assert_called_once()
    event = mock_dispatcher.dispatch.call_args[0][0]
    assert isinstance(event, SettingBulkChangeEvent)
    assert event.settings == ["test.audit.bulkfail.a", "test.audit.bulkfail.b"]
    assert event.error_type == "OptimisticLockError"
