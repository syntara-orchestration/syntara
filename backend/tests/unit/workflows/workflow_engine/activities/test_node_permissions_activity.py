"""Unit tests for the node-permission runtime activities (ANSTRAT-1750, slice 4)."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine.activities.node_permissions_activity import (
    NODE_PERMISSION_ACTIVITIES,
    check_node_kind_enabled,
    recompute_denied_nodes,
    record_node_execute_denied,
)

_MODULE = "syntara.workflows.workflow_engine.activities.node_permissions_activity"

EXECUTION_ID = UUID("33333333-3333-4333-8333-333333333333")
PRINCIPAL_ID = UUID("11111111-1111-4111-8111-111111111111")


def _session_stub(execution: object | None = None, scalar: object | None = None) -> Any:  # noqa: ANN401
    """Async-context-manager session stub whose exec() returns a fixed row."""
    result = MagicMock()
    result.one_or_none.return_value = execution
    result.first.return_value = scalar
    session = MagicMock()
    session.exec = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


class TestCheckNodeKindEnabled:
    """The kill switch is re-read as a node starts (AD-19)."""

    @pytest.mark.asyncio
    async def test_enabled_kind_passes(self) -> None:
        with patch(f"{_MODULE}.get_disabled_node_kinds", AsyncMock(return_value=frozenset())):
            await check_node_kind_enabled("script")

    @pytest.mark.asyncio
    async def test_disabled_kind_fails_non_retryably(self) -> None:
        with (
            patch(f"{_MODULE}.get_disabled_node_kinds", AsyncMock(return_value=frozenset({"script"}))),
            pytest.raises(ApplicationError) as exc_info,
        ):
            await check_node_kind_enabled("script")

        error = exc_info.value
        assert error.non_retryable is True
        assert error.type == "NodeKindDisabledError"
        assert "node_kind_disabled" in str(error)
        assert error.details[0]["output"]["error"]["code"] == "node_kind_disabled"

    @pytest.mark.asyncio
    async def test_other_disabled_kinds_do_not_fail_this_node(self) -> None:
        with patch(f"{_MODULE}.get_disabled_node_kinds", AsyncMock(return_value=frozenset({"http_request"}))):
            await check_node_kind_enabled("script")


class TestRecordNodeExecuteDenied:
    """One audit event per denied node (AD-15)."""

    @pytest.mark.asyncio
    async def test_dispatches_event_with_workflow_id(self) -> None:
        workflow_id = uuid4()
        with (
            patch(f"{_MODULE}.AsyncSessionLocal", MagicMock(return_value=_session_stub(scalar=workflow_id))),
            patch(f"{_MODULE}.AuditEventDispatcher.dispatch") as dispatch,
        ):
            await record_node_execute_denied(
                str(EXECUTION_ID), "denied_node", "script", "no-scripts", str(PRINCIPAL_ID)
            )

        event = dispatch.call_args[0][0]
        assert event.execution_id == EXECUTION_ID
        assert event.node_id == "denied_node"
        assert event.kind == "script"
        assert event.denied_by == "no-scripts"
        assert event.principal_id == PRINCIPAL_ID
        assert event.workflow_id == workflow_id

    @pytest.mark.asyncio
    async def test_principal_is_optional(self) -> None:
        with (
            patch(f"{_MODULE}.AsyncSessionLocal", MagicMock(return_value=_session_stub(scalar=None))),
            patch(f"{_MODULE}.AuditEventDispatcher.dispatch") as dispatch,
        ):
            await record_node_execute_denied(str(EXECUTION_ID), "denied_node", "script", "no-scripts", None)

        assert dispatch.call_args[0][0].principal_id is None


class TestRecomputeDeniedNodes:
    """Resuming a suspended run replaces the denied set on the execution row (AD-12)."""

    @pytest.mark.asyncio
    async def test_persists_the_refreshed_set(self) -> None:
        execution = MagicMock()
        execution.project_id = uuid4()
        execution.workflow_version.workflow_definition = {"nodes": [{"id": "step", "type": "script"}]}
        execution.denied_nodes = [{"node_id": "step", "kind": "script", "denied_by": "stale"}]
        session = _session_stub(execution=execution)
        refreshed = [{"node_id": "step", "kind": "script", "denied_by": "fresh"}]

        with (
            patch(f"{_MODULE}.AsyncSessionLocal", MagicMock(return_value=session)),
            patch(f"{_MODULE}.get_node_authz_evaluator", MagicMock(return_value=MagicMock())),
            patch(f"{_MODULE}.compute_denied_nodes", AsyncMock(return_value=refreshed)),
        ):
            result = await recompute_denied_nodes(str(EXECUTION_ID), str(PRINCIPAL_ID))

        assert result == refreshed
        assert execution.denied_nodes == refreshed
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_result_clears_the_column(self) -> None:
        execution = MagicMock()
        execution.project_id = uuid4()
        execution.workflow_version.workflow_definition = {"nodes": []}
        session = _session_stub(execution=execution)

        with (
            patch(f"{_MODULE}.AsyncSessionLocal", MagicMock(return_value=session)),
            patch(f"{_MODULE}.get_node_authz_evaluator", MagicMock(return_value=MagicMock())),
            patch(f"{_MODULE}.compute_denied_nodes", AsyncMock(return_value=[])),
        ):
            assert await recompute_denied_nodes(str(EXECUTION_ID), str(PRINCIPAL_ID)) == []

        assert execution.denied_nodes is None

    @pytest.mark.asyncio
    async def test_missing_execution_returns_empty(self) -> None:
        session = _session_stub(execution=None)
        with patch(f"{_MODULE}.AsyncSessionLocal", MagicMock(return_value=session)):
            assert await recompute_denied_nodes(str(EXECUTION_ID), str(PRINCIPAL_ID)) == []
        session.commit.assert_not_awaited()


class TestRegistration:
    """All three activities are exported for worker registration."""

    def test_all_three_are_registered(self) -> None:
        names = {getattr(fn, "__temporal_activity_definition").name for fn in NODE_PERMISSION_ACTIVITIES}
        assert names == {"check_node_kind_enabled", "record_node_execute_denied", "recompute_denied_nodes"}
