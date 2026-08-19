"""Shared fixtures for GenericAgent test modules."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from contextlib import AbstractContextManager

    from tests.fixtures.settings import FakeSettingsCache


@pytest.fixture(autouse=True)
def _mock_runtime_settings(
    override_runtime_settings: Callable[..., AbstractContextManager[FakeSettingsCache]],
) -> Generator[None]:
    """Swap the SettingsCache singleton with a FakeSettingsCache for all GenericAgent tests."""
    with override_runtime_settings():
        yield
