"""Tests for execute_internal_activity."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch
from uuid import uuid4

import pytest
from temporalio.exceptions import ApplicationError

from syntara.core.config.base import Settings
from syntara.core.models.principal import service_principal_id
from syntara.workflows.workflow_engine.activities.internal_activity import (
    execute_internal_activity,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Generator
    from contextlib import AbstractAsyncContextManager

_SERVICE_IDENTITY = "worker.ao.svc"


@pytest.fixture(autouse=True)
def _mock_service_identity() -> Generator[None, None, None]:
    """Provide a service_identity for tests running without S2S TLS certificates.

    Same pattern as tests/unit/workflows/activities/conftest.py — that
    conftest doesn't cover this sibling directory
    (workflow_engine/activities/), so it's reproduced locally here.
    """
    with patch.object(Settings, "service_identity", new_callable=PropertyMock, return_value=_SERVICE_IDENTITY):
        yield


class TestExecuteInternalActivity:
    """Tests for the internal_activity Temporal activity."""

    @pytest.mark.anyio
    async def test_missing_activity_key_raises(self) -> None:
        with pytest.raises(ApplicationError, match="requires 'activity' in config"):
            await execute_internal_activity({}, None)

    @pytest.mark.anyio
    async def test_unknown_activity_raises(self) -> None:
        with pytest.raises(ApplicationError, match="Unknown internal activity: bogus"):
            await execute_internal_activity({"activity": "bogus"}, None)

    @pytest.mark.anyio
    async def test_document_conversion_missing_file_id_raises(self) -> None:
        with pytest.raises(ApplicationError, match="requires 'file_id'"):
            await execute_internal_activity({"activity": "document_conversion", "input": {}}, None)

    @pytest.mark.anyio
    async def test_invocation_execution_missing_invocation_id_raises(self) -> None:
        with pytest.raises(ApplicationError, match="requires 'invocation_id'"):
            await execute_internal_activity({"activity": "invocation_execution", "input": {}}, None)

    @pytest.mark.anyio
    async def test_document_conversion_dispatches(self) -> None:
        file_id = uuid4()
        mock_handler = AsyncMock(return_value={"output": {"status": "SUCCESS"}})

        with patch.dict(
            "syntara.workflows.workflow_engine.activities.internal_activity._DISPATCH",
            {"document_conversion": mock_handler},
        ):
            result = await execute_internal_activity(
                {"activity": "document_conversion", "input": {"file_id": str(file_id)}},
                None,
            )

        assert result == {"output": {"status": "SUCCESS"}}
        mock_handler.assert_awaited_once_with({"file_id": str(file_id)})

    @pytest.mark.anyio
    async def test_invocation_execution_dispatches(self) -> None:
        inv_id = uuid4()
        mock_handler = AsyncMock(return_value={"output": {"status": "completed"}})

        with patch.dict(
            "syntara.workflows.workflow_engine.activities.internal_activity._DISPATCH",
            {"invocation_execution": mock_handler},
        ):
            result = await execute_internal_activity(
                {"activity": "invocation_execution", "input": {"invocation_id": str(inv_id)}},
                None,
            )

        assert result == {"output": {"status": "completed"}}
        mock_handler.assert_awaited_once_with({"invocation_id": str(inv_id)})


def _session_factory(session: AsyncMock) -> Callable[[], AbstractAsyncContextManager[AsyncMock]]:
    """Build an ``AsyncSessionLocal``-shaped factory that always yields ``session``.

    ``_run_integration_health_check`` does ``async with AsyncSessionLocal() as session:``
    (and again per-integration for isolation) — this mirrors the existing
    ``@asynccontextmanager``-factory pattern used elsewhere in the test suite
    (e.g. ``test_invocation_executor_token_update.py``) instead of trying to make
    a bare ``AsyncMock`` behave like an async context manager factory.
    """

    @asynccontextmanager
    async def _factory() -> AsyncGenerator[AsyncMock, None]:
        yield session

    return _factory


class TestRunIntegrationHealthCheck:
    """Tests for _run_integration_health_check activity."""

    @pytest.mark.anyio
    async def test_batch_mode_processes_all_stale_integrations(self) -> None:
        """Batch mode: query returns N stale ids, each is checked in its own session."""
        id1, id2 = uuid4(), uuid4()

        batch_exec_result = MagicMock()
        batch_exec_result.all.return_value = [id1, id2]

        session = AsyncMock()
        # The batch query runs once on the outer session. Per-integration
        # sessions no longer issue any query of their own — the actor is now
        # a synthetic service principal (F3 fix), not a DB-looked-up admin
        # row — so no further .exec() calls are expected.
        session.exec = AsyncMock(return_value=batch_exec_result)

        validate_result = MagicMock(success=True, error=None)
        mock_service = MagicMock()
        mock_service.validate_integration = AsyncMock(return_value=validate_result)

        mock_settings = MagicMock()
        mock_settings.get = AsyncMock(return_value=300)

        with (
            patch("syntara.integrations.services.health_check.AsyncSessionLocal", _session_factory(session)),
            patch("syntara.integrations.services.health_check.get_runtime_settings", return_value=mock_settings),
            patch("syntara.integrations.services.health_check.create_secret_service", return_value=MagicMock()),
            patch(
                "syntara.integrations.services.health_check.IntegrationService",
                return_value=mock_service,
            ),
        ):
            result = await execute_internal_activity(
                {"activity": "integration_health_check", "input": {"batch": True}},
                None,
            )

        assert result["output"]["checked"] == 2
        assert result["output"]["available"] == 2
        assert result["output"]["error"] == 0
        assert mock_service.validate_integration.await_count == 2

    @pytest.mark.anyio
    async def test_batch_mode_empty_input(self) -> None:
        """Empty input {} works for batch mode."""
        batch_exec_result = MagicMock()
        batch_exec_result.all.return_value = []

        session = AsyncMock()
        session.exec = AsyncMock(return_value=batch_exec_result)

        mock_settings = MagicMock()
        mock_settings.get = AsyncMock(return_value=300)

        with (
            patch("syntara.integrations.services.health_check.AsyncSessionLocal", _session_factory(session)),
            patch("syntara.integrations.services.health_check.get_runtime_settings", return_value=mock_settings),
        ):
            result = await execute_internal_activity(
                {"activity": "integration_health_check", "input": {}},
                None,
            )

        assert result == {"output": {"checked": 0, "available": 0, "error": 0, "results": []}}

    @pytest.mark.anyio
    async def test_uses_service_principal_not_admin_lookup(self) -> None:
        """IntegrationService is constructed with a service principal, not a DB admin lookup."""
        integration_id = uuid4()

        batch_exec_result = MagicMock()
        batch_exec_result.all.return_value = [integration_id]

        session = AsyncMock()
        session.exec = AsyncMock(return_value=batch_exec_result)

        validate_result = MagicMock(success=True, error=None)
        mock_service = MagicMock()
        mock_service.validate_integration = AsyncMock(return_value=validate_result)
        mock_integration_service_cls = MagicMock(return_value=mock_service)

        mock_settings = MagicMock()
        mock_settings.get = AsyncMock(return_value=300)

        with (
            patch("syntara.integrations.services.health_check.AsyncSessionLocal", _session_factory(session)),
            patch("syntara.integrations.services.health_check.get_runtime_settings", return_value=mock_settings),
            patch("syntara.integrations.services.health_check.create_secret_service", return_value=MagicMock()),
            patch(
                "syntara.integrations.services.health_check.IntegrationService",
                mock_integration_service_cls,
            ),
        ):
            await execute_internal_activity(
                {"activity": "integration_health_check", "input": {}},
                None,
            )

        mock_integration_service_cls.assert_called()
        actor = mock_integration_service_cls.call_args.args[1]
        assert actor.id == service_principal_id(_SERVICE_IDENTITY)
        assert actor.username == _SERVICE_IDENTITY

    @pytest.mark.anyio
    async def test_validation_failure_surfaces_adapter_error(self) -> None:
        """A clean adapter-reported failure (e.g. connection refused) is passed through."""
        integration_id = uuid4()

        batch_exec_result = MagicMock()
        batch_exec_result.all.return_value = [integration_id]

        session = AsyncMock()
        session.exec = AsyncMock(return_value=batch_exec_result)

        validate_result = MagicMock(success=False, error="Unable to connect to the service")
        mock_service = MagicMock()
        mock_service.validate_integration = AsyncMock(return_value=validate_result)

        mock_settings = MagicMock()
        mock_settings.get = AsyncMock(return_value=300)

        with (
            patch("syntara.integrations.services.health_check.AsyncSessionLocal", _session_factory(session)),
            patch("syntara.integrations.services.health_check.get_runtime_settings", return_value=mock_settings),
            patch("syntara.integrations.services.health_check.create_secret_service", return_value=MagicMock()),
            patch(
                "syntara.integrations.services.health_check.IntegrationService",
                return_value=mock_service,
            ),
        ):
            result = await execute_internal_activity(
                {"activity": "integration_health_check", "input": {}},
                None,
            )

        assert result["output"]["checked"] == 1
        assert result["output"]["error"] == 1
        assert result["output"]["results"][0]["error"] == "Unable to connect to the service"

    @pytest.mark.anyio
    async def test_unexpected_exception_is_scrubbed(self) -> None:
        """Raw exception text must not leak into activity result; only exception type appears."""
        integration_id = uuid4()

        batch_exec_result = MagicMock()
        batch_exec_result.all.return_value = [integration_id]

        session = AsyncMock()
        session.exec = AsyncMock(return_value=batch_exec_result)

        mock_service = MagicMock()
        mock_service.validate_integration = AsyncMock(
            side_effect=RuntimeError("Bearer sk-secret-abc123 rejected by https://internal.example/token"),
        )

        mock_settings = MagicMock()
        mock_settings.get = AsyncMock(return_value=300)

        with (
            patch("syntara.integrations.services.health_check.AsyncSessionLocal", _session_factory(session)),
            patch("syntara.integrations.services.health_check.get_runtime_settings", return_value=mock_settings),
            patch("syntara.integrations.services.health_check.create_secret_service", return_value=MagicMock()),
            patch(
                "syntara.integrations.services.health_check.IntegrationService",
                return_value=mock_service,
            ),
        ):
            result = await execute_internal_activity(
                {"activity": "integration_health_check", "input": {}},
                None,
            )

        assert result["output"]["error"] == 1
        error_message = result["output"]["results"][0]["error"]
        assert error_message == "Unexpected error: RuntimeError"
        assert "sk-secret-abc123" not in error_message
        assert "internal.example" not in error_message


class TestRunIntegrationResourceDiscovery:
    """Tests for the integration_resource_discovery internal activity."""

    @pytest.mark.anyio
    async def test_batch_mode_processes_all_due_integrations(self) -> None:
        """Batch mode: query returns N due ids, each refreshed in its own session."""
        id1, id2 = uuid4(), uuid4()

        batch_exec_result = MagicMock()
        batch_exec_result.all.return_value = [id1, id2]

        session = AsyncMock()
        session.exec = AsyncMock(return_value=batch_exec_result)

        refresh_result = MagicMock(synced_count=1, updated_count=2, missing_count=0)
        mock_service = MagicMock()
        mock_service.refresh_resources = AsyncMock(return_value=refresh_result)

        mock_settings = MagicMock()
        mock_settings.get = AsyncMock(return_value=300)

        with (
            patch("syntara.integrations.services.resource_discovery.AsyncSessionLocal", _session_factory(session)),
            patch("syntara.integrations.services.resource_discovery.get_runtime_settings", return_value=mock_settings),
            patch("syntara.integrations.services.resource_discovery.create_secret_service", return_value=MagicMock()),
            patch("syntara.integrations.services.resource_discovery.IntegrationService", return_value=mock_service),
        ):
            result = await execute_internal_activity(
                {"activity": "integration_resource_discovery", "input": {"batch": True}},
                None,
            )

        assert result["output"]["processed"] == 2
        assert result["output"]["refreshed"] == 2
        assert result["output"]["error"] == 0
        assert mock_service.refresh_resources.await_count == 2

    @pytest.mark.anyio
    async def test_isolates_per_integration_failure(self) -> None:
        """A failing integration is recorded as error; the batch continues."""
        id1, id2 = uuid4(), uuid4()

        batch_exec_result = MagicMock()
        batch_exec_result.all.return_value = [id1, id2]

        session = AsyncMock()
        session.exec = AsyncMock(return_value=batch_exec_result)

        ok = MagicMock(synced_count=0, updated_count=0, missing_count=0)
        mock_service = MagicMock()
        mock_service.refresh_resources = AsyncMock(side_effect=[ok, RuntimeError("boom")])

        mock_settings = MagicMock()
        mock_settings.get = AsyncMock(return_value=300)

        with (
            patch("syntara.integrations.services.resource_discovery.AsyncSessionLocal", _session_factory(session)),
            patch("syntara.integrations.services.resource_discovery.get_runtime_settings", return_value=mock_settings),
            patch("syntara.integrations.services.resource_discovery.create_secret_service", return_value=MagicMock()),
            patch("syntara.integrations.services.resource_discovery.IntegrationService", return_value=mock_service),
        ):
            result = await execute_internal_activity(
                {"activity": "integration_resource_discovery", "input": {"batch": True}},
                None,
            )

        assert result["output"]["processed"] == 2
        assert result["output"]["refreshed"] == 1
        assert result["output"]["error"] == 1
