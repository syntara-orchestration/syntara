"""Tests for the Segment telemetry live-reload watcher functions.

Covers _resolve_telemetry_config and _reinitialize_from_runtime
(invoked by the @watch_setting callbacks for telemetry.segment_write_key
and telemetry.segment_endpoint).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.telemetry.client import (
    _on_segment_endpoint_changed,
    _on_segment_write_key_changed,
    _resolve_telemetry_config,
)


class TestResolveTelemetryConfig:
    """Tests for _resolve_telemetry_config helper."""

    @patch("syntara.telemetry.client.get_settings")
    def test_runtime_override_takes_precedence(self, mock_get_settings: MagicMock) -> None:
        mock_settings = MagicMock()
        mock_settings.segment_write_key.get_secret_value.return_value = "static-key"
        mock_get_settings.return_value = mock_settings

        write_key, host = _resolve_telemetry_config(
            override_write_key="runtime-key",
            override_endpoint="http://runtime:9999",
        )
        assert write_key == "runtime-key"
        assert host == "http://runtime:9999"

    @patch("syntara.telemetry.client.get_settings")
    def test_empty_override_falls_back_to_static(self, mock_get_settings: MagicMock) -> None:
        mock_settings = MagicMock()
        mock_settings.segment_write_key.get_secret_value.return_value = "static-key"
        mock_get_settings.return_value = mock_settings

        write_key, host = _resolve_telemetry_config(
            override_write_key="",
            override_endpoint="",
        )
        assert write_key == "static-key"
        assert host is None

    @patch("syntara.telemetry.client.get_settings")
    def test_none_override_falls_back_to_static(self, mock_get_settings: MagicMock) -> None:
        mock_settings = MagicMock()
        mock_settings.segment_write_key.get_secret_value.return_value = "static-key"
        mock_get_settings.return_value = mock_settings

        write_key, host = _resolve_telemetry_config(
            override_write_key=None,
            override_endpoint=None,
        )
        assert write_key == "static-key"
        assert host is None

    @patch("syntara.telemetry.client.get_settings")
    def test_whitespace_only_override_treated_as_empty(self, mock_get_settings: MagicMock) -> None:
        mock_settings = MagicMock()
        mock_settings.segment_write_key.get_secret_value.return_value = "static-key"
        mock_get_settings.return_value = mock_settings

        write_key, host = _resolve_telemetry_config(
            override_write_key="   ",
            override_endpoint="  ",
        )
        assert write_key == "static-key"
        assert host is None

    @patch("syntara.telemetry.client.get_settings")
    def test_no_static_key_returns_empty(self, mock_get_settings: MagicMock) -> None:
        mock_settings = MagicMock()
        mock_settings.segment_write_key.get_secret_value.return_value = ""
        mock_get_settings.return_value = mock_settings

        write_key, host = _resolve_telemetry_config(
            override_write_key="",
            override_endpoint="",
        )
        assert write_key == ""
        assert host is None

    @patch("syntara.telemetry.client.get_settings")
    def test_mixed_override_and_fallback(self, mock_get_settings: MagicMock) -> None:
        mock_settings = MagicMock()
        mock_settings.segment_write_key.get_secret_value.return_value = "static-key"
        mock_get_settings.return_value = mock_settings

        write_key, host = _resolve_telemetry_config(
            override_write_key="runtime-key",
            override_endpoint="",
        )
        assert write_key == "runtime-key"
        assert host is None


class TestReinitializeFromRuntime:
    """Tests for _reinitialize_from_runtime via the @watch_setting callbacks."""

    @patch("syntara.telemetry.client.get_telemetry_registry")
    @patch("syntara.telemetry.client.get_settings")
    @patch("syntara.settings.cache.settings_cache.get_runtime_settings")
    def test_write_key_change_triggers_reinitialize(
        self,
        mock_get_runtime: MagicMock,
        mock_get_settings: MagicMock,
        mock_get_registry: MagicMock,
    ) -> None:
        cached_values = {
            "telemetry.segment_write_key": "new-runtime-key",
        }
        mock_cache = MagicMock()
        mock_cache.get_cached.side_effect = cached_values.get
        mock_get_runtime.return_value = mock_cache

        mock_settings = MagicMock()
        mock_settings.segment_write_key.get_secret_value.return_value = "static-key"
        mock_get_settings.return_value = mock_settings

        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry

        _on_segment_write_key_changed("telemetry.segment_write_key", "new-runtime-key")

        mock_registry.reinitialize.assert_called_once_with("new-runtime-key", host=None)

    @patch("syntara.telemetry.client.get_telemetry_registry")
    @patch("syntara.telemetry.client.get_settings")
    @patch("syntara.settings.cache.settings_cache.get_runtime_settings")
    def test_endpoint_change_triggers_reinitialize(
        self,
        mock_get_runtime: MagicMock,
        mock_get_settings: MagicMock,
        mock_get_registry: MagicMock,
    ) -> None:
        cached_values = {
            "telemetry.segment_write_key": "my-key",
            "telemetry.segment_endpoint": "http://mock:9999",
        }
        mock_cache = MagicMock()
        mock_cache.get_cached.side_effect = cached_values.get
        mock_get_runtime.return_value = mock_cache

        mock_settings = MagicMock()
        mock_settings.segment_write_key.get_secret_value.return_value = "static-key"
        mock_get_settings.return_value = mock_settings

        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry

        _on_segment_endpoint_changed("telemetry.segment_endpoint", "http://mock:9999")

        mock_registry.reinitialize.assert_called_once_with(
            "my-key",
            host="http://mock:9999",
        )

    @patch("syntara.telemetry.client.get_telemetry_registry")
    @patch("syntara.telemetry.client.get_settings")
    @patch("syntara.settings.cache.settings_cache.get_runtime_settings")
    def test_cleared_runtime_key_falls_back_to_static(
        self,
        mock_get_runtime: MagicMock,
        mock_get_settings: MagicMock,
        mock_get_registry: MagicMock,
    ) -> None:
        cached_values = {
            "telemetry.segment_write_key": "",
        }
        mock_cache = MagicMock()
        mock_cache.get_cached.side_effect = cached_values.get
        mock_get_runtime.return_value = mock_cache

        mock_settings = MagicMock()
        mock_settings.segment_write_key.get_secret_value.return_value = "static-fallback"
        mock_get_settings.return_value = mock_settings

        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry

        _on_segment_write_key_changed("telemetry.segment_write_key", "")

        mock_registry.reinitialize.assert_called_once_with("static-fallback", host=None)

    @patch("syntara.telemetry.client.get_telemetry_registry")
    @patch("syntara.telemetry.client.get_settings")
    @patch("syntara.settings.cache.settings_cache.get_runtime_settings")
    def test_no_keys_anywhere_disables_telemetry(
        self,
        mock_get_runtime: MagicMock,
        mock_get_settings: MagicMock,
        mock_get_registry: MagicMock,
    ) -> None:
        mock_cache = MagicMock()
        mock_cache.get_cached.return_value = None
        mock_get_runtime.return_value = mock_cache

        mock_settings = MagicMock()
        mock_settings.segment_write_key.get_secret_value.return_value = ""
        mock_get_settings.return_value = mock_settings

        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry

        _on_segment_write_key_changed("telemetry.segment_write_key", "")

        mock_registry.reinitialize.assert_called_once_with("")

    @patch("syntara.telemetry.client.get_telemetry_registry")
    @patch("syntara.telemetry.client.get_settings")
    @patch("syntara.settings.cache.settings_cache.get_runtime_settings")
    def test_both_settings_from_runtime(
        self,
        mock_get_runtime: MagicMock,
        mock_get_settings: MagicMock,
        mock_get_registry: MagicMock,
    ) -> None:
        cached_values = {
            "telemetry.segment_write_key": "runtime-key",
            "telemetry.segment_endpoint": "http://custom:8080",
        }
        mock_cache = MagicMock()
        mock_cache.get_cached.side_effect = cached_values.get
        mock_get_runtime.return_value = mock_cache

        mock_settings = MagicMock()
        mock_settings.segment_write_key.get_secret_value.return_value = "static-key"
        mock_get_settings.return_value = mock_settings

        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry

        _on_segment_write_key_changed("telemetry.segment_write_key", "runtime-key")

        mock_registry.reinitialize.assert_called_once_with(
            "runtime-key",
            host="http://custom:8080",
        )

    @patch("syntara.telemetry.client.get_telemetry_registry")
    @patch("syntara.settings.cache.settings_cache.get_runtime_settings")
    def test_skips_reinitialize_when_not_initialized_and_no_key(
        self,
        mock_get_runtime: MagicMock,
        mock_get_registry: MagicMock,
    ) -> None:
        """_reinitialize_from_runtime is a no-op when not initialized and no runtime key."""
        mock_cache = MagicMock()
        mock_cache.get_cached.return_value = None
        mock_get_runtime.return_value = mock_cache

        mock_registry = MagicMock()
        mock_registry.is_initialized.return_value = False
        mock_get_registry.return_value = mock_registry

        _on_segment_write_key_changed("telemetry.segment_write_key", "")

        mock_registry.reinitialize.assert_not_called()

    @patch("syntara.telemetry.client.asyncio.get_running_loop")
    @patch("syntara.telemetry.client.get_telemetry_registry")
    @patch("syntara.telemetry.client.get_settings")
    @patch("syntara.settings.cache.settings_cache.get_runtime_settings")
    def test_schedules_async_init_when_not_initialized_but_key_present(
        self,
        mock_get_runtime: MagicMock,
        mock_get_settings: MagicMock,
        mock_get_registry: MagicMock,
        mock_get_running_loop: MagicMock,
    ) -> None:
        """When not initialized but a runtime key arrives, an async init task is scheduled."""
        cached_values = {"telemetry.segment_write_key": "runtime-key"}
        mock_cache = MagicMock()
        mock_cache.get_cached.side_effect = cached_values.get
        mock_get_runtime.return_value = mock_cache

        mock_settings = MagicMock()
        mock_settings.segment_write_key.get_secret_value.return_value = ""
        mock_get_settings.return_value = mock_settings

        mock_registry = MagicMock()
        mock_registry.is_initialized.return_value = False
        mock_get_registry.return_value = mock_registry

        mock_loop = MagicMock()
        mock_get_running_loop.return_value = mock_loop

        _on_segment_write_key_changed("telemetry.segment_write_key", "runtime-key")

        mock_loop.create_task.assert_called_once()
        mock_registry.reinitialize.assert_not_called()


class TestPeriodicCollectorRestart:
    """Tests for PeriodicCollector.restart()."""

    @pytest.mark.asyncio
    async def test_restart_stops_starts_and_collects_immediately(self) -> None:
        from syntara.telemetry.periodic_collector import PeriodicCollector

        mock_registry = MagicMock()
        mock_session_factory = MagicMock()

        collector = PeriodicCollector(
            registry=mock_registry,
            session_factory=mock_session_factory,
        )
        collector._worker = MagicMock()
        collector._worker.stop = AsyncMock()

        with patch(
            "syntara.telemetry.periodic_collector._collect_and_send",
            new_callable=AsyncMock,
        ) as mock_collect:
            await collector.restart()

        collector._worker.stop.assert_awaited_once()
        collector._worker.start.assert_called_once()
        mock_collect.assert_awaited_once_with(mock_session_factory, mock_registry)
