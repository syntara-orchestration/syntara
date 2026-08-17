"""Unit tests for seed_builtin_workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.workflows.exceptions import ScheduledTriggerSyncError
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_publish_event import WorkflowPublishEvent
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.seed_builtin import _BUILTIN_DEFINITIONS, seed_builtin_workflows
from syntara.workflows.validators import workflow_validator as real_workflow_validator

if TYPE_CHECKING:
    from collections.abc import Generator


def _mock_session(*results: object) -> AsyncMock:
    """Create a mock session whose .exec() returns results in sequence."""
    session = AsyncMock()
    mock_results = []
    for result in results:
        mock_result = MagicMock()
        if result is None:
            mock_result.first.return_value = None
            mock_result.one_or_none.return_value = None
        else:
            mock_result.first.return_value = result
            mock_result.one_or_none.return_value = result
        mock_results.append(mock_result)
    session.exec.side_effect = mock_results
    return session


def _mock_admin() -> MagicMock:
    admin = MagicMock()
    admin.id = uuid4()
    return admin


def _mock_project() -> MagicMock:
    project = MagicMock()
    project.id = uuid4()
    return project


def _assert_worst_case_runtime_fits_interval(defn: dict[str, Any]) -> None:
    """A scheduled builtin's worst-case run time must fit within one schedule interval.

    Worst case = the node timeout on the first attempt plus every retry's backoff +
    timeout. Fallbacks mirror node_settings_resolver.resolve_retry_policy so this
    stays a true worst case even if a future edit sets max_retries without also
    setting initial_interval/backoff_coefficient.
    """
    node_settings = defn["nodes"][0]["settings"]
    node_timeout = node_settings["timeout"]
    retry_policy = node_settings.get("retry_policy") or {}

    max_retries = retry_policy.get("max_retries", 3)
    initial_interval = retry_policy.get("initial_interval", 1)
    max_interval = retry_policy.get("max_interval", 60)
    backoff_coefficient = retry_policy.get("backoff_coefficient", 2.0)

    total_worst_case = node_timeout  # first attempt
    backoff = initial_interval
    for _ in range(max_retries):
        total_worst_case += backoff + node_timeout
        backoff = min(backoff * backoff_coefficient, max_interval)

    interval_spec = defn["triggers"][0]["parameters"]["interval"]
    # ISO 8601 recurring interval, e.g. "R/2024-01-01T00:00:00Z/PT5M" — the last
    # component is the ISO 8601 duration. Parsed narrowly here (not a general ISO
    # 8601 duration parser) since this builtin's interval is a fixed, known constant.
    duration_str = interval_spec.rsplit("/", 1)[-1]
    parse_error_msg = f"Expected a PT<n>M duration, got {duration_str!r} — update parsing if format changed"
    assert duration_str.startswith("PT"), parse_error_msg
    assert duration_str.endswith("M"), parse_error_msg
    interval_seconds = int(duration_str[2:-1]) * 60

    assert total_worst_case < interval_seconds, (
        f"Worst-case total time ({total_worst_case}s with max_retries={max_retries}) "
        f"exceeds schedule interval ({interval_seconds}s)"
    )


class TestSeedBuiltinWorkflows:
    """Test suite for seed_builtin_workflows."""

    @pytest.fixture(autouse=True)
    def _patch_validator(self) -> Generator[MagicMock, None, None]:
        with patch("syntara.workflows.seed_builtin.workflow_validator") as mock_v:
            self.mock_validator = mock_v
            yield mock_v

    @pytest.fixture(autouse=True)
    def _patch_scheduled_trigger_service(self) -> Generator[MagicMock, None, None]:
        """Prevent real Temporal connection attempts during unit tests."""
        with patch("syntara.workflows.seed_builtin.ScheduledTriggerService") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.sync_scheduled_triggers = AsyncMock(return_value=0)
            mock_cls.return_value = mock_instance
            self.mock_scheduler = mock_instance
            yield mock_instance

    @pytest.mark.asyncio
    async def test_raises_when_no_admin_user(self) -> None:
        session = _mock_session(None)
        with pytest.raises(RuntimeError, match="No admin user found"):
            await seed_builtin_workflows(session)

    @pytest.mark.asyncio
    async def test_raises_when_no_builtin_project(self) -> None:
        session = _mock_session(_mock_admin(), None)
        with pytest.raises(RuntimeError, match="Built-in project not found"):
            await seed_builtin_workflows(session)

    @pytest.mark.asyncio
    async def test_creates_all_builtin_workflows(self) -> None:
        admin, project = _mock_admin(), _mock_project()
        # exec sequence per definition: admin (shared), project (shared),
        # then for each definition: existing workflow lookup (None = new)
        session = _mock_session(admin, project, *[None] * len(_BUILTIN_DEFINITIONS))

        await seed_builtin_workflows(session)

        add_calls = session.add.call_args_list
        workflows_added = [c[0][0] for c in add_calls if isinstance(c[0][0], Workflow)]
        versions_added = [c[0][0] for c in add_calls if isinstance(c[0][0], WorkflowVersion)]

        assert len(workflows_added) == len(_BUILTIN_DEFINITIONS)
        assert len(versions_added) == len(_BUILTIN_DEFINITIONS)

        for wf in workflows_added:
            assert wf.is_builtin is True
            assert wf.published_version_id is not None
            assert wf.project_id == project.id
            assert wf.created_by == admin.id

        for ver in versions_added:
            assert ver.version == 1

        # Verify WorkflowPublishEvent was added for each workflow
        publish_events_added = [c[0][0] for c in add_calls if isinstance(c[0][0], WorkflowPublishEvent)]
        assert len(publish_events_added) == len(_BUILTIN_DEFINITIONS)

        created_names = {wf.name for wf in workflows_added}
        expected_names = {d["name"] for d in _BUILTIN_DEFINITIONS}
        assert created_names == expected_names

        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_unchanged_workflow(self) -> None:
        first_def = _BUILTIN_DEFINITIONS[0]

        existing = MagicMock(spec=Workflow)
        existing.id = uuid4()
        existing.current_version = 1
        existing.project_id = uuid4()

        cur_ver = MagicMock(spec=WorkflowVersion)
        cur_ver.workflow_definition = first_def

        # admin, project, existing workflow, current version, then remaining defs as new
        session = _mock_session(
            _mock_admin(), _mock_project(), existing, cur_ver, *[None] * (len(_BUILTIN_DEFINITIONS) - 1)
        )

        await seed_builtin_workflows(session)

        # Only the remaining (non-first) definitions should create new workflows
        workflows_added = [c[0][0] for c in session.add.call_args_list if isinstance(c[0][0], Workflow)]
        assert len(workflows_added) == len(_BUILTIN_DEFINITIONS) - 1

    @pytest.mark.asyncio
    async def test_updates_changed_workflow(self) -> None:
        first_def = _BUILTIN_DEFINITIONS[0]
        old_def = {**first_def, "description": "Old description"}

        existing = MagicMock(spec=Workflow)
        existing.id = uuid4()
        existing.current_version = 1
        existing.project_id = uuid4()
        existing.increment_version.return_value = 2

        cur_ver = MagicMock(spec=WorkflowVersion)
        cur_ver.workflow_definition = old_def

        # admin, project, existing workflow, current version, then remaining defs as new
        session = _mock_session(
            _mock_admin(), _mock_project(), existing, cur_ver, *[None] * (len(_BUILTIN_DEFINITIONS) - 1)
        )

        await seed_builtin_workflows(session)

        versions_added = [c[0][0] for c in session.add.call_args_list if isinstance(c[0][0], WorkflowVersion)]
        updated_version = next(v for v in versions_added if v.version == 2)
        assert updated_version.workflow_definition == first_def
        assert existing.published_version_id == updated_version.id

        # Verify WorkflowPublishEvent was added for the updated version
        publish_events = [c[0][0] for c in session.add.call_args_list if isinstance(c[0][0], WorkflowPublishEvent)]
        assert any(e.version_id == updated_version.id for e in publish_events)

    @pytest.mark.asyncio
    async def test_failed_seed_continues_to_next(self) -> None:
        self.mock_validator.validate_workflow_definition.side_effect = [
            ValueError("bad"),
            *[None] * (len(_BUILTIN_DEFINITIONS) - 1),
        ]
        session = _mock_session(_mock_admin(), _mock_project(), *[None] * (len(_BUILTIN_DEFINITIONS) - 1))

        await seed_builtin_workflows(session)

        workflows_added = [c[0][0] for c in session.add.call_args_list if isinstance(c[0][0], Workflow)]
        assert len(workflows_added) == len(_BUILTIN_DEFINITIONS) - 1

    @pytest.mark.asyncio
    async def test_definitions_are_valid(self) -> None:
        """Sanity check that embedded definitions have required fields."""
        for defn in _BUILTIN_DEFINITIONS:
            assert "name" in defn
            assert "schema_version" in defn
            assert "triggers" in defn
            assert "nodes" in defn
            assert "edges" in defn

    @pytest.mark.asyncio
    async def test_sync_builtin_schedules_called_on_create(self) -> None:
        """Every newly-created builtin workflow gets schedule-synced."""
        admin, project = _mock_admin(), _mock_project()
        session = _mock_session(admin, project, *[None] * len(_BUILTIN_DEFINITIONS))

        await seed_builtin_workflows(session)

        assert self.mock_scheduler.sync_scheduled_triggers.await_count == len(_BUILTIN_DEFINITIONS)
        synced_definitions = [
            call.kwargs["workflow_definition"] for call in self.mock_scheduler.sync_scheduled_triggers.await_args_list
        ]
        synced_names = {d["name"] for d in synced_definitions}
        assert synced_names == {d["name"] for d in _BUILTIN_DEFINITIONS}

        # Verify builtins route to background task queue
        sync_calls = self.mock_scheduler.sync_scheduled_triggers.await_args_list
        assert all(call.kwargs.get("is_builtin") is True for call in sync_calls)

    @pytest.mark.asyncio
    async def test_sync_builtin_schedules_called_on_unchanged_skip(self) -> None:
        """Schedule sync runs even when the definition is unchanged (idempotent)."""
        first_def = _BUILTIN_DEFINITIONS[0]
        existing = MagicMock(spec=Workflow)
        existing.id = uuid4()
        existing.current_version = 1
        existing.project_id = uuid4()

        cur_ver = MagicMock(spec=WorkflowVersion)
        cur_ver.workflow_definition = first_def

        session = _mock_session(
            _mock_admin(), _mock_project(), existing, cur_ver, *[None] * (len(_BUILTIN_DEFINITIONS) - 1)
        )

        await seed_builtin_workflows(session)

        # First definition took the "unchanged, skip" branch but must still
        # have triggered a schedule sync call for that workflow's ID.
        synced_workflow_ids = {
            call.kwargs["workflow_id"] for call in self.mock_scheduler.sync_scheduled_triggers.await_args_list
        }
        assert str(existing.id) in synced_workflow_ids

    @pytest.mark.asyncio
    async def test_sync_error_does_not_abort_seeding(self) -> None:
        """A Temporal-unreachable ScheduledTriggerSyncError must not fail the whole seed pass.

        Mirrors WorkflowService's own degrade-gracefully behaviour on
        publish: the workflow row is still seeded correctly even if
        Temporal is down at startup.
        """
        self.mock_scheduler.sync_scheduled_triggers = AsyncMock(
            side_effect=ScheduledTriggerSyncError("some-workflow-id", 1)
        )
        admin, project = _mock_admin(), _mock_project()
        session = _mock_session(admin, project, *[None] * len(_BUILTIN_DEFINITIONS))

        # Must not raise even though every sync call fails.
        await seed_builtin_workflows(session)

        workflows_added = [c[0][0] for c in session.add.call_args_list if isinstance(c[0][0], Workflow)]
        assert len(workflows_added) == len(_BUILTIN_DEFINITIONS)
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_health_check_definition_has_scheduled_trigger(self) -> None:
        """Health check workflow uses a scheduled_trigger, not manual_trigger."""
        hc_def = next(d for d in _BUILTIN_DEFINITIONS if d["name"] == "Integration Health Check")
        assert hc_def["triggers"][0]["type"] == "scheduled_trigger"
        assert hc_def["triggers"][0]["parameters"]["schedule_type"] == "interval"
        assert hc_def["nodes"][0]["type"] == "internal_activity"
        assert hc_def["nodes"][0]["parameters"]["activity"] == "integration_health_check"

    @pytest.mark.asyncio
    async def test_health_check_definition_passes_real_schema_validation(self) -> None:
        """Health check definition passes real schema validation (not mocked)."""
        hc_def = next(d for d in _BUILTIN_DEFINITIONS if d["name"] == "Integration Health Check")

        real_workflow_validator.validate_workflow_definition(hc_def)

    def test_health_check_node_timeout_fits_within_schedule_interval(self) -> None:
        """Worst-case execution time (all retries + backoff) must fit within one schedule interval."""
        hc_def = next(d for d in _BUILTIN_DEFINITIONS if d["name"] == "Integration Health Check")
        _assert_worst_case_runtime_fits_interval(hc_def)

    def test_resource_discovery_node_timeout_fits_within_schedule_interval(self) -> None:
        """Discovery's worst-case run time must fit within its schedule interval (timeout < interval)."""
        rd_def = next(d for d in _BUILTIN_DEFINITIONS if d["name"] == "Integration Resource Discovery")
        _assert_worst_case_runtime_fits_interval(rd_def)
