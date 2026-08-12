"""Unit tests for Identity Provider OIDC SQLModel.

This file contains comprehensive tests for the Identity Provider OIDC model.

Tests cover:
- OIDC Configuration (creation).
"""

import pytest
from pydantic import ValidationError

from syntara.identity_providers.models import OIDCConfiguration


def _make_oidc_config(**overrides: object) -> OIDCConfiguration:
    """Build an OIDCConfiguration with sensible defaults."""
    defaults: dict[str, object] = {
        "issuer_url": "https://idp.example.com",
        "client_id": "client-id",
        "client_secret": "client-secret",
        "redirect_uri": "https://app.example.com/callback",
    }
    return OIDCConfiguration(**(defaults | overrides))


def test_oidc_configuration_with_auto_discovery_enabled() -> None:
    """Test creating an OIDC configuration with auto discovery enabled."""
    oidc_configuration = _make_oidc_config(
        enable_rp_initiated_logout=True,
        auto_discovery=True,
    )

    assert str(oidc_configuration.issuer_url) == "https://idp.example.com/"
    assert oidc_configuration.client_id == "client-id"
    assert oidc_configuration.client_secret == "client-secret"  # noqa: S105
    assert str(oidc_configuration.redirect_uri) == "https://app.example.com/callback"
    assert oidc_configuration.enable_rp_initiated_logout is True
    assert oidc_configuration.auto_discovery is True
    assert oidc_configuration.authorization_endpoint is None
    assert oidc_configuration.token_endpoint is None
    assert oidc_configuration.jwks_uri is None


def test_oidc_configuration_with_manual_endpoints_provided() -> None:
    """Test creating an OIDC configuration with manual endpoints provided."""
    oidc_configuration = _make_oidc_config(
        enable_rp_initiated_logout=True,
        auto_discovery=False,
        authorization_endpoint="https://idp.example.com/auth",
        token_endpoint="https://idp.example.com/token",  # noqa: S106
        jwks_uri="https://idp.example.com/jwks",
    )

    assert oidc_configuration.auto_discovery is False
    assert str(oidc_configuration.authorization_endpoint) == "https://idp.example.com/auth"
    assert str(oidc_configuration.jwks_uri) == "https://idp.example.com/jwks"


def test_oidc_configuration_with_manual_endpoints_missing() -> None:
    """Test that missing required manual endpoints raise ValidationError."""
    with pytest.raises(ValidationError, match="token_endpoint is required when auto_discovery is disabled"):
        _make_oidc_config(
            enable_rp_initiated_logout=True,
            auto_discovery=False,
            authorization_endpoint="https://idp.example.com/auth",
            token_endpoint=None,
            jwks_uri="https://idp.example.com/jwks",
        )


def test_oidc_configuration_with_invalid_format_manual_endpoints() -> None:
    """Test that manual endpoints with invalid URL format raise ValidationError."""
    with pytest.raises(ValidationError, match="authorization_endpoint must be a valid URL"):
        _make_oidc_config(
            enable_rp_initiated_logout=True,
            auto_discovery=False,
            authorization_endpoint="authorization_endpoint",
            token_endpoint="https://idp.example.com/token",  # noqa: S106
            jwks_uri="https://idp.example.com/jwks",
        )


def test_oidc_configuration_invalid_issuer_url() -> None:
    """Test that an invalid issuer URL raises ValidationError."""
    with pytest.raises(ValidationError, match="issuer_url must be a valid URL"):
        _make_oidc_config(issuer_url="not-a-url")


def test_oidc_configuration_issuer_url_preserves_trailing_slash() -> None:
    """Test that issuer URL trailing slash is preserved (significant for OIDC)."""
    config = _make_oidc_config(issuer_url="https://idp.example.com/")
    assert str(config.issuer_url) == "https://idp.example.com/"


def test_oidc_configuration_invalid_idp_type() -> None:
    """Test that an unknown idp_type raises ValidationError."""
    with pytest.raises(ValidationError, match="Unknown idp_type"):
        _make_oidc_config(idp_type="unknown-provider")


def test_oidc_configuration_valid_idp_type_aap() -> None:
    """Test that known idp_type 'aap' is accepted."""
    config = _make_oidc_config(idp_type="aap")

    assert config.idp_type == "aap"


def test_oidc_configuration_valid_idp_type_custom() -> None:
    """Test that known idp_type 'custom' is accepted."""
    config = _make_oidc_config(idp_type="custom")

    assert config.idp_type == "custom"


def test_oidc_configuration_invalid_group_jmespath_expression() -> None:
    """Test that an invalid JMESPath expression raises ValidationError."""
    with pytest.raises(ValidationError, match="Invalid group extraction expression"):
        _make_oidc_config(group_jmespath_expression="[invalid-jmespath")


def test_oidc_configuration_valid_group_jmespath_expression() -> None:
    """Test that a valid JMESPath expression is accepted."""
    config = _make_oidc_config(group_jmespath_expression="groups[*].name")

    assert config.group_jmespath_expression == "groups[*].name"


def test_oidc_configuration_aap_role_mapping_requires_aap_type() -> None:
    """Test that aap_role_mapping_enabled requires idp_type='aap'."""
    with pytest.raises(ValidationError, match="aap_role_mapping_enabled requires idp_type to be 'aap'"):
        _make_oidc_config(aap_role_mapping_enabled=True, idp_type="custom")


def test_oidc_configuration_aap_role_mapping_with_aap_type() -> None:
    """Test that aap_role_mapping_enabled is accepted when idp_type='aap'."""
    config = _make_oidc_config(aap_role_mapping_enabled=True, idp_type="aap")

    assert config.aap_role_mapping_enabled is True
    assert config.idp_type == "aap"


def test_oidc_configuration_optional_manual_endpoints_invalid_url() -> None:
    """Test that optional manual endpoints with invalid URL format raise ValidationError."""
    with pytest.raises(ValidationError, match="userinfo_endpoint must be a valid URL"):
        _make_oidc_config(
            auto_discovery=False,
            authorization_endpoint="https://idp.example.com/auth",
            token_endpoint="https://idp.example.com/token",  # noqa: S106
            jwks_uri="https://idp.example.com/jwks",
            userinfo_endpoint="not-a-url",
        )


def test_oidc_configuration_with_optional_manual_endpoints() -> None:
    """Test creating an OIDC configuration with all optional manual endpoints."""
    config = _make_oidc_config(
        auto_discovery=False,
        authorization_endpoint="https://idp.example.com/auth",
        token_endpoint="https://idp.example.com/token",  # noqa: S106
        jwks_uri="https://idp.example.com/jwks",
        userinfo_endpoint="https://idp.example.com/userinfo",
        end_session_endpoint="https://idp.example.com/logout",
    )

    assert str(config.userinfo_endpoint) == "https://idp.example.com/userinfo"
    assert str(config.end_session_endpoint) == "https://idp.example.com/logout"


def test_oidc_configuration_default_values() -> None:
    """Test that OIDCConfiguration defaults are applied correctly."""
    config = _make_oidc_config()

    assert config.auto_discovery is True
    assert config.scopes == "openid profile email"
    assert config.enable_rp_initiated_logout is False
    assert config.allow_all_authenticated is False
    assert config.aap_role_mapping_enabled is False
    assert config.disable_tls_verify is False
    assert config.idp_type is None
    assert config.group_jmespath_expression is None
    assert config.group_mapping_entries == []
