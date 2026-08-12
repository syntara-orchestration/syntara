"""Unit tests for audit handler auto-discovery."""

import logging
from dataclasses import dataclass
from types import ModuleType
from unittest.mock import patch

import pytest

from syntara.audit.discovery import discover_handlers, get_event_type
from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import AuditEvent, EventCategory
from syntara.audit.models.structured_data import AuditContextData


@dataclass
class _FakeEvent:
    value: str


class _FakeHandler(AuditEventHandler["_FakeEvent"]):
    def handle(self, event: "_FakeEvent") -> AuditEvent:
        return AuditEvent(
            event_category=EventCategory.USER_ACTION,
            event_action="fake",
            event_message=event.value,
            source_component="test",
        )


class _IntermediateHandler(AuditEventHandler["_FakeEvent"]):
    """Intermediate base that binds the generic parameter."""

    def handle(self, event: "_FakeEvent") -> AuditEvent:
        return AuditEvent(
            event_category=EventCategory.USER_ACTION,
            event_action="intermediate",
            event_message=event.value,
            source_component="test",
        )


class _DerivedFromIntermediate(_IntermediateHandler):
    """Concrete handler inheriting the generic binding from an intermediate class."""


class _RequiresArgHandler(AuditEventHandler["_FakeEvent"]):
    """Handler whose __init__ requires an argument — discovery must skip it."""

    def __init__(self, dependency: str) -> None:
        self._dependency = dependency

    def handle(self, event: "_FakeEvent") -> AuditEvent:
        return AuditEvent(
            event_category=EventCategory.USER_ACTION,
            event_action="requires_arg",
            event_message=event.value,
            source_component="test",
        )


class TestGetEventType:
    """Tests for extracting the event type from a handler's generic parameter."""

    def test_extracts_type_from_generic_base(self) -> None:
        """get_event_type returns the type argument from AuditEventHandler[T]."""
        result = get_event_type(_FakeHandler)
        assert result is _FakeEvent

    def test_returns_none_for_non_generic_handler(self) -> None:
        """get_event_type returns None if the handler has no type parameter."""

        class _RawHandler(AuditEventHandler):  # type: ignore[type-arg]
            def handle(self, event: object) -> AuditEvent:
                return AuditEvent(
                    event_category=EventCategory.USER_ACTION,
                    event_action="raw",
                    event_message="raw",
                    source_component="test",
                    structured_data=AuditContextData(data_type="test"),
                )

        result = get_event_type(_RawHandler)
        assert result is None

    def test_walks_mro_for_intermediate_ancestor(self) -> None:
        """get_event_type finds the parameter through a multi-level inheritance chain."""
        result = get_event_type(_DerivedFromIntermediate)
        assert result is _FakeEvent


class TestDiscoverHandlers:
    """Tests for discover_handlers() package walking."""

    def test_discovers_handlers_from_package(self) -> None:
        """discover_handlers returns a dict mapping event types to handler instances."""
        # Create a fake package that contains _FakeHandler
        fake_module = ModuleType("syntara.test_pkg.audit")
        fake_module._FakeHandler = _FakeHandler  # type: ignore[attr-defined]
        fake_module._FakeEvent = _FakeEvent  # type: ignore[attr-defined]

        fake_pkg = ModuleType("syntara.test_pkg")
        fake_pkg.__path__ = []
        fake_pkg.__name__ = "syntara.test_pkg"

        with (
            patch("syntara.audit.discovery.pkgutil.walk_packages") as mock_walk,
            patch("syntara.audit.discovery.importlib.import_module") as mock_import,
        ):
            mock_walk.return_value = [
                (None, "syntara.test_pkg.audit", False),
            ]
            mock_import.return_value = fake_module

            registry = discover_handlers(fake_pkg)

        assert _FakeEvent in registry
        assert isinstance(registry[_FakeEvent], _FakeHandler)

    def test_skips_abstract_base_class(self) -> None:
        """discover_handlers does not register AuditEventHandler itself."""
        fake_module = ModuleType("syntara.test_pkg.base")
        fake_module.AuditEventHandler = AuditEventHandler  # type: ignore[attr-defined]

        fake_pkg = ModuleType("syntara.test_pkg")
        fake_pkg.__path__ = []
        fake_pkg.__name__ = "syntara.test_pkg"

        with (
            patch("syntara.audit.discovery.pkgutil.walk_packages") as mock_walk,
            patch("syntara.audit.discovery.importlib.import_module") as mock_import,
        ):
            mock_walk.return_value = [(None, "syntara.test_pkg.base", False)]
            mock_import.return_value = fake_module

            registry = discover_handlers(fake_pkg)

        assert len(registry) == 0

    def test_empty_package_returns_empty_dict(self) -> None:
        """discover_handlers returns empty dict when no handlers found."""
        fake_pkg = ModuleType("empty_pkg")
        fake_pkg.__path__ = []
        fake_pkg.__name__ = "empty_pkg"

        with patch("syntara.audit.discovery.pkgutil.walk_packages") as mock_walk:
            mock_walk.return_value = []
            registry = discover_handlers(fake_pkg)

        assert registry == {}

    def test_discovers_handler_with_intermediate_base(self) -> None:
        """discover_handlers finds concrete handlers that inherit their generic binding."""
        fake_module = ModuleType("syntara.test_pkg.derived")
        fake_module._DerivedFromIntermediate = _DerivedFromIntermediate  # type: ignore[attr-defined]

        fake_pkg = ModuleType("syntara.test_pkg")
        fake_pkg.__path__ = []
        fake_pkg.__name__ = "syntara.test_pkg"

        with (
            patch("syntara.audit.discovery.pkgutil.walk_packages") as mock_walk,
            patch("syntara.audit.discovery.importlib.import_module") as mock_import,
        ):
            mock_walk.return_value = [(None, "syntara.test_pkg.derived", False)]
            mock_import.return_value = fake_module

            registry = discover_handlers(fake_pkg)

        assert _FakeEvent in registry
        assert isinstance(registry[_FakeEvent], _DerivedFromIntermediate)

    def test_instantiation_failure_is_logged_and_skipped(self, caplog: pytest.LogCaptureFixture) -> None:
        """A handler whose __init__ raises is logged and skipped, not fatal."""
        fake_module = ModuleType("syntara.test_pkg.needs_arg")
        fake_module._RequiresArgHandler = _RequiresArgHandler  # type: ignore[attr-defined]

        fake_pkg = ModuleType("syntara.test_pkg")
        fake_pkg.__path__ = []
        fake_pkg.__name__ = "syntara.test_pkg"

        with (
            patch("syntara.audit.discovery.pkgutil.walk_packages") as mock_walk,
            patch("syntara.audit.discovery.importlib.import_module") as mock_import,
            caplog.at_level(logging.ERROR, logger="syntara.audit.discovery"),
        ):
            mock_walk.return_value = [(None, "syntara.test_pkg.needs_arg", False)]
            mock_import.return_value = fake_module

            registry = discover_handlers(fake_pkg)

        assert registry == {}
        assert any("instantiation failed" in record.message for record in caplog.records)

    def test_import_failure_is_logged_and_skipped(self, caplog: pytest.LogCaptureFixture) -> None:
        """Modules that fail to import are logged and skipped, not fatal."""
        fake_pkg = ModuleType("syntara.test_pkg")
        fake_pkg.__path__ = []
        fake_pkg.__name__ = "syntara.test_pkg"

        with (
            patch("syntara.audit.discovery.pkgutil.walk_packages") as mock_walk,
            patch("syntara.audit.discovery.importlib.import_module") as mock_import,
            caplog.at_level(logging.ERROR, logger="syntara.audit.discovery"),
        ):
            mock_walk.return_value = [(None, "syntara.test_pkg.broken", False)]
            mock_import.side_effect = ImportError("boom")

            registry = discover_handlers(fake_pkg)

        assert registry == {}
        assert any("failed to import module" in record.message for record in caplog.records)


