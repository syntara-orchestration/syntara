"""Tests for resolve_aap_auth integration-required behavior (PR #771)."""

from collections.abc import Callable
from contextlib import AbstractContextManager

import pytest
from pydantic import SecretStr
from temporalio.exceptions import ApplicationError

from syntara.core.config.base import get_settings
from syntara.workflows.workflow_engine.activities.aap_common import (
    AAPResolvedAuth,
    resolve_aap_auth,
)

_FAKE_TOKEN = "tok"  # noqa: S105
_FAKE_ENV_TOKEN = "env-token"  # noqa: S105


@pytest.fixture(autouse=True)
def _aap_settings(override_settings: Callable[..., AbstractContextManager[object]]) -> object:
    with override_settings(
        aap_token=None,
        aap_username=None,
        aap_password=None,
    ):
        yield


_INTEGRATION = {"base_url": "https://aap.example.com", "verify_ssl": True}
_INTEGRATION_NO_SSL = {"base_url": "https://aap.example.com", "verify_ssl": False}


class TestResolveAAPAuthRequiresIntegration:
    """resolve_aap_auth must error when _resolved_integration is absent."""

    def test_missing_integration_raises_config_error(
        self, override_settings: Callable[..., AbstractContextManager[object]]
    ) -> None:
        with override_settings(aap_token=SecretStr(_FAKE_TOKEN)):
            with pytest.raises(ApplicationError, match="AAP integration not configured") as exc_info:
                resolve_aap_auth({}, get_settings())
        assert exc_info.value.non_retryable

    def test_none_integration_raises_config_error(
        self, override_settings: Callable[..., AbstractContextManager[object]]
    ) -> None:
        with override_settings(aap_token=SecretStr(_FAKE_TOKEN)):
            with pytest.raises(ApplicationError, match="AAP integration not configured"):
                resolve_aap_auth({"_resolved_integration": None}, get_settings())

    def test_empty_dict_integration_raises_config_error(
        self, override_settings: Callable[..., AbstractContextManager[object]]
    ) -> None:
        with override_settings(aap_token=SecretStr(_FAKE_TOKEN)):
            with pytest.raises(ApplicationError, match="AAP integration not configured"):
                resolve_aap_auth({"_resolved_integration": {}}, get_settings())


class TestResolveAAPAuthWithIntegration:
    """resolve_aap_auth uses integration for URL/SSL and credentials for auth."""

    def test_url_and_ssl_from_integration(
        self, override_settings: Callable[..., AbstractContextManager[object]]
    ) -> None:
        with override_settings(aap_token=SecretStr(_FAKE_TOKEN)):
            result = resolve_aap_auth({"_resolved_integration": _INTEGRATION}, get_settings())

        assert isinstance(result, AAPResolvedAuth)
        assert result.base_url == "https://aap.example.com"
        assert result.verify_ssl is True

    def test_verify_ssl_false_from_integration(
        self, override_settings: Callable[..., AbstractContextManager[object]]
    ) -> None:
        with override_settings(aap_token=SecretStr(_FAKE_TOKEN)):
            result = resolve_aap_auth({"_resolved_integration": _INTEGRATION_NO_SSL}, get_settings())

        assert result.verify_ssl is False

    def test_auth_from_credentials_token(self) -> None:
        creds = {
            "extra_vars": {"aap_oauth_token": "cred-token"},
        }
        result = resolve_aap_auth(
            {"_resolved_integration": _INTEGRATION, "_resolved_credentials": creds},
            get_settings(),
        )

        assert result.auth_headers == {"Authorization": "Bearer cred-token"}
        assert result.basic_auth is None

    def test_auth_from_credentials_basic(self) -> None:
        creds = {
            "extra_vars": {"aap_username": "admin", "aap_password": "secret"},
        }
        result = resolve_aap_auth(
            {"_resolved_integration": _INTEGRATION, "_resolved_credentials": creds},
            get_settings(),
        )

        assert result.auth_headers == {}
        assert result.basic_auth is not None

    def test_auth_from_settings_when_no_credentials(
        self, override_settings: Callable[..., AbstractContextManager[object]]
    ) -> None:
        with override_settings(aap_token=SecretStr(_FAKE_ENV_TOKEN)):
            result = resolve_aap_auth({"_resolved_integration": _INTEGRATION}, get_settings())

        assert result.auth_headers == {"Authorization": "Bearer env-token"}

    def test_auth_failure_raises_config_error(self) -> None:
        with pytest.raises(ApplicationError, match="Authentication failed"):
            resolve_aap_auth({"_resolved_integration": _INTEGRATION}, get_settings())

    def test_credential_with_empty_auth_returns_empty_headers(self) -> None:
        creds: dict[str, dict[str, str]] = {
            "extra_vars": {},
        }
        result = resolve_aap_auth(
            {"_resolved_integration": _INTEGRATION, "_resolved_credentials": creds},
            get_settings(),
        )
        assert result.auth_headers == {}
        assert result.basic_auth is None
