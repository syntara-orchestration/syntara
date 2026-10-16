"""Association tables for form prompt responders.

Many-to-many relationships:
- form_prompts ↔ users (via form_prompt_responder_users)
- form_prompts ↔ groups (via form_prompt_responder_groups)
"""

from uuid import UUID

from sqlmodel import Field, SQLModel


class FormPromptResponderUser(SQLModel, table=True):
    """Many-to-many association: form_prompts ↔ users.

    Links a form prompt to a user who is authorized to respond to it.
    When a user is deleted, the association is removed (CASCADE).
    """

    __tablename__ = "form_prompt_responder_users"

    form_prompt_id: UUID = Field(
        foreign_key="form_prompts.id",
        primary_key=True,
        ondelete="CASCADE",
    )
    user_id: UUID = Field(
        foreign_key="users.id",
        primary_key=True,
        ondelete="CASCADE",
    )


class FormPromptResponderGroup(SQLModel, table=True):
    """Many-to-many association: form_prompts ↔ groups.

    Links a form prompt to a group whose members are authorized to respond to it.
    When a group is deleted, the association is removed (CASCADE).
    """

    __tablename__ = "form_prompt_responder_groups"

    form_prompt_id: UUID = Field(
        foreign_key="form_prompts.id",
        primary_key=True,
        ondelete="CASCADE",
    )
    group_id: UUID = Field(
        foreign_key="groups.id",
        primary_key=True,
        ondelete="CASCADE",
    )
