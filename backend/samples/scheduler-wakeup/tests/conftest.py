from __future__ import annotations

import pytest
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from scheduler_wakeup_poc.models import SQLModel
from scheduler_wakeup_poc.store import AsyncExecutionStore


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--adapter", default="http")
    parser.addoption("--recovery", default="on")


@pytest.fixture
async def engine() -> AsyncEngine:
    value = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with value.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    yield value
    await value.dispose()


@pytest.fixture
def store(engine: AsyncEngine) -> AsyncExecutionStore:
    return AsyncExecutionStore(
        async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False),
        lease_duration=timedelta(seconds=0.05),
    )
