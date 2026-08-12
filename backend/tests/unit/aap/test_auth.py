"""Tests for AAP shared auth resolution."""

from collections.abc import Callable
from contextlib import AbstractContextManager

import httpx
import pytest
from pydantic import SecretStr

from syntara.aap.auth import (
    _get_auth_headers_from_settings,
    _get_basic_auth_from_settings,
    resolve_aap_connection,
)
from syntara.aap.exceptions import AAPNotConfiguredError
from syntara.core.config.base import get_settings


@pytest.fixture(autouse=True)
def _aap_settings(override_settings: Callable[..., AbstractContextManager[object]]) -> object:
    with override_settings(
        aap_base_url=None,
        aap_verify_ssl=True,
        aap_proxy_timeout_seconds=30,
        aap_token=None,
        aap_username=None,
        aap_password=None,
    ):
        yield


class TestGetAuthHeadersFromSettings:
    """Tests for _get_auth_headers_from_settings."""

    def test_token_auth_returns_bearer_header(
        self, override_settings: Callable[..., AbstractContextManager[object]]
    ) -> None:
        with override_settings(aap_token=SecretStr("my-token")):
            headers = _get_auth_headers_from_settings(get_settings())
        assert headers == {"Authorization": "Bearer my-token"}

    def test_basic_auth_returns_empty_headers(
        self, override_settings: Callable[..., AbstractContextManager[object]]
    ) -> None:
        with override_settings(aap_username="admin", aap_password=SecretStr("secret")):
            headers = _get_auth_headers_from_settings(get_settings())
        assert headers == {}

    def test_token_preferred_over_basic(self, override_settings: Callable[..., AbstractContextManager[object]]) -> None:
        with override_settings(aap_token=SecretStr("my-token"), aap_username="admin", aap_password=SecretStr("secret")):
            headers = _get_auth_headers_from_settings(get_settings())
        assert headers == {"Authorization": "Bearer my-token"}

    def test_no_auth_raises_not_configured(self) -> None:
        with pytest.raises(AAPNotConfiguredError):
            _get_auth_headers_from_settings(get_settings())


class TestGetBasicAuthFromSettings:
    """Tests for _get_basic_auth_from_settings."""

    def test_returns_basic_auth_when_no_token(
        self, override_settings: Callable[..., AbstractContextManager[object]]
    ) -> None:
        with override_settings(aap_username="admin", aap_password=SecretStr("secret")):
            auth = _get_basic_auth_from_settings(get_settings())
        assert isinstance(auth, httpx.BasicAuth)

    def test_returns_none_when_token_present(
        self, override_settings: Callable[..., AbstractContextManager[object]]
    ) -> None:
        with override_settings(aap_token=SecretStr("my-token"), aap_username="admin", aap_password=SecretStr("secret")):
            auth = _get_basic_auth_from_settings(get_settings())
        assert auth is None

    def test_returns_none_when_no_credentials(self) -> None:
        auth = _get_basic_auth_from_settings(get_settings())
        assert auth is None


class TestResolveAAPConnection:
    """Tests for resolve_aap_connection."""

    def test_env_token_auth(self, override_settings: Callable[..., AbstractContextManager[object]]) -> None:
        with override_settings(aap_base_url="https://aap.example.com", aap_token=SecretStr("env-token")):
            conn = resolve_aap_connection(get_settings())
        assert conn.base_url == "https://aap.example.com"
        assert conn.headers == {"Authorization": "Bearer env-token"}
        assert conn.basic_auth is None

    def test_env_basic_auth(self, override_settings: Callable[..., AbstractContextManager[object]]) -> None:
        with override_settings(
            aap_base_url="https://aap.example.com", aap_username="admin", aap_password=SecretStr("secret")
        ):
            conn = resolve_aap_connection(get_settings())
        assert conn.base_url == "https://aap.example.com"
        assert conn.headers == {}
        assert isinstance(conn.basic_auth, httpx.BasicAuth)

    def test_no_base_url_raises_not_configured(
        self, override_settings: Callable[..., AbstractContextManager[object]]
    ) -> None:
        with override_settings(aap_token=SecretStr("env-token")):
            with pytest.raises(AAPNotConfiguredError, match="AAP host not configured"):
                resolve_aap_connection(get_settings())

    def test_trailing_slash_stripped(self, override_settings: Callable[..., AbstractContextManager[object]]) -> None:
        with override_settings(aap_base_url="https://aap.example.com/", aap_token=SecretStr("t")):
            conn = resolve_aap_connection(get_settings())
        assert conn.base_url == "https://aap.example.com"

    def test_timeout_from_settings(self, override_settings: Callable[..., AbstractContextManager[object]]) -> None:
        with override_settings(
            aap_base_url="https://aap.example.com", aap_token=SecretStr("t"), aap_proxy_timeout_seconds=120
        ):
            conn = resolve_aap_connection(get_settings())
        assert conn.timeout == 120.0

    def test_basic_auth_over_http_raises_not_configured(
        self, override_settings: Callable[..., AbstractContextManager[object]]
    ) -> None:
        with override_settings(
            aap_base_url="http://aap.example.com", aap_username="admin", aap_password=SecretStr("secret")
        ):
            with pytest.raises(AAPNotConfiguredError, match="credentials require HTTPS"):
                resolve_aap_connection(get_settings())

    def test_token_auth_over_http_raises_not_configured(
        self, override_settings: Callable[..., AbstractContextManager[object]]
    ) -> None:
        with override_settings(aap_base_url="http://aap.example.com", aap_token=SecretStr("t")):
            with pytest.raises(AAPNotConfiguredError, match="credentials require HTTPS"):
                resolve_aap_connection(get_settings())

    def test_basic_auth_with_verify_ssl_false_raises_not_configured(
        self, override_settings: Callable[..., AbstractContextManager[object]]
    ) -> None:
        with override_settings(
            aap_base_url="https://aap.example.com",
            aap_username="admin",
            aap_password=SecretStr("secret"),
            aap_verify_ssl=False,
        ):
            with pytest.raises(AAPNotConfiguredError, match="basic auth requires SSL verification"):
                resolve_aap_connection(get_settings())

    def test_token_auth_with_verify_ssl_false_warns(
        self, override_settings: Callable[..., AbstractContextManager[object]]
    ) -> None:
        with override_settings(aap_base_url="https://aap.example.com", aap_token=SecretStr("t"), aap_verify_ssl=False):
            conn = resolve_aap_connection(get_settings())
        assert conn.verify_ssl is False
