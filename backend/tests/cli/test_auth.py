"""Tests for persistent token storage in orchestrator_cli.auth."""

from __future__ import annotations

import json
import stat
import sys
import time
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path
from orchestrator_cli import auth as auth_module

_URL = "http://localhost:8000"
_TOKEN = "test-token-abc"  # noqa: S105


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect auth storage to a temp dir so tests never touch ~/.orchestrator."""
    d = tmp_path / ".orchestrator"
    d.mkdir()
    monkeypatch.setattr(auth_module, "_CONFIG_DIR", d)
    return d


# ---------------------------------------------------------------------------
# save_token
# ---------------------------------------------------------------------------


def test_save_token_writes_expected_fields(config_dir: Path) -> None:
    """save_token creates a JSON file with base_url, access_token, and saved_at."""
    path = auth_module.save_token(_URL, _TOKEN)
    data = json.loads(path.read_text())
    assert data["base_url"] == _URL
    assert data["access_token"] == _TOKEN
    assert "saved_at" in data
    assert "expires_at" not in data


def test_save_token_stores_expires_at_when_expires_in_given(config_dir: Path) -> None:
    """expires_at = saved_at + expires_in when expires_in is provided."""
    path = auth_module.save_token(_URL, _TOKEN, expires_in=3600)
    data = json.loads(path.read_text())
    assert data["expires_at"] == pytest.approx(data["saved_at"] + 3600, abs=1)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes not enforced on Windows")
def test_save_token_sets_file_mode_600(config_dir: Path) -> None:
    """Token file must not be readable by group or others."""
    path = auth_module.save_token(_URL, _TOKEN)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


# ---------------------------------------------------------------------------
# load_token
# ---------------------------------------------------------------------------


def test_load_token_returns_token_for_valid_file(config_dir: Path) -> None:
    """load_token returns the stored token when the file is valid and unexpired."""
    auth_module.save_token(_URL, _TOKEN)
    assert auth_module.load_token(_URL) == _TOKEN


def test_load_token_returns_none_when_file_missing(config_dir: Path) -> None:
    """load_token returns None without raising when no token file exists."""
    assert auth_module.load_token(_URL) is None


def test_load_token_returns_none_when_file_is_invalid_json(config_dir: Path) -> None:
    """load_token swallows JSONDecodeError and returns None."""
    auth_module._token_path(_URL).write_text("{not valid json")
    assert auth_module.load_token(_URL) is None


def test_load_token_returns_none_and_deletes_file_when_expired(config_dir: Path) -> None:
    """load_token deletes the token file and returns None when expires_at is in the past."""
    path = auth_module._token_path(_URL)
    path.write_text(
        json.dumps(
            {
                "base_url": _URL,
                "access_token": _TOKEN,
                "saved_at": time.time() - 7200,
                "expires_at": time.time() - 3600,
            }
        )
    )
    assert auth_module.load_token(_URL) is None
    assert not path.exists()


def test_load_token_returns_none_when_access_token_key_missing(config_dir: Path) -> None:
    """load_token returns None when the JSON is valid but lacks access_token."""
    auth_module._token_path(_URL).write_text(json.dumps({"base_url": _URL, "saved_at": time.time()}))
    assert auth_module.load_token(_URL) is None


# ---------------------------------------------------------------------------
# clear_token
# ---------------------------------------------------------------------------


def test_clear_token_deletes_file_and_returns_true(config_dir: Path) -> None:
    """clear_token removes the token file and returns True."""
    auth_module.save_token(_URL, _TOKEN)
    assert auth_module.clear_token(_URL) is True
    assert not auth_module._token_path(_URL).exists()


def test_clear_token_returns_false_when_no_file_exists(config_dir: Path) -> None:
    """clear_token returns False without raising when no token file exists."""
    assert auth_module.clear_token(_URL) is False


# ---------------------------------------------------------------------------
# _instance_slug
# ---------------------------------------------------------------------------


def test_instance_slug_is_idempotent() -> None:
    """The same URL always produces the same slug."""
    assert auth_module._instance_slug(_URL) == auth_module._instance_slug(_URL)


def test_instance_slug_differs_for_http_vs_https() -> None:
    """http:// and https:// produce distinct slugs so their token files never collide."""
    http_slug = auth_module._instance_slug("http://localhost:8000")
    https_slug = auth_module._instance_slug("https://localhost:8000")
    assert http_slug != https_slug
