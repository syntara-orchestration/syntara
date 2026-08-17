"""IdP group mapping entry model.

Maps identity provider group values to Syntara groups in a dedicated table,
enabling FK constraints and ON DELETE CASCADE.
"""

from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class IdpGroupMappingEntry(SQLModel, table=True):
    """Maps a single IdP group value to a Syntara group."""

    __tablename__ = "idp_group_mapping_entries"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    identity_provider_id: UUID = Field(foreign_key="identity_providers.id", ondelete="CASCADE", index=True)
    idp_group_value: str = Field(min_length=1)
    mapped_group_id: UUID = Field(foreign_key="groups.id", ondelete="CASCADE", index=True)

    __table_args__ = (UniqueConstraint("identity_provider_id", "idp_group_value", "mapped_group_id"),)


class IdpGroupMappingEntryRead(SQLModel):
    """Response schema for a group mapping entry."""

    id: UUID
    idp_group_value: str
    mapped_group_id: UUID


class IdpGroupMappingEntryCreate(SQLModel):
    """Create schema for a group mapping entry."""

    idp_group_value: str = Field(min_length=1)
    mapped_group_id: UUID
