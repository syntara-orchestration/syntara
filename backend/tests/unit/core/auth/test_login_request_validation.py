"""Unit tests for LoginRequest input validation."""

import pytest
from pydantic import ValidationError

from syntara.auth.schemas import LoginRequest


class TestLoginRequestNullByteValidation:
    """Test that LoginRequest rejects null bytes in username."""

    def test_normal_username_accepted(self) -> None:
        req = LoginRequest(username="alice", password="secret")  # noqa: S106
        assert req.username == "alice"

    def test_null_byte_in_username_rejected(self) -> None:
        with pytest.raises(ValidationError, match="invalid characters"):
            LoginRequest(username="admin\x00hacker", password="secret")  # noqa: S106

    def test_null_byte_at_start_rejected(self) -> None:
        with pytest.raises(ValidationError, match="invalid characters"):
            LoginRequest(username="\x00admin", password="secret")  # noqa: S106

    def test_null_byte_at_end_rejected(self) -> None:
        with pytest.raises(ValidationError, match="invalid characters"):
            LoginRequest(username="admin\x00", password="secret")  # noqa: S106

    def test_multiple_null_bytes_rejected(self) -> None:
        with pytest.raises(ValidationError, match="invalid characters"):
            LoginRequest(username="\x00\x00\x00", password="secret")  # noqa: S106

    def test_empty_username_accepted(self) -> None:
        req = LoginRequest(username="", password="secret")  # noqa: S106
        assert req.username == ""

    def test_unicode_username_accepted(self) -> None:
        req = LoginRequest(username="用户名", password="secret")  # noqa: S106
        assert req.username == "用户名"
