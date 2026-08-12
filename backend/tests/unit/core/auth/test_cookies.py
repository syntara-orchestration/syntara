"""Unit tests for refresh-token cookie helpers."""

from unittest.mock import MagicMock, patch

from syntara.auth.cookies import (
    clear_refresh_cookie,
    get_refresh_token_from_cookie,
    set_refresh_cookie,
)


def _mock_settings(**overrides: bool | str | None) -> MagicMock:
    defaults: dict[str, bool | str | None] = {
        "cookie_secure": True,
        "cookie_domain": None,
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


class TestSetRefreshCookie:
    """Tests for set_refresh_cookie."""

    def test_sets_cookie_with_correct_attributes(self) -> None:
        response = MagicMock()
        with patch("syntara.auth.cookies.get_settings", return_value=_mock_settings()):
            set_refresh_cookie(response, "my-jwt-token", max_age=28800)

        response.set_cookie.assert_called_once_with(
            key="ao_refresh_token",
            value="my-jwt-token",
            max_age=28800,
            httponly=True,
            secure=True,
            samesite="lax",
            domain=None,
            path="/api/v1/auth",
        )

    def test_uses_configurable_settings(self) -> None:
        response = MagicMock()
        settings = _mock_settings(
            cookie_secure=False,
            cookie_domain=".example.com",
        )
        with patch("syntara.auth.cookies.get_settings", return_value=settings):
            set_refresh_cookie(response, "tok", max_age=3600)

        response.set_cookie.assert_called_once_with(
            key="ao_refresh_token",
            value="tok",
            max_age=3600,
            httponly=True,
            secure=False,
            samesite="lax",
            domain=".example.com",
            path="/api/v1/auth",
        )


class TestClearRefreshCookie:
    """Tests for clear_refresh_cookie."""

    def test_deletes_cookie_with_correct_attributes(self) -> None:
        response = MagicMock()
        with patch("syntara.auth.cookies.get_settings", return_value=_mock_settings()):
            clear_refresh_cookie(response)

        response.delete_cookie.assert_called_once_with(
            key="ao_refresh_token",
            httponly=True,
            secure=True,
            samesite="lax",
            domain=None,
            path="/api/v1/auth",
        )


class TestGetRefreshTokenFromCookie:
    """Tests for get_refresh_token_from_cookie."""

    def test_returns_token_when_present(self) -> None:
        request = MagicMock()
        request.cookies = {"ao_refresh_token": "my-jwt-token"}
        result = get_refresh_token_from_cookie(request)

        assert result == "my-jwt-token"

    def test_returns_none_when_absent(self) -> None:
        request = MagicMock()
        request.cookies = {}
        result = get_refresh_token_from_cookie(request)

        assert result is None
