"""Association tables for approval request approvers.

Many-to-many relationships:
- approval_requests ↔ users (via approval_approver_users)
- approval_requests ↔ groups (via approval_approver_groups)
"""

from uuid import UUID

from sqlmodel import Field, SQLModel


class ApprovalApproverUser(SQLModel, table=True):
    """Many-to-many association: approval_requests ↔ users.

    Links an approval request to a user who is authorized to approve it.
    When a user is deleted, the association is removed (CASCADE).
    """

    __tablename__ = "approval_approver_users"

    approval_id: UUID = Field(
        foreign_key="approval_requests.id",
        primary_key=True,
        ondelete="CASCADE",
    )
    user_id: UUID = Field(
        foreign_key="users.id",
        primary_key=True,
        ondelete="CASCADE",
    )


class ApprovalApproverGroup(SQLModel, table=True):
    """Many-to-many association: approval_requests ↔ groups.

    Links an approval request to a group whose members are authorized to approve it.
    When a group is deleted, the association is removed (CASCADE).
    """

    __tablename__ = "approval_approver_groups"

    approval_id: UUID = Field(
        foreign_key="approval_requests.id",
        primary_key=True,
        ondelete="CASCADE",
    )
    group_id: UUID = Field(
        foreign_key="groups.id",
        primary_key=True,
        ondelete="CASCADE",
    )
