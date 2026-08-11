"""Unit tests for UserLoginTelemetryHandler."""

import hashlib
import hmac
from unittest.mock import MagicMock, patch
from uuid import uuid4

from syntara.auth.audit.user_login import AMR, UserLoginEvent
from syntara.telemetry.events.new_user import NewUserEvent
from syntara.telemetry.events.user_login import UserLoginEvent as UserLoginTelemetryEvent
from syntara.telemetry.handlers.user_login import UserLoginTelemetryHandler

TEST_SALT = "12345678-1234-5678-1234-567812345678"

_SETTINGS_PATH = "syntara.telemetry.handlers.user_login.get_settings"
_REGISTRY_PATH = "syntara.telemetry.handlers.user_login.get_telemetry_registry"


def _make_settings_mock(*, enabled: bool = True) -> MagicMock:
    mock = MagicMock()
    mock.segment_high_volume_events_enabled = enabled
    return mock


def _make_registry_mock() -> MagicMock:
    registry = MagicMock()
    registry.is_initialized.return_value = True
    registry.entitlement_id = ""
    registry.installation_salt = TEST_SALT
    return registry


class TestUserLoginHandlerTelemetry:
    """Test that the handler emits Segment telemetry correctly."""

    def test_emits_user_login_event(self) -> None:
        registry = _make_registry_mock()
        registry.entitlement_id = "ent-123"

        user_id = uuid4()
        domain_event = UserLoginEvent(user_id=user_id, amr=[AMR.FEDERATED], idp="okta")

        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=registry),
        ):
            result = UserLoginTelemetryHandler().handle(domain_event)

        assert result is None
        registry.send_event.assert_called_once()
        event = registry.send_event.call_args[0][0]
        assert isinstance(event, UserLoginTelemetryEvent)
        expected_hash = hmac.new(TEST_SALT.encode(), str(user_id).encode(), hashlib.sha256).hexdigest()
        assert event.user_id_hash == expected_hash
        assert event.amr == ["fed"]
        assert event.idp == "okta"
        assert event.entitlement_id == "ent-123"

    def test_first_login_emits_both_events(self) -> None:
        registry = _make_registry_mock()

        user_id = uuid4()
        domain_event = UserLoginEvent(user_id=user_id, amr=[AMR.PASSWORD], idp="local", is_first_login=True)

        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=registry),
        ):
            result = UserLoginTelemetryHandler().handle(domain_event)

        assert result is None
        assert registry.send_event.call_count == 2
        events = [call.args[0] for call in registry.send_event.call_args_list]
        assert isinstance(events[0], UserLoginTelemetryEvent)
        assert isinstance(events[1], NewUserEvent)
        expected_hash = hmac.new(TEST_SALT.encode(), str(user_id).encode(), hashlib.sha256).hexdigest()
        assert events[1].user_id_hash == expected_hash

    def test_non_first_login_does_not_emit_new_user(self) -> None:
        registry = _make_registry_mock()

        domain_event = UserLoginEvent(user_id=uuid4(), amr=[AMR.PASSWORD], idp="local", is_first_login=False)

        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=registry),
        ):
            UserLoginTelemetryHandler().handle(domain_event)

        registry.send_event.assert_called_once()
        assert isinstance(registry.send_event.call_args[0][0], UserLoginTelemetryEvent)

    def test_skips_when_not_initialized(self) -> None:
        registry = _make_registry_mock()
        registry.is_initialized.return_value = False

        domain_event = UserLoginEvent(user_id=uuid4(), amr=[AMR.PASSWORD], idp="local")

        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=registry),
        ):
            result = UserLoginTelemetryHandler().handle(domain_event)

        assert result is None
        registry.send_event.assert_not_called()

    def test_does_not_raise_on_telemetry_error(self) -> None:
        domain_event = UserLoginEvent(user_id=uuid4(), amr=[AMR.PASSWORD], idp="local")

        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, side_effect=RuntimeError("boom")),
        ):
            result = UserLoginTelemetryHandler().handle(domain_event)
        assert result is None

    def test_amr_fed(self) -> None:
        registry = _make_registry_mock()

        domain_event = UserLoginEvent(user_id=uuid4(), amr=[AMR.FEDERATED], idp="okta")

        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=registry),
        ):
            UserLoginTelemetryHandler().handle(domain_event)

        event = registry.send_event.call_args[0][0]
        assert event.amr == ["fed"]
        assert event.idp == "okta"

    def test_amr_pwd(self) -> None:
        registry = _make_registry_mock()

        domain_event = UserLoginEvent(user_id=uuid4(), amr=[AMR.PASSWORD], idp="local")

        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=registry),
        ):
            UserLoginTelemetryHandler().handle(domain_event)

        event = registry.send_event.call_args[0][0]
        assert event.amr == ["pwd"]
        assert event.idp == "local"

    def test_different_salts_produce_different_hashes(self) -> None:
        """Same user UUID with different installation salts must produce different hashes."""
        user_id = uuid4()
        hashes = []
        for salt in [TEST_SALT, str(uuid4())]:
            registry = _make_registry_mock()
            registry.installation_salt = salt

            domain_event = UserLoginEvent(user_id=user_id, amr=[AMR.PASSWORD], idp="local")

            with (
                patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
                patch(_REGISTRY_PATH, return_value=registry),
            ):
                UserLoginTelemetryHandler().handle(domain_event)

            event = registry.send_event.call_args[0][0]
            hashes.append(event.user_id_hash)

        assert hashes[0] != hashes[1]

    def test_same_salt_produces_consistent_hash(self) -> None:
        """Same user UUID with same salt must produce the same hash."""
        user_id = uuid4()
        hashes = []
        for _ in range(2):
            registry = _make_registry_mock()

            domain_event = UserLoginEvent(user_id=user_id, amr=[AMR.PASSWORD], idp="local")

            with (
                patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
                patch(_REGISTRY_PATH, return_value=registry),
            ):
                UserLoginTelemetryHandler().handle(domain_event)

            event = registry.send_event.call_args[0][0]
            hashes.append(event.user_id_hash)

        assert hashes[0] == hashes[1]


class TestUserLoginHandlerDisabledByDefault:
    """Test that high-volume user_login events are suppressed by default."""

    def test_no_user_login_event_when_disabled(self) -> None:
        registry = _make_registry_mock()

        domain_event = UserLoginEvent(user_id=uuid4(), amr=[AMR.PASSWORD], idp="local", is_first_login=False)

        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=False)),
            patch(_REGISTRY_PATH, return_value=registry),
        ):
            result = UserLoginTelemetryHandler().handle(domain_event)

        assert result is None
        registry.send_event.assert_not_called()

    def test_new_user_event_still_emitted_when_disabled(self) -> None:
        """new_user events must still fire on first login even when high-volume events are off."""
        registry = _make_registry_mock()

        domain_event = UserLoginEvent(user_id=uuid4(), amr=[AMR.PASSWORD], idp="local", is_first_login=True)

        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=False)),
            patch(_REGISTRY_PATH, return_value=registry),
        ):
            result = UserLoginTelemetryHandler().handle(domain_event)

        assert result is None
        registry.send_event.assert_called_once()
        event = registry.send_event.call_args[0][0]
        assert isinstance(event, NewUserEvent)
