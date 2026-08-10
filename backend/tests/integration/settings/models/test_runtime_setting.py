"""Unit tests for the RuntimeSetting SQLModel.

Tests cover:
- Creation with required fields and correct defaults
- NamedResource-inherited fields (id, created_at, updated_at, labels, name, description)
- JSONB value and default_value columns accept native Python types
- Per-setting cache_ttl_seconds (None by default)
- Unique constraint on key
- Enum columns for category and value_type
- version starts at 1
- requires_restart defaults to False
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from syntara.settings.models.runtime_setting import RuntimeSetting, SettingCategory, SettingValueType

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.mark.asyncio
async def test_create_runtime_setting_with_required_fields(
    test_db_session: AsyncSession,
) -> None:
    """RuntimeSetting can be created with only required fields; defaults are correct."""
    setting = RuntimeSetting(
        id=uuid4(),
        name="AI Model Name",
        key="test.ai.model_name",
        category=SettingCategory.AI_LLM,
        value_type=SettingValueType.STRING,
    )
    test_db_session.add(setting)
    await test_db_session.commit()

    assert setting.id is not None
    assert setting.name == "AI Model Name"
    assert setting.key == "test.ai.model_name"
    assert setting.category == SettingCategory.AI_LLM
    assert setting.value_type == SettingValueType.STRING
    assert setting.description is None
    assert setting.labels == {}
    assert setting.created_at is not None
    assert setting.updated_at is not None
    assert setting.value is None
    assert setting.default_value is None
    assert setting.version == 1
    assert setting.requires_restart is False
    assert setting.cache_ttl_seconds is None
    assert setting.validation_schema is None


@pytest.mark.asyncio
async def test_create_runtime_setting_with_all_fields(
    test_db_session: AsyncSession,
) -> None:
    """RuntimeSetting stores all fields correctly, including JSONB and optional fields."""
    setting = RuntimeSetting(
        id=uuid4(),
        name="Sampling Temperature",
        description="Controls randomness of AI output",
        key="test.ai.sampling_temperature",
        category=SettingCategory.AI_LLM,
        value_type=SettingValueType.FLOAT,
        default_value=0.7,
        value=0.9,
        requires_restart=False,
        cache_ttl_seconds=120,
        validation_schema={"min": 0.0, "max": 1.0},
        labels={"env": "prod"},
    )
    test_db_session.add(setting)
    await test_db_session.commit()

    assert setting.description == "Controls randomness of AI output"
    assert setting.default_value == 0.7
    assert setting.value == 0.9
    assert setting.cache_ttl_seconds == 120
    assert setting.validation_schema == {"min": 0.0, "max": 1.0}
    assert setting.labels == {"env": "prod"}


@pytest.mark.asyncio
async def test_jsonb_value_stores_native_types(
    test_db_session: AsyncSession,
) -> None:
    """Value and default_value columns store native Python types (int, bool, list) without string conversion."""
    setting = RuntimeSetting(
        id=uuid4(),
        name="Max Retries",
        key="test.workflow.max_retry_attempts",
        category=SettingCategory.WORKFLOW_EXECUTION,
        value_type=SettingValueType.INTEGER,
        default_value=3,
        value=5,
    )
    test_db_session.add(setting)
    await test_db_session.commit()

    result = await test_db_session.exec(
        select(RuntimeSetting).where(RuntimeSetting.key == "test.workflow.max_retry_attempts")
    )
    fetched = result.one()
    assert fetched.default_value == 3
    assert fetched.value == 5
    assert isinstance(fetched.default_value, int)
    assert isinstance(fetched.value, int)


@pytest.mark.asyncio
async def test_jsonb_value_stores_boolean(
    test_db_session: AsyncSession,
) -> None:
    """Boolean values survive the JSONB round-trip as bool, not int."""
    setting = RuntimeSetting(
        id=uuid4(),
        name="Feature Flag",
        key="test.system.feature_enabled",
        category=SettingCategory.SYSTEM,
        value_type=SettingValueType.BOOLEAN,
        default_value=False,
        value=True,
    )
    test_db_session.add(setting)
    await test_db_session.commit()

    result = await test_db_session.exec(
        select(RuntimeSetting).where(RuntimeSetting.key == "test.system.feature_enabled")
    )
    fetched = result.one()
    assert fetched.value is True
    assert fetched.default_value is False


@pytest.mark.asyncio
async def test_key_unique_constraint(
    test_db_session: AsyncSession,
) -> None:
    """Two RuntimeSettings with the same key cannot be inserted."""
    setting_a = RuntimeSetting(
        id=uuid4(),
        name="Model A",
        key="test.ai.model_name",
        category=SettingCategory.AI_LLM,
        value_type=SettingValueType.STRING,
    )
    setting_b = RuntimeSetting(
        id=uuid4(),
        name="Model B",
        key="test.ai.model_name",
        category=SettingCategory.AI_LLM,
        value_type=SettingValueType.STRING,
    )
    test_db_session.add(setting_a)
    await test_db_session.commit()

    test_db_session.add(setting_b)
    with pytest.raises(IntegrityError):
        await test_db_session.commit()


@pytest.mark.asyncio
async def test_version_starts_at_one(
    test_db_session: AsyncSession,
) -> None:
    """Newly created settings have version=1."""
    setting = RuntimeSetting(
        id=uuid4(),
        name="Timeout",
        key="test.workflow.execution_timeout_seconds",
        category=SettingCategory.WORKFLOW_EXECUTION,
        value_type=SettingValueType.INTEGER,
        default_value=3600,
    )
    test_db_session.add(setting)
    await test_db_session.commit()

    assert setting.version == 1


@pytest.mark.asyncio
async def test_all_setting_categories_accepted(
    test_db_session: AsyncSession,
) -> None:
    """All SettingCategory enum values are accepted by the database."""
    for i, category in enumerate(SettingCategory):
        setting = RuntimeSetting(
            id=uuid4(),
            name=f"Setting {i}",
            key=f"test.category_{i}",
            category=category,
            value_type=SettingValueType.STRING,
        )
        test_db_session.add(setting)
    await test_db_session.commit()


@pytest.mark.asyncio
async def test_all_value_types_accepted(
    test_db_session: AsyncSession,
) -> None:
    """All SettingValueType enum values are accepted by the database."""
    for i, value_type in enumerate(SettingValueType):
        setting = RuntimeSetting(
            id=uuid4(),
            name=f"Setting {i}",
            key=f"test.type_{i}",
            category=SettingCategory.SYSTEM,
            value_type=value_type,
        )
        test_db_session.add(setting)
    await test_db_session.commit()


@pytest.mark.asyncio
async def test_requires_restart_flag(
    test_db_session: AsyncSession,
) -> None:
    """requires_restart=True is stored and retrieved correctly."""
    setting = RuntimeSetting(
        id=uuid4(),
        name="Max Concurrent Executions",
        key="test.workflow.max_concurrent_executions",
        category=SettingCategory.WORKFLOW_EXECUTION,
        value_type=SettingValueType.INTEGER,
        default_value=10,
        requires_restart=True,
    )
    test_db_session.add(setting)
    await test_db_session.commit()

    result = await test_db_session.exec(
        select(RuntimeSetting).where(RuntimeSetting.key == "test.workflow.max_concurrent_executions")
    )
    fetched = result.one()
    assert fetched.requires_restart is True
