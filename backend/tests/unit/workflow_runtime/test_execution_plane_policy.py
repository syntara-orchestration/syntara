"""Keep system EP dispatch controls independent of workflow node settings."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from syntara.core.config.base import Settings, WorkflowClientSettings
from syntara.workflow_runtime.engines.temporal.activities import runtime_settings_activity
from syntara.workflow_runtime.engines.temporal.execution_plane_policy import (
    EP_POLICY_SNAPSHOT_KEY,
    build_ep_retry_policy,
)


def test_ep_policy_defaults_match_process_settings() -> None:
    settings = WorkflowClientSettings()
    policy = build_ep_retry_policy({})
    assert policy.maximum_attempts == settings.ep_dispatch_max_retries + 1
    assert policy.initial_interval == timedelta(seconds=settings.ep_dispatch_initial_backoff_seconds)
    assert policy.maximum_interval == timedelta(seconds=settings.ep_dispatch_max_backoff_seconds)


@pytest.mark.parametrize("ep_dispatch_max_retries", [0, 1, 5])
def test_ep_retry_count_excludes_initial_attempt(ep_dispatch_max_retries: int) -> None:
    policy = build_ep_retry_policy({"ep_dispatch_max_retries": ep_dispatch_max_retries})
    assert policy.maximum_attempts == ep_dispatch_max_retries + 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"ep_dispatch_max_retries": -1},
        {"ep_dispatch_initial_backoff_seconds": 0},
        {"ep_dispatch_max_backoff_seconds": 0},
        {"ep_dispatch_initial_backoff_seconds": 20, "ep_dispatch_max_backoff_seconds": 10},
        {"ep_work_timeout_seconds": 0},
        {"ep_work_timeout_seconds": float("inf")},
    ],
)
def test_ep_policy_rejects_invalid_configuration(overrides: dict[str, float]) -> None:
    with pytest.raises(ValidationError):
        WorkflowClientSettings.model_validate(overrides)


@pytest.mark.asyncio
async def test_runtime_settings_activity_records_separate_ep_policy() -> None:
    settings = SimpleNamespace(
        ep_dispatch_max_retries=7,
        ep_dispatch_initial_backoff_seconds=2.5,
        ep_dispatch_max_backoff_seconds=30,
        ep_work_timeout_seconds=1200,
    )
    cache = SimpleNamespace(get=AsyncMock(return_value=None))
    with (
        patch.object(runtime_settings_activity, "get_settings", return_value=settings),
        patch.object(runtime_settings_activity, "get_runtime_settings", return_value=cache),
    ):
        snapshot = await runtime_settings_activity.fetch_workflow_runtime_settings()
    settings.ep_dispatch_max_retries = 0
    assert snapshot[EP_POLICY_SNAPSHOT_KEY] == {
        "ep_dispatch_max_retries": 7,
        "ep_dispatch_initial_backoff_seconds": 2.5,
        "ep_dispatch_max_backoff_seconds": 30,
        "ep_work_timeout_seconds": 1200,
    }
    policy = build_ep_retry_policy(snapshot[EP_POLICY_SNAPSHOT_KEY])
    assert policy.maximum_attempts == 8
    assert policy.initial_interval == timedelta(seconds=2.5)
    assert policy.maximum_interval == timedelta(seconds=30)


def test_ep_settings_can_be_overridden_for_troubleshooting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_EP_DISPATCH_MAX_RETRIES", "0")
    monkeypatch.setenv("APP_EP_DISPATCH_INITIAL_BACKOFF_SECONDS", "2")
    monkeypatch.setenv("APP_EP_DISPATCH_MAX_BACKOFF_SECONDS", "8")
    monkeypatch.setenv("APP_EP_WORK_TIMEOUT_SECONDS", "600")
    monkeypatch.setenv("APP_EP_REQUEST_TIMEOUT_SECONDS", "15")
    settings = Settings()
    assert settings.ep_dispatch_max_retries == 0
    assert settings.ep_dispatch_initial_backoff_seconds == 2
    assert settings.ep_dispatch_max_backoff_seconds == 8
    assert settings.ep_work_timeout_seconds == 600
    assert settings.ep_request_timeout_seconds == 15
