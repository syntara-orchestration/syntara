"""Tests for the @watch_setting decorator and _apply_watchers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from syntara.settings import watch as watch_module
from syntara.settings.watch import _apply_watchers, watch_setting


@pytest.fixture(autouse=True)
def _isolate_pending_watchers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace _pending_watchers with a fresh list for each test."""
    monkeypatch.setattr(watch_module, "_pending_watchers", [])


class TestWatchSetting:
    """Tests for the @watch_setting decorator."""

    def test_registers_function_in_pending_list(self) -> None:
        @watch_setting("test.key")
        def handler(_key: str, _value: object) -> None:
            pass

        assert ("test.key", handler) in watch_module._pending_watchers

    def test_returns_original_function(self) -> None:
        def handler(_key: str, _value: object) -> None:
            pass

        decorated = watch_setting("test.key")(handler)
        assert decorated is handler

    def test_multiple_decorators_register_all(self) -> None:
        @watch_setting("a.key")
        def handler_a(_key: str, _value: object) -> None:
            pass

        @watch_setting("b.key")
        def handler_b(_key: str, _value: object) -> None:
            pass

        assert len(watch_module._pending_watchers) == 2


class TestApplyWatchers:
    """Tests for _apply_watchers."""

    def test_calls_on_change_for_each_pending(self) -> None:
        @watch_setting("test.key")
        def handler(_key: str, _value: object) -> None:
            pass

        mock_cache = MagicMock()
        _apply_watchers(mock_cache)

        mock_cache.on_change.assert_called_once_with("test.key", handler)

    def test_no_pending_does_not_call_on_change(self) -> None:
        mock_cache = MagicMock()
        _apply_watchers(mock_cache)
        mock_cache.on_change.assert_not_called()
