"""Deployment-only terminal-proof trust inputs and safe disabled defaults."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from syntara.core.config.base import Settings
from syntara.eventstreams.services.delivery_cache_policy import DeliveryEvidencePolicy


def test_proof_cache_is_disabled_without_external_trust_inputs() -> None:
    settings = Settings()
    assert not settings.event_delivery_cache_enabled
    assert settings.event_delivery_cache_epoch is None
    assert settings.event_delivery_cache_clock_error_bound_seconds is None
    assert settings.event_delivery_cache_ttl_seconds == 60
    assert settings.event_delivery_cache_timeout_seconds == 1


def test_enabled_cache_loads_external_epoch_and_clock_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_EVENT_DELIVERY_CACHE_ENABLED", "true")
    monkeypatch.setenv("APP_EVENT_DELIVERY_CACHE_EPOCH", str(UUID(int=20)))
    monkeypatch.setenv("APP_EVENT_DELIVERY_CACHE_CLOCK_ERROR_BOUND_SECONDS", "0.25")
    settings = Settings()
    assert settings.event_delivery_cache_enabled
    assert settings.event_delivery_cache_epoch == UUID(int=20)
    assert settings.event_delivery_cache_clock_error_bound_seconds == 0.25


@pytest.mark.parametrize(
    "changes",
    [
        {"event_delivery_cache_epoch": None},
        {"event_delivery_cache_epoch": UUID(int=0)},
        {"event_delivery_cache_epoch": "invalid"},
        {"event_delivery_cache_clock_error_bound_seconds": None},
        {"event_delivery_cache_clock_error_bound_seconds": 1},
        {"event_delivery_cache_clock_error_bound_seconds": -1},
        {"event_delivery_cache_clock_error_bound_seconds": float("inf")},
        {"event_delivery_cache_ttl_seconds": 0},
        {"event_delivery_cache_ttl_seconds": 1},
        {"event_delivery_retention_seconds": 1},
        {"event_delivery_cache_timeout_seconds": 0},
        {"event_delivery_cache_timeout_seconds": float("nan")},
        {"event_delivery_cache_skew_seconds": 0},
    ],
)
def test_enabled_cache_rejects_missing_or_invalid_trust(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(
            {
                "event_delivery_cache_enabled": True,
                "event_delivery_cache_epoch": UUID(int=20),
                "event_delivery_cache_clock_error_bound_seconds": 0.25,
                **changes,
            }
        )


@pytest.mark.parametrize(
    ("changes", "accepted"),
    [
        ({}, True),
        ({"enabled": False, "cache_epoch": None, "clock_error_bound_seconds": None}, True),
        ({"cache_epoch": None}, False),
        ({"enabled": False, "cache_epoch": UUID(int=0)}, False),
        ({"clock_error_bound_seconds": None}, False),
        ({"clock_error_bound_seconds": 1}, False),
        ({"ttl_seconds": 1}, False),
        ({"retention_seconds": 1}, False),
    ],
)
def test_settings_and_injected_policy_share_trust_rules(changes: dict[str, object], *, accepted: bool) -> None:
    values = {"enabled": True, "cache_epoch": UUID(int=20), "clock_error_bound_seconds": 0.25, **changes}
    setting_names = {
        "cache_epoch": "event_delivery_cache_epoch",
        "retention_seconds": "event_delivery_retention_seconds",
    }
    deployment_values = {setting_names.get(key, f"event_delivery_cache_{key}"): value for key, value in values.items()}
    if accepted:
        Settings.model_validate(deployment_values)
        DeliveryEvidencePolicy.model_validate(values)
    else:
        with pytest.raises(ValidationError):
            Settings.model_validate(deployment_values)
        with pytest.raises(ValidationError):
            DeliveryEvidencePolicy.model_validate(values)
