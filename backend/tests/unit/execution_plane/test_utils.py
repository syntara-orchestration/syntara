"""Unit tests for shared Execution Plane utilities."""

from unittest.mock import Mock

import pytest

from syntara.execution_plane import utils


def _settings(node_container_images: dict[str, str | None]) -> Mock:
    settings = Mock()
    settings.node_container_images = node_container_images
    return settings


def test_container_image_lookup_returns_configured_image(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(utils, "get_settings", lambda: _settings({"script": "example/script:latest"}))

    assert utils.execution_plane_container_image("script") == "example/script:latest"


def test_container_image_lookup_treats_missing_and_empty_as_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(utils, "get_settings", lambda: _settings({"script": ""}))

    assert utils.execution_plane_container_image("script") is None
    assert utils.execution_plane_container_image("other") is None


def test_supported_node_types_exclude_empty_images(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        utils,
        "get_settings",
        lambda: _settings({"script": "example/script:latest", "other": "", "missing": None}),
    )

    assert utils.execution_plane_supported_node_types() == frozenset({"script"})
