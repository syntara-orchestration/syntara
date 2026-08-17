"""Shared test helpers for workflow engine unit tests."""

from syntara.settings.catalog import SETTINGS_CATALOG
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow


def make_workflow_runtime_settings() -> dict[str, object]:
    """Return a runtime_settings dict seeded with all workflow_engine.* catalog defaults."""
    return {e.key: e.default_value for e in SETTINGS_CATALOG if e.key.startswith("workflow_engine.")}


def init_workflow_runtime(wf: OrchestratorWorkflow) -> None:
    """Initialise the runtime-fetched fields on an OrchestratorWorkflow test instance.

    Call this inside every _make_workflow helper after the other state fields
    are set. Keeps the 4-line block from being copy-pasted across all 8 test files.
    """
    wf._runtime_settings = make_workflow_runtime_settings()
    wf._has_unhandled_failure = False
