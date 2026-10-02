"""Unit tests for orchestrator_test_sdk.e2e.helpers polling helpers."""

from dataclasses import dataclass

from orchestrator_test_sdk.e2e.helpers import _activities_settled


@dataclass
class _FakeActivity:
    activity_id: str
    status: str


@dataclass
class _FakeExecution:
    activities: list[_FakeActivity]


def _execution(*activities: tuple[str, str]) -> _FakeExecution:
    return _FakeExecution(activities=[_FakeActivity(activity_id, status) for activity_id, status in activities])


def test_activities_settled_when_all_present_are_terminal() -> None:
    execution = _execution(("trigger", "completed"), ("branch_a", "completed"))
    assert _activities_settled(execution) is True


def test_activities_settled_false_while_any_activity_running() -> None:
    execution = _execution(("trigger", "completed"), ("branch_a", "running"))
    assert _activities_settled(execution) is False


def test_activities_settled_ignores_missing_rows_without_expected_ids() -> None:
    execution = _execution(("trigger", "completed"))
    assert _activities_settled(execution) is True


def test_activities_settled_waits_for_expected_ids() -> None:
    """Missing activity rows are not settled when the caller named them (AAP-95126)."""
    execution = _execution(("trigger", "completed"), ("branch_a", "completed"))
    expected = {"trigger", "branch_a", "branch_b", "join"}
    assert _activities_settled(execution, expected) is False

    execution = _execution(
        ("trigger", "completed"),
        ("branch_a", "completed"),
        ("branch_b", "completed"),
        ("join", "completed"),
    )
    assert _activities_settled(execution, expected) is True
