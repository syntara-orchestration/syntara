"""Deployment defaults and administrator overrides for bounded record runners."""

from collections.abc import Generator

import pytest
from pydantic import ValidationError

from syntara.core.config.base import get_settings

DEFAULTS = {
    "event_fetch_max_records": 100,
    "event_queue_max_records": 100,
    "event_queue_max_bytes": 8 * 1024 * 1024,
    "event_partition_max_records": 10,
    "event_processing_concurrency": 8,
    "event_fetch_timeout_ms": 100,
    "event_drain_timeout_seconds": 20,
}


@pytest.fixture(autouse=True)
def clear_settings() -> Generator[None, None, None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.parametrize(("name", "default"), DEFAULTS.items())
def test_defaults_and_environment_override(name: str, default: int, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(f"APP_{name.upper()}", raising=False)
    assert getattr(get_settings(), name) == default
    get_settings.cache_clear()
    monkeypatch.setenv(f"APP_{name.upper()}", "3")
    assert getattr(get_settings(), name) == 3


@pytest.mark.parametrize("name", DEFAULTS)
@pytest.mark.parametrize("value", ["0", "-1"])
def test_limits_must_be_positive(name: str, value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"APP_{name.upper()}", value)
    with pytest.raises(ValidationError):
        get_settings()


@pytest.mark.parametrize("value", ["nan", "inf"])
def test_drain_deadline_must_be_finite(value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_EVENT_DRAIN_TIMEOUT_SECONDS", value)
    with pytest.raises(ValidationError):
        get_settings()
