"""Tests for secret_encryption_key validation and path-based loading (AAP-76773).

Run with:
    uv run pytest tests/unit/core/config/test_encryption_key_validation.py -v
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from syntara.core.config.base import CredentialEncryptionSettings, validate_encryption_key_at_startup
from syntara.core.lib.encryption import key_from_string

if TYPE_CHECKING:
    from pathlib import Path

VALID_KEY = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
ALL_ZEROS_KEY = "0" * 64

# CredentialEncryptionSettings is a mixin without env_prefix.
# The APP_ prefix is only on the composed Settings class.
# When testing the mixin directly, use unprefixed env var names.
ENV_KEY = "SECRET_ENCRYPTION_KEY"
ENV_PATH = "SECRET_ENCRYPTION_KEY_PATH"


def _build_settings(env: dict[str, str]) -> CredentialEncryptionSettings:
    with patch.dict("os.environ", env, clear=False):
        return CredentialEncryptionSettings()


class TestEncryptionKeyRequired:
    """Verify secret_encryption_key is optional at construction but required at startup."""

    def test_construction_succeeds_without_key(self) -> None:
        settings = _build_settings({})
        assert settings.secret_encryption_key is None

    def test_startup_validation_rejects_missing_key(self) -> None:
        settings = _build_settings({})
        with (
            patch("syntara.core.config.base.get_settings", return_value=settings),
            pytest.raises(RuntimeError, match=r"APP_SECRET_ENCRYPTION_KEY.*is required"),
        ):
            validate_encryption_key_at_startup()

    def test_accepts_valid_hex_key(self) -> None:
        settings = _build_settings({ENV_KEY: VALID_KEY})
        assert settings.secret_encryption_key is not None
        assert settings.secret_encryption_key.get_secret_value() == VALID_KEY


class TestRejectsInsecureDefaults:
    """Verify the all-zeros default key is explicitly rejected."""

    def test_rejects_all_zeros_key(self) -> None:
        with pytest.raises(ValidationError, match="all-zeros default"):
            _build_settings({ENV_KEY: ALL_ZEROS_KEY})

    def test_error_includes_generation_instructions(self) -> None:
        with pytest.raises(ValidationError, match="openssl rand -hex 32"):
            _build_settings({ENV_KEY: ALL_ZEROS_KEY})


class TestPathBasedLoading:
    """Verify key loading from file path with correct precedence."""

    def test_loads_key_from_path(self, tmp_path: Path) -> None:
        key_file = tmp_path / "encryption-key"
        key_file.write_text(VALID_KEY + "\n")
        settings = _build_settings({ENV_PATH: str(key_file)})
        assert settings.secret_encryption_key is not None
        assert settings.secret_encryption_key.get_secret_value() == VALID_KEY

    def test_path_wins_over_direct_value(self, tmp_path: Path) -> None:
        key_file = tmp_path / "encryption-key"
        key_file.write_text(VALID_KEY)
        other_key = "abcdef01abcdef01abcdef01abcdef01abcdef01abcdef01abcdef01abcdef01"
        settings = _build_settings(
            {
                ENV_KEY: other_key,
                ENV_PATH: str(key_file),
            }
        )
        assert settings.secret_encryption_key is not None
        assert settings.secret_encryption_key.get_secret_value() == VALID_KEY

    def test_rejects_nonexistent_path(self) -> None:
        with pytest.raises(ValidationError, match="does not exist"):
            _build_settings({ENV_PATH: "/nonexistent/path/key"})

    def test_rejects_invalid_hex_in_file(self, tmp_path: Path) -> None:
        key_file = tmp_path / "bad-key"
        key_file.write_text("x" * 64)
        with pytest.raises(ValidationError, match="valid hex string"):
            _build_settings({ENV_PATH: str(key_file)})

    def test_rejects_all_zeros_in_file(self, tmp_path: Path) -> None:
        key_file = tmp_path / "zeros-key"
        key_file.write_text(ALL_ZEROS_KEY)
        with pytest.raises(ValidationError, match="all-zeros default"):
            _build_settings({ENV_PATH: str(key_file)})

    def test_rejects_unreadable_file(self, tmp_path: Path) -> None:
        key_file = tmp_path / "unreadable-key"
        key_file.write_text(VALID_KEY)
        key_file.chmod(0o000)
        try:
            with pytest.raises(ValidationError, match="Failed to read"):
                _build_settings({ENV_PATH: str(key_file)})
        finally:
            key_file.chmod(0o644)

    def test_rejects_empty_file(self, tmp_path: Path) -> None:
        key_file = tmp_path / "empty-key"
        key_file.write_text("")
        with pytest.raises(ValidationError, match="must be exactly 64 hex characters"):
            _build_settings({ENV_PATH: str(key_file)})


class TestKeyFromStringDefenseInDepth:
    """Verify key_from_string() rejects insecure keys independently of Settings validation."""

    def test_rejects_all_zeros_bytes(self) -> None:
        with pytest.raises(ValueError, match="insecure all-zeros"):
            key_from_string(ALL_ZEROS_KEY)

    def test_accepts_valid_key(self) -> None:
        key_bytes = key_from_string(VALID_KEY)
        assert len(key_bytes) == 32

    def test_allow_insecure_accepts_all_zeros(self) -> None:
        key_bytes = key_from_string(ALL_ZEROS_KEY, allow_insecure=True)
        assert key_bytes == b"\x00" * 32
