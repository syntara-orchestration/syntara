"""AO descriptive context comes from the execution record."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from syntara.workflows.workflow_engine.activities.ep import ep_dispatch_activity as dispatch


@pytest.mark.asyncio
@pytest.mark.parametrize("execution_exists", [True, False])
async def test_runtime_context_uses_persisted_execution_context(monkeypatch, *, execution_exists: bool) -> None:
    execution_id, project_id, workflow_id = uuid4(), uuid4(), uuid4()
    session = AsyncMock()
    rows = MagicMock()
    rows.first.return_value = (project_id, workflow_id) if execution_exists else None
    session.exec.return_value = rows
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(dispatch, "AsyncSessionLocal", factory)

    if not execution_exists:
        from temporalio.exceptions import ApplicationError

        with pytest.raises(ApplicationError, match="Execution does not exist"):
            await dispatch._work_runtime_context(execution_id)
        return
    runtime_context = await dispatch._work_runtime_context(execution_id)

    expected = {"execution_id": str(execution_id)}
    if execution_exists:
        expected.update(project_id=str(project_id), workflow_id=str(workflow_id))
    assert runtime_context == expected
    assert session.exec.await_args is not None
    query = session.exec.await_args.args[0].compile()
    assert execution_id in query.params.values()
