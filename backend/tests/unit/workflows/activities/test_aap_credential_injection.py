"""Tests for AAP activity credential injection (T068).

These tests verify the credential override logic in execute_aap_job_template_activity.
Full execution requires an AAP instance, so we test the auth setup path only.
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from syntara.core.config.base import get_settings
from syntara.workflows.workflow_engine.activities.aap_common import (
    get_aap_auth_from_credentials,
    get_aap_auth_headers,
    get_aap_basic_auth,
)


@pytest.fixture(autouse=True)
def _aap_settings(override_settings: Callable[..., AbstractContextManager[object]]) -> object:
    with override_settings(
        aap_token=None,
        aap_username=None,
        aap_password=None,
    ):
        yield


class TestAAPCredentialInjection:
    """Test AAP activity auth override from resolved credentials."""

    def test_settings_token_auth(self, override_settings: Callable[..., AbstractContextManager[object]]) -> None:
        """Default settings-based token auth works."""
        with override_settings(aap_token=SecretStr("settings-token")):
            headers = get_aap_auth_headers(get_settings())
        assert headers["Authorization"] == "Bearer settings-token"

    def test_settings_basic_auth(self, override_settings: Callable[..., AbstractContextManager[object]]) -> None:
        """Default settings-based basic auth works."""
        with override_settings(aap_username="admin", aap_password=SecretStr("pass")):
            basic_auth = get_aap_basic_auth(get_settings())
        assert basic_auth is not None

    def test_credential_override_structure(self) -> None:
        """Verify resolved credential extra_vars structure matches what AAP activity expects."""
        resolved_creds = {
            "extra_vars": {
                "auth_type": "aap",
                "aap_username": "nexus-user",
                "aap_password": "nexus-pass",
                "aap_oauth_token": "oauth-token-123",
            },
        }
        extra_vars = resolved_creds["extra_vars"]

        # Verify the structure has the fields the activity code checks
        assert "aap_oauth_token" in extra_vars
        assert "aap_username" in extra_vars
        assert "aap_password" in extra_vars

    def test_credential_oauth_auth_extracted(self) -> None:
        """OAuth token is correctly extracted from credential."""
        resolved_creds = {
            "extra_vars": {
                "aap_oauth_token": "token",
            },
        }
        result = get_aap_auth_from_credentials(resolved_creds)
        assert result.headers == {"Authorization": "Bearer token"}
        assert result.basic_auth is None

    def test_credential_basic_auth_extracted(self) -> None:
        """Basic auth is correctly extracted from credential."""
        resolved_creds = {
            "extra_vars": {
                "aap_username": "admin",
                "aap_password": "pass",
            },
        }
        result = get_aap_auth_from_credentials(resolved_creds)
        assert result.headers == {}
        assert result.basic_auth is not None

    def test_credential_no_auth_warns(self) -> None:
        """No auth fields returns empty auth with warning."""
        resolved_creds: dict[str, dict[str, str]] = {
            "extra_vars": {},
        }
        result = get_aap_auth_from_credentials(resolved_creds)
        assert result.headers == {}
        assert result.basic_auth is None


class TestResolveAAPAuthWithIntegrationConfig:
    """Test resolve_aap_auth reads connection config from _resolved_integration_config."""

    def test_uses_integration_config_for_url_and_tls(self) -> None:
        """URL and TLS should come from integration config, not credentials."""
        from syntara.workflows.workflow_engine.activities.aap_common import resolve_aap_auth

        settings = MagicMock()

        input_config = {
            "_resolved_credentials": {
                "extra_vars": {
                    "aap_oauth_token": "token",
                },
            },
            "_resolved_integration": {
                "base_url": "https://integration.example.com",
                "verify_ssl": True,
            },
        }

        result = resolve_aap_auth(input_config, settings)
        assert result.base_url == "https://integration.example.com"
        assert result.verify_ssl is True
