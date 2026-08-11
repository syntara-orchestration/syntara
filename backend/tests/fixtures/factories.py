"""Factory fixtures shared across unit and integration tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest_asyncio

from tests.integration.helpers.workflow import ExecutionsFactory

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User
    from syntara.workflows.models import Workflow


@pytest_asyncio.fixture
async def executions_factory(
    test_db_session: AsyncSession, test_workflow: Workflow, test_user: User
) -> ExecutionsFactory:
    """Create a factory fixture for multiple test executions with configurable properties."""
    return ExecutionsFactory(test_db_session, test_workflow, test_user)