class TestDiscoverySecurityValidation:
    """Tests for security validations that prevent malicious module loading."""

    def test_rejects_non_nexus_package(self, caplog: pytest.LogCaptureFixture) -> None:
        """discover_handlers rejects packages outside the syntara.* hierarchy."""
        malicious_pkg = ModuleType("malicious.package")
        malicious_pkg.__path__ = []
        malicious_pkg.__name__ = "malicious.package"

        with caplog.at_level(logging.ERROR, logger="syntara.audit.discovery"):
            registry = discover_handlers(malicious_pkg)

        assert registry == {}
        assert any("restricted to syntara.* packages" in record.message for record in caplog.records)

    def test_rejects_module_outside_expected_hierarchy(self, caplog: pytest.LogCaptureFixture) -> None:
        """discover_handlers rejects modules whose name doesn't match the package prefix."""
        fake_module = ModuleType("malicious.injected.handler")
        fake_module._FakeHandler = _FakeHandler  # type: ignore[attr-defined]

        fake_pkg = ModuleType("syntara.test_pkg")
        fake_pkg.__path__ = []
        fake_pkg.__name__ = "syntara.test_pkg"

        with (
            patch("syntara.audit.discovery.pkgutil.walk_packages") as mock_walk,
            patch("syntara.audit.discovery.importlib.import_module") as mock_import,
            caplog.at_level(logging.ERROR, logger="syntara.audit.discovery"),
        ):
            # Mock pkgutil to return a module with mismatched name
            mock_walk.return_value = [(None, "malicious.injected.handler", False)]
            mock_import.return_value = fake_module

            registry = discover_handlers(fake_pkg)

        assert registry == {}
        assert any("rejected module outside expected package hierarchy" in record.message for record in caplog.records)

    def test_rejects_module_with_path_outside_expected_base(self, caplog: pytest.LogCaptureFixture) -> None:
        """discover_handlers rejects modules whose file path is outside the expected base directory."""
        from pathlib import Path
        from tempfile import mkdtemp

        # Create a malicious module with a file path outside the expected base
        malicious_dir = mkdtemp(prefix="malicious_")
        malicious_file = Path(malicious_dir) / "handler.py"

        fake_module = ModuleType("syntara.test_pkg.handler")
        fake_module.__file__ = str(malicious_file)
        fake_module._FakeHandler = _FakeHandler  # type: ignore[attr-defined]

        fake_pkg = ModuleType("syntara.test_pkg")
        # Set the package path to a different directory
        safe_dir = mkdtemp(prefix="safe_nexus_")
        fake_pkg.__path__ = [safe_dir]
        fake_pkg.__name__ = "syntara.test_pkg"

        try:
            with (
                patch("syntara.audit.discovery.pkgutil.walk_packages") as mock_walk,
                patch("syntara.audit.discovery.importlib.import_module") as mock_import,
                caplog.at_level(logging.ERROR, logger="syntara.audit.discovery"),
            ):
                mock_walk.return_value = [(None, "syntara.test_pkg.handler", False)]
                mock_import.return_value = fake_module

                registry = discover_handlers(fake_pkg)

            assert registry == {}
            assert any(
                "rejected module with file path outside expected base" in record.message for record in caplog.records
            )
        finally:
            # Cleanup temp directories
            import shutil

            shutil.rmtree(malicious_dir, ignore_errors=True)
            shutil.rmtree(safe_dir, ignore_errors=True)
