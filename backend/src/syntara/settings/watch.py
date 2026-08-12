"""Decorator for registering runtime setting change watchers.

To react to a runtime setting change, decorate a function with
:func:`watch_setting`.  The application lifecycle handles the rest —
no additional wiring is needed::

    from syntara.settings.watch import watch_setting

    @watch_setting("logging.log_level")
    def _on_log_level_changed(_key: str, new_value: Any) -> None:
        level = str(new_value).upper()
        _set_log_level(level)

The decorated module must be imported during normal application startup
(i.e. part of the regular import chain).  Only settings with
``requires_restart=False`` can be watched.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from collections.abc import Callable

    from syntara.settings.cache.settings_cache import SettingsCache

logger = structlog.stdlib.get_logger(__name__)

_pending_watchers: list[tuple[str, Callable[[str, Any], Any]]] = []


def watch_setting(key: str) -> Callable[[Callable[[str, Any], Any]], Callable[[str, Any], Any]]:
    """Register a function as a setting change handler.

    The decorated function will be called with ``(key, new_value)`` when
    the setting's value changes in the database.  Registration is deferred
    until :meth:`SettingsCache.start_watching` is called at startup.

    Args:
        key: Dot-namespaced setting key to watch, e.g. ``"logging.log_level"``.

    """

    def decorator(func: Callable[[str, Any], Any]) -> Callable[[str, Any], Any]:
        _pending_watchers.append((key, func))
        return func

    return decorator


def _apply_watchers(cache: SettingsCache) -> None:
    """Apply all pending :func:`watch_setting` registrations to a cache.

    Called internally by :meth:`SettingsCache.start_watching` — callers
    do not need to invoke this directly.

    Args:
        cache: The process-wide :class:`SettingsCache` instance.

    """
    for key, callback in _pending_watchers:
        cache.on_change(key, callback)
    if _pending_watchers:
        logger.info(
            "settings.watchers_applied",
            count=len(_pending_watchers),
            keys=[k for k, _ in _pending_watchers],
        )
    _pending_watchers.clear()
