"""Shared fixtures for integration/services tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.fixtures.settings import FakeSettingsCache, enable_script_nodes

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture(autouse=True)
def _ensure_runtime_settings() -> Generator[None, None, None]:
    """Ensure the SettingsCache singleton is initialised for temporal tests.

    Activities like ``execute_script_activity`` call ``get_runtime_settings()``
    which raises ``RuntimeError`` if the singleton has not been set.
    Also enables script nodes since the gate defaults to False.
    """
    import syntara.settings.cache.settings_cache as _settings_mod

    original = _settings_mod._runtime_settings
    _settings_mod._runtime_settings = FakeSettingsCache()  # type: ignore[assignment]

    with enable_script_nodes():
        try:
            yield
        finally:
            _settings_mod._runtime_settings = original


# These tests drive workflow-engine routing (loops, conditions, switch, converge,
# auth) but use `script` nodes as their unit of work. AAP-93615 moved script
# execution out of an in-process subprocess and into cold-start Kubernetes pods, so
# the in-process EP worker started by the `temporal_env` fixture now needs a real
# kind cluster plus a reachable node image to run the pod and resume the activity.
# CI's integration job has neither (it registers only a placeholder `local://`
# target), so every script dispatch fails ('failed' != 'completed'). This coverage
# moves with the Execution Plane code to its own repository; the non-script tests in
# these modules still run.
_EP_DISPATCH_TESTS = frozenset(
    {
        "test_for_each_loop",
        "test_do_while_loop",
        "test_condition_true_branch",
        "test_condition_false_branch",
        "test_switch_routes_to_matching_case",
        "test_switch_routes_to_default",
        "test_converge_all_waits_for_both_branches",
        "test_converge_any_fires_after_n_required",
        "test_converge_any_off_section_node_does_not_cause_engine_error",
        "test_continue_on_failure_executes_next_node",
        "test_condition_then_parallel_converge",
        "test_downstream_node_receives_upstream_output",
        "test_worker_processes_workflows",
        "test_worker_uses_correct_task_queue",
        "test_multiple_workers_different_queues",
        "test_authorized_workflow_succeeds",
        "test_schedule_baked_auth_header_accepted",
    }
)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip EP script-dispatch tests that require a kind cluster absent from CI (AAP-93615)."""
    skip_marker = pytest.mark.skip(
        reason="Execution Plane script dispatch requires a kind cluster + node image not present in CI (AAP-93615)"
    )
    for item in items:
        if getattr(item, "originalname", item.name) in _EP_DISPATCH_TESTS:
            item.add_marker(skip_marker)
