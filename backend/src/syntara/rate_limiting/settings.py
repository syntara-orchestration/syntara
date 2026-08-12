"""Rate limiting settings constants and helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from syntara.settings.cache.settings_cache import SettingsCache

RATE_LIMIT_REQUESTS_PER_WINDOW = "rate_limiting.requests_per_window"
RATE_LIMIT_WINDOW_DURATION_SECONDS = "rate_limiting.window_duration_seconds"


async def get_rate_limit_config(
    settings_cache: SettingsCache,
) -> tuple[int, int] | None:
    """Read the global rate limit configuration from runtime settings.

    Returns:
        ``(requests_per_window, window_seconds)`` when rate limiting is
        enabled, or ``None`` when disabled (value is 0 or absent).

    """
    requests_per_window = await settings_cache.get_int(RATE_LIMIT_REQUESTS_PER_WINDOW)
    if not requests_per_window:
        return None

    window_seconds = await settings_cache.get_int(RATE_LIMIT_WINDOW_DURATION_SECONDS)

    return requests_per_window, window_seconds
