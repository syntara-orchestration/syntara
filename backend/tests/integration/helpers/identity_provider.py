"""Test fixtures and helpers for identity provider tests."""

from uuid import uuid4

from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.identity_providers.models.identity_provider import IdentityProvider


class IdentityProviderCreate:
    """Factory for creating identity providers."""

    def __init__(self, session: AsyncSession, user: User) -> None:
        """Initialize with database session and user."""
        self.session = session
        self.user = user

    async def create(
        self,
        name: str | None = None,
        *,
        enabled: bool = True,
        provider_type: str = "oidc",
    ) -> IdentityProvider:
        """Create a single identity provider."""
        idp = IdentityProvider(
            name=name or f"idp-{uuid4().hex[:8]}",
            enabled=enabled,
            created_by=self.user.id,
            configuration={
                "provider_type": provider_type,
                "issuer_url": "https://idp.example.com",
                "client_id": f"client-{uuid4().hex[:8]}",
                "redirect_uri": "https://app.example.com/callback",
            },
        )
        self.session.add(idp)
        await self.session.flush()
        return idp

    async def create_many(
        self,
        count: int,
        *,
        prefix: str = "idp",
        enabled: bool = True,
        provider_type: str = "oidc",
    ) -> list[IdentityProvider]:
        """Create multiple identity providers."""
        return [await self.create(f"{prefix}-{i}", enabled=enabled, provider_type=provider_type) for i in range(count)]
