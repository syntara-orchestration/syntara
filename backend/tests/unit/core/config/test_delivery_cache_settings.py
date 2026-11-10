"""Deployment-only terminal-proof trust inputs and safe disabled defaults."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from syntara.core.config.base import Settings
from syntara.eventstreams.services import delivery_cache_policy
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
        {"event_delivery_cache_clock_error_bound_seconds": 2},
        {"event_delivery_cache_clock_error_bound_seconds": -1},
        {"event_delivery_cache_clock_error_bound_seconds": float("inf")},
        {"event_delivery_cache_clock_error_bound_seconds": float("nan")},
        {"event_delivery_cache_clock_error_bound_seconds": "invalid"},
    ],
)
def test_untrusted_cache_settings_disable_caching(changes: dict[str, object], monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings.model_validate(
        {
            "event_delivery_cache_enabled": True,
            "event_delivery_cache_epoch": UUID(int=20),
            "event_delivery_cache_clock_error_bound_seconds": 0.25,
            **changes,
        }
    )
    assert not settings.event_delivery_cache_enabled
    monkeypatch.setattr(delivery_cache_policy, "get_settings", lambda: settings)
    policy = DeliveryEvidencePolicy.from_settings()
    assert not policy.enabled
    assert policy.retention_seconds == settings.event_delivery_retention_seconds


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("EPOCH", "invalid"),
        ("EPOCH", str(UUID(int=0))),
        ("CLOCK_ERROR_BOUND_SECONDS", "invalid"),
        ("CLOCK_ERROR_BOUND_SECONDS", "-1"),
        ("CLOCK_ERROR_BOUND_SECONDS", "nan"),
        ("CLOCK_ERROR_BOUND_SECONDS", "inf"),
    ],
)
def test_untrusted_environment_values_allow_startup(name: str, value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_EVENT_DELIVERY_CACHE_ENABLED", "true")
    monkeypatch.setenv("APP_EVENT_DELIVERY_CACHE_EPOCH", str(UUID(int=20)))
    monkeypatch.setenv("APP_EVENT_DELIVERY_CACHE_CLOCK_ERROR_BOUND_SECONDS", "0.25")
    monkeypatch.setenv(f"APP_EVENT_DELIVERY_CACHE_{name}", value)
    assert not Settings().event_delivery_cache_enabled


@pytest.mark.parametrize(
    "changes",
    [
        {"event_delivery_cache_ttl_seconds": 0},
        {"event_delivery_cache_ttl_seconds": 1},
        {"event_delivery_retention_seconds": 1},
        {"event_delivery_cache_timeout_seconds": 0},
        {"event_delivery_cache_timeout_seconds": float("nan")},
        {"event_delivery_cache_skew_seconds": 0},
    ],
)
def test_invalid_cache_durations_still_fail_validation(changes: dict[str, object]) -> None:
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
    ("changes", "expected_enabled"),
    [
        ({}, True),
        ({"enabled": False, "cache_epoch": None, "clock_error_bound_seconds": None}, False),
        ({"clock_error_bound_seconds": 0}, True),
        ({"cache_epoch": None}, False),
        ({"cache_epoch": "invalid"}, False),
        ({"cache_epoch": UUID(int=0)}, False),
        ({"enabled": False, "cache_epoch": UUID(int=0)}, False),
        ({"clock_error_bound_seconds": None}, False),
        ({"clock_error_bound_seconds": 1}, False),
        ({"clock_error_bound_seconds": -1}, False),
        ({"clock_error_bound_seconds": "invalid"}, False),
        ({"clock_error_bound_seconds": float("inf")}, False),
        ({"clock_error_bound_seconds": float("nan")}, False),
    ],
)
def test_settings_and_injected_policy_share_trust_rules(changes: dict[str, object], *, expected_enabled: bool) -> None:
    values = {"enabled": True, "cache_epoch": UUID(int=20), "clock_error_bound_seconds": 0.25, **changes}
    setting_names = {
        "cache_epoch": "event_delivery_cache_epoch",
        "retention_seconds": "event_delivery_retention_seconds",
    }
    deployment_values = {setting_names.get(key, f"event_delivery_cache_{key}"): value for key, value in values.items()}
    assert Settings.model_validate(deployment_values).event_delivery_cache_enabled is expected_enabled
    assert DeliveryEvidencePolicy.model_validate(values).enabled is expected_enabled
