"""Unit tests for IntegrationHealthEvent."""

import pytest

from syntara.telemetry.events.integration_health import (
    CredentialHealth,
    CredentialInfo,
    IdentityProviderHealth,
    IdentityProviderInfo,
    IntegrationHealth,
    IntegrationHealthEvent,
    IntegrationInfo,
)


class TestIntegrationHealthEvent:
    """Tests for IntegrationHealthEvent model."""

    def test_event_name(self):
        event = IntegrationHealthEvent(entitlement_id="ent-123")
        segment_event = event.to_segment_event()
        assert segment_event["event"] == "integration_health"

    def test_defaults_to_empty_health(self):
        event = IntegrationHealthEvent(entitlement_id="ent-123")
        assert event.integrations.items == {}
        assert event.integrations.total == 0
        assert event.identity_providers.items == {}
        assert event.identity_providers.total == 0
        assert event.credentials.items == {}
        assert event.credentials.total == 0

    def test_segment_properties_structure(self):
        event = IntegrationHealthEvent(
            entitlement_id="ent-123",
            integrations=IntegrationHealth(
                items={
                    "mcp_server": IntegrationInfo(enabled=2, disabled=1),
                },
                total=3,
            ),
            identity_providers=IdentityProviderHealth(
                items={
                    "oidc": IdentityProviderInfo(enabled=1, disabled=0),
                },
                total=1,
            ),
            credentials=CredentialHealth(
                items={
                    "HTTP Bearer Token": CredentialInfo(enabled=1, disabled=1),
                    "SSH Key": CredentialInfo(enabled=0, disabled=1),
                },
                total=3,
                enabled=1,
                disabled=2,
            ),
        )
        props = event.to_segment_event()["properties"]

        integrations = props["integrations"]
        assert integrations["items"]["mcp_server"]["enabled"] == 2
        assert integrations["items"]["mcp_server"]["disabled"] == 1
        assert integrations["total"] == 3

        idp = props["identity_providers"]
        assert idp["items"]["oidc"]["enabled"] == 1
        assert idp["items"]["oidc"]["disabled"] == 0
        assert idp["total"] == 1

        cred = props["credentials"]
        assert cred["items"]["HTTP Bearer Token"]["enabled"] == 1
        assert cred["items"]["HTTP Bearer Token"]["disabled"] == 1
        assert cred["items"]["SSH Key"]["enabled"] == 0
        assert cred["items"]["SSH Key"]["disabled"] == 1
        assert cred["total"] == 3
        assert cred["enabled"] == 1
        assert cred["disabled"] == 2


class TestInfoModels:
    """Tests for per-integration/credential info models."""

    @pytest.mark.parametrize(
        ("model_cls", "kwargs"),
        [
            (IntegrationInfo, {"enabled": 3, "disabled": 1}),
            (IdentityProviderInfo, {"enabled": 2, "disabled": 1}),
            (CredentialInfo, {"enabled": 3, "disabled": 1}),
        ],
    )
    def test_construction(self, model_cls, kwargs):
        info = model_cls(**kwargs)
        for field, value in kwargs.items():
            assert getattr(info, field) == value


class TestHealthModels:
    """Tests for wrapper health models that bundle items and status."""

    def test_integration_health_defaults_to_empty(self):
        health = IntegrationHealth()
        assert health.items == {}
        assert health.total == 0

    def test_identity_provider_health_defaults_to_empty(self):
        health = IdentityProviderHealth()
        assert health.items == {}
        assert health.total == 0

    def test_credential_health_defaults_to_empty(self):
        health = CredentialHealth()
        assert health.items == {}
        assert health.total == 0
        assert health.enabled == 0
        assert health.disabled == 0
