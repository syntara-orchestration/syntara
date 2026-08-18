"""Settings override fixtures and FakeSettingsCache shared across unit and integration tests."""

from __future__ import annotations

import os
from contextlib import AbstractContextManager, contextmanager
from typing import TYPE_CHECKING, Any

import pytest

# Prevent local .env from leaking into tests. Must be set before Settings is
# imported, since _get_env_file() is evaluated at class-definition time.
os.environ.setdefault("APP_ENV_FILE_PATH", "/dev/null")
os.environ.setdefault(
    "APP_SECRET_ENCRYPTION_KEY",
    "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
)

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from syntara.core.config.base import Settings


class FakeSettingsCache:
    """In-memory SettingsCache replacement for unit and integration tests.

    Seeded from SETTINGS_CATALOG defaults, with test-specific overrides applied on top.
    """

    def __init__(self, overrides: dict[str, object] | None = None) -> None:
        """Seed from catalog defaults and apply overrides."""
        from syntara.settings.catalog import SETTINGS_CATALOG
        from syntara.settings.seeder import _resolve_default

        self._store: dict[str, object] = {
            entry.key: _resolve_default(entry.default_value) for entry in SETTINGS_CATALOG
        }
        if overrides:
            unknown = [k for k in overrides if k not in self._store]
            if unknown:
                msg = f"Runtime setting(s) not in SETTINGS_CATALOG: {unknown}"
                raise KeyError(msg)
            self._store.update(overrides)

    async def get(self, key: str) -> Any:  # noqa: ANN401
        """Return the setting value, or None if unknown."""
        return self._store.get(key)

    async def _get_typed(
        self,
        key: str,
        expected_types: type | tuple[type, ...],
        type_name: str,
        *,
        default: Any = None,  # noqa: ANN401
        reject_bool: bool = False,
    ) -> Any:  # noqa: ANN401
        """Fetch a setting and validate its runtime type."""
        from syntara.settings.exceptions import SettingTypeError

        value = await self.get(key)
        if value is None:
            if default is not None:
                return default
            raise SettingTypeError(key, type_name, "None")
        if reject_bool and isinstance(value, bool):
            raise SettingTypeError(key, type_name, "bool")
        if not isinstance(value, expected_types):
            raise SettingTypeError(key, type_name, type(value).__name__)
        return self._validate_against_catalog(key, value, default)

    def _validate_against_catalog(
        self,
        key: str,
        value: Any,  # noqa: ANN401
        default: Any,  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        """Mirror SettingsCache._validate_against_catalog for test parity."""
        from syntara.settings.catalog import SETTINGS_CATALOG
        from syntara.settings.exceptions import SettingValidationError
        from syntara.settings.validators import validate_setting_value

        defn = next((d for d in SETTINGS_CATALOG if d.key == key), None)
        if defn is None or defn.validation_schema is None:
            return value

        try:
            validate_setting_value(
                key=key,
                value=value,
                value_type=defn.value_type,
                validation_schema=defn.validation_schema,
            )
        except SettingValidationError:
            from syntara.settings.seeder import _resolve_default

            raw_fallback = defn.default_value if defn.default_value is not None else default
            return _resolve_default(raw_fallback)

        return value

    async def get_int(self, key: str, *, default: int | None = None) -> int:
        """Return the setting value as an ``int``."""
        return await self._get_typed(key, int, "int", default=default, reject_bool=True)  # type: ignore[no-any-return]

    async def get_float(self, key: str, *, default: float | None = None) -> float:
        """Return the setting value as a ``float``."""
        value = await self._get_typed(key, (int, float), "float", default=default, reject_bool=True)
        return float(value)

    async def get_str(self, key: str, *, default: str | None = None) -> str:
        """Return the setting value as a ``str``."""
        return await self._get_typed(key, str, "str", default=default)  # type: ignore[no-any-return]

    async def get_bool(self, key: str, *, default: bool | None = None) -> bool:
        """Return the setting value as a ``bool``."""
        return await self._get_typed(key, bool, "bool", default=default)  # type: ignore[no-any-return]

    async def invalidate(self, key: str) -> None:
        """Evict key from store."""
        self._store.pop(key, None)

    async def publish_change(self, key: str) -> None:
        """No-op in tests."""

    def on_change(self, key: str, callback: Any) -> None:  # noqa: ANN401
        """Register a callback (no-op in tests — no polling)."""

    def start_watching(self) -> None:
        """No-op in tests."""

    async def stop_watching(self) -> None:
        """No-op in tests."""


@contextmanager
def enable_script_nodes() -> Generator[None, None, None]:
    """Enable script nodes by toggling the frozen Pydantic Settings field.

    Use as a context manager in fixtures that need script node execution enabled.
    """
    from syntara.core.config.base import get_settings

    settings = get_settings()
    original = settings.script_nodes_enabled
    object.__setattr__(settings, "script_nodes_enabled", True)
    try:
        yield
    finally:
        object.__setattr__(settings, "script_nodes_enabled", original)


@pytest.fixture
def override_settings() -> Callable[..., AbstractContextManager[object]]:
    """Fixture for temporarily overriding settings in tests.

    Example:
        def test_meaning_of_life(override_settings):
            with override_settings(meaning_of_life=42):
                settings = get_settings()
                assert settings.meaning_of_life == 42

    """
    from contextlib import ExitStack
    from unittest.mock import patch

    from syntara.core.config.base import get_settings

    @contextmanager
    def _override(**overrides: object) -> Generator[Settings, None, None]:
        settings = get_settings()
        with ExitStack() as stack:
            for name, value in overrides.items():
                if not hasattr(settings, name):
                    msg = f"Setting '{name}' does not exist on Settings object"
                    raise AttributeError(msg)
                stack.enter_context(patch.object(settings, name, value))
            yield settings

    return _override


@pytest.fixture
def override_runtime_settings() -> Callable[..., AbstractContextManager[FakeSettingsCache]]:
    """Temporarily override runtime settings in tests.

    Swaps the process-wide SettingsCache singleton with a FakeSettingsCache
    seeded from SETTINGS_CATALOG defaults.

    Example:
        def test_custom_timeout(override_runtime_settings):
            with override_runtime_settings({"context_manager.request_timeout_seconds": 3}):
                ...

    """

    @contextmanager
    def _override(
        overrides: dict[str, object] | None = None,
        /,
    ) -> Generator[FakeSettingsCache, None, None]:
        import syntara.settings.cache.settings_cache as _mod

        original = _mod._runtime_settings
        fake = FakeSettingsCache(overrides)
        _mod._runtime_settings = fake  # type: ignore[assignment]
        try:
            yield fake
        finally:
            _mod._runtime_settings = original

    return _override


@pytest.fixture
def fast_retry_settings(
    override_settings: Callable[..., AbstractContextManager[object]],
) -> Generator[None, None, None]:
    """Configure fast retry settings for agent orchestrator tests."""
    with override_settings(
        adapter_max_retries=3,
        adapter_initial_backoff_seconds=0.1,
        adapter_backoff_growth_factor=2.0,
        adapter_max_backoff_seconds=1.0,
        adapter_request_timeout_seconds=5.0,
    ):
        yield
