"""Secret storage models for pluggable secret storage.

The secrets table is a routing layer — it contains zero secret values.
The encrypted_secrets table stores AES-256-GCM encrypted field data
for the DatabaseBackend. Both tables are shared infrastructure used
by Credentials (GA), Application Settings, and OIDC configs (post-GA).
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import DateTime, Field, SQLModel

_SERVER_NOW = text("now()")
_TIMESTAMP_TYPE = DateTime(timezone=True)


class Secret(SQLModel, table=True):
    """Routing record for the StorageBackend Protocol.

    Contains zero secret values — only an ID and timestamps.
    For GA, the secret's UUID is sufficient to locate its data
    in the encrypted_secrets table. Post-GA, storage_backend
    and backend_config_id columns will be added via migration
    when multi-backend support lands.
    """

    __tablename__ = "secrets"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(
        sa_type=_TIMESTAMP_TYPE,  # type: ignore[call-overload]
        sa_column_kwargs={"server_default": _SERVER_NOW},
    )
    updated_at: datetime = Field(
        sa_type=_TIMESTAMP_TYPE,  # type: ignore[call-overload]
        sa_column_kwargs={"server_default": _SERVER_NOW, "onupdate": _SERVER_NOW},
    )


class EncryptedSecret(SQLModel, table=True):
    """Backend storage for DatabaseBackend.

    Stores AES-256-GCM encrypted field data as JSONB.
    1:1 relationship with secrets table for GA (one encrypted payload per secret).

    The encrypted_data dict maps field names to base64-encoded ciphertext:
    {"field_name": "base64(nonce_12 + ciphertext + tag_16)", ...}
    """

    __tablename__ = "encrypted_secrets"
    __table_args__ = (UniqueConstraint("secret_id"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    secret_id: UUID = Field(
        foreign_key="secrets.id",
        nullable=False,
        index=True,
        description="FK to secrets routing table (1:1 for GA)",
    )
    encrypted_data: dict[str, str] = Field(
        sa_type=JSONB,
        description="Encrypted field values {field_name: base64_ciphertext}",
    )
    created_at: datetime = Field(
        sa_type=_TIMESTAMP_TYPE,  # type: ignore[call-overload]
        sa_column_kwargs={"server_default": _SERVER_NOW},
    )
    updated_at: datetime = Field(
        sa_type=_TIMESTAMP_TYPE,  # type: ignore[call-overload]
        sa_column_kwargs={"server_default": _SERVER_NOW, "onupdate": _SERVER_NOW},
    )
