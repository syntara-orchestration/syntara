"""Unit tests for the Temporal activity registries."""

from typing import ClassVar

from syntara.workflows.seed_builtin import _BUILTIN_DEFINITIONS
from syntara.workflows.workflow_engine.activities.registry import (
    ACTIVITY_REGISTRY,
    BACKGROUND_ACTIVITY_REGISTRY,
)


class TestBackgroundActivityRegistry:
    """BACKGROUND_ACTIVITY_REGISTRY must contain exactly the minimal set needed by built-in workflows."""

    EXPECTED_ACTIVITIES: ClassVar[set[str]] = {
        "register_activity_monitoring",
        "fetch_workflow_runtime_settings",
        "manual_trigger",
        "scheduled_trigger",
        "execute_internal_activity",
    }

    def test_contains_exactly_expected_activities(self) -> None:
        assert set(BACKGROUND_ACTIVITY_REGISTRY.keys()) == self.EXPECTED_ACTIVITIES

    def test_is_strict_subset_of_main_registry(self) -> None:
        """Every background activity must also appear in the main registry."""
        assert BACKGROUND_ACTIVITY_REGISTRY.keys() <= ACTIVITY_REGISTRY.keys()

    def test_does_not_contain_user_executor_activities(self) -> None:
        """User-facing executor activities must not leak into the background registry."""
        user_activities = {"execute_agentic_activity", "execute_script_activity", "execute_http_request_activity"}
        assert BACKGROUND_ACTIVITY_REGISTRY.keys().isdisjoint(user_activities)

    def test_every_builtin_trigger_type_has_a_registered_background_activity(self) -> None:
        """Ensure all builtin trigger types have registered background activities.

        Missing activities cause workflows to fail with NotFoundError on every tick.
        """
        trigger_types = {
            trigger["type"] for workflow_dict in _BUILTIN_DEFINITIONS for trigger in workflow_dict["triggers"]
        }
        missing = trigger_types - BACKGROUND_ACTIVITY_REGISTRY.keys()
        assert not missing, (
            f"Builtin workflow trigger type(s) {missing} have no matching activity in "
            "BACKGROUND_ACTIVITY_REGISTRY — workflows using these triggers will fail."
        )
