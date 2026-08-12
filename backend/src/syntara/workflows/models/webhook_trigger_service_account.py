"""Association table for webhook trigger ↔ service account authorization.

Many-to-many relationship: webhook_triggers ↔ service_accounts.
When a trigger or service account is deleted, the association is removed (CASCADE).
"""

from uuid import UUID

from sqlmodel import Field, Index, SQLModel


class WebhookTriggerServiceAccount(SQLModel, table=True):
    """Many-to-many association: webhook_triggers ↔ service_accounts.

    Links a webhook trigger to a service account that is authorized to invoke it.
    """

    __tablename__ = "webhook_trigger_service_accounts"

    webhook_trigger_id: UUID = Field(
        foreign_key="webhook_triggers.id",
        primary_key=True,
        ondelete="CASCADE",
    )
    service_account_id: UUID = Field(
        foreign_key="service_accounts.id",
        primary_key=True,
        ondelete="CASCADE",
    )

    __table_args__ = (Index("ix_wt_sa_service_account_id", "service_account_id"),)
