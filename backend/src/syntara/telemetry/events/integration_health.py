"""Periodic integration health status event.

Emitted alongside system analytics to provide insight into
configured integration connectivity and health.
"""

from pydantic import Field
from sqlmodel import SQLModel

from syntara.telemetry.events.base import BaseTelemetryEvent


class IntegrationInfo(SQLModel):
    """Per-integration-type count breakdown by status."""

    enabled: int = Field(default=0, description="Enabled integrations of this type")
    disabled: int = Field(default=0, description="Disabled integrations of this type")


class IntegrationHealth(SQLModel):
    """Integration health: per-type counts and aggregate total."""

    items: dict[str, IntegrationInfo] = Field(
        default_factory=dict,
        description="Integration type to enabled/disabled counts mapping",
    )
    total: int = Field(default=0, description="Total configured integrations")


class IdentityProviderInfo(SQLModel):
    """Per-provider-type count breakdown by status."""

    enabled: int = Field(default=0, description="Enabled identity providers of this type")
    disabled: int = Field(default=0, description="Disabled identity providers of this type")


class IdentityProviderHealth(SQLModel):
    """Identity provider health: per-type counts and aggregate total."""

    items: dict[str, IdentityProviderInfo] = Field(
        default_factory=dict,
        description="Provider type to enabled/disabled counts mapping",
    )
    total: int = Field(default=0, description="Total configured identity providers")


class CredentialInfo(SQLModel):
    """Per-type credential count breakdown by status."""

    enabled: int = Field(default=0, description="Enabled credentials of this type")
    disabled: int = Field(default=0, description="Disabled credentials of this type")


class CredentialHealth(SQLModel):
    """Credential health: per-type counts and aggregate totals."""

    items: dict[str, CredentialInfo] = Field(
        default_factory=dict,
        description="Credential type to enabled/disabled counts mapping",
    )
    total: int = Field(default=0, description="Total configured credentials")
    enabled: int = Field(default=0, description="Total enabled credentials")
    disabled: int = Field(default=0, description="Total disabled credentials")


class IntegrationHealthEvent(BaseTelemetryEvent):
    """Periodic health status event for configured integrations.

    Snapshot of provider connectivity and health state.
    Emitted at the same interval as system analytics.
    """

    integrations: IntegrationHealth = Field(
        default_factory=IntegrationHealth,
        description="Integration health status",
    )
    identity_providers: IdentityProviderHealth = Field(
        default_factory=IdentityProviderHealth,
        description="Identity provider health status",
    )
    credentials: CredentialHealth = Field(
        default_factory=CredentialHealth,
        description="Credential health status",
    )
