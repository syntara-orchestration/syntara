"""Lock FK ondelete rules for user/group hard delete.

Mis-setting ON DELETE CASCADE on a non-user-scoped table would destroy
live resources when a user or group is removed. These assertions are the
regression net for that class of mistake.
"""

from typing import Any

from sqlalchemy import Column

from syntara.agent_orchestrator.token_manager.models import TokenUsageRecord, UserTokenConfig
from syntara.approvals.models.approval_approvers import ApprovalApproverUser
from syntara.auth.session.models import RefreshSession
from syntara.core.models.group import Group, user_groups, user_idp_groups
from syntara.core.models.user_identity import UserIdentity
from syntara.workflows.models.workflow import Workflow


def _ondelete(column: Column[Any]) -> str | None:
    fks = list(column.foreign_keys)
    assert len(fks) == 1, column
    return fks[0].ondelete


def _referenced_table(column: Column[Any]) -> str:
    fks = list(column.foreign_keys)
    assert len(fks) == 1, column
    return fks[0].column.table.name


def test_user_scoped_fks_cascade() -> None:
    """Membership, identity, session, token config, and approver rows go with the user."""
    assert _ondelete(user_groups.c.user_id) == "CASCADE"
    assert _ondelete(user_idp_groups.c.user_id) == "CASCADE"
    assert _ondelete(UserIdentity.__table__.c.user_id) == "CASCADE"
    assert _ondelete(RefreshSession.__table__.c.user_id) == "CASCADE"
    assert _ondelete(UserTokenConfig.__table__.c.user_id) == "CASCADE"
    assert _ondelete(ApprovalApproverUser.__table__.c.user_id) == "CASCADE"


def test_token_usage_set_null_and_nullable() -> None:
    """Spend history must survive user deletion (install-wide accounting)."""
    column = TokenUsageRecord.__table__.c.user_id
    assert column.nullable is True
    assert _ondelete(column) == "SET NULL"


def test_group_created_by_set_null() -> None:
    """A group outlives its creator."""
    column = Group.__table__.c.created_by
    assert column.nullable is True
    assert _ondelete(column) == "SET NULL"


def test_owned_resources_do_not_reference_users_id() -> None:
    """created_by/updated_by point at principals, so user delete cannot cascade into owned work."""
    created = Workflow.__table__.c.created_by
    updated = Workflow.__table__.c.updated_by
    assert _referenced_table(created) == "principals"
    assert _ondelete(created) != "CASCADE"
    assert _referenced_table(updated) == "principals"
    assert _ondelete(updated) != "CASCADE"
