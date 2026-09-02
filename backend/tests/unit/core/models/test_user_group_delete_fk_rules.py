"""Lock FK ondelete rules for user/group hard delete.

Mis-setting ON DELETE CASCADE on a non-user-scoped table would destroy
live resources when a user or group is removed. These assertions are the
regression net for that class of mistake.
"""

from typing import Any

from sqlalchemy import Column
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.sql.schema import Table

from syntara.agent_orchestrator.token_manager.models import TokenUsageRecord, UserTokenConfig
from syntara.approvals.models.approval_approvers import ApprovalApproverUser
from syntara.auth.session.models import RefreshSession
from syntara.core.models.group import Group, user_groups, user_idp_groups
from syntara.core.models.user_identity import UserIdentity
from syntara.workflows.models.workflow import Workflow


def _table(model: type[Any]) -> Table:
    table = sa_inspect(model).local_table
    assert isinstance(table, Table)
    return table


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
    assert _ondelete(_table(UserIdentity).c.user_id) == "CASCADE"
    assert _ondelete(_table(RefreshSession).c.user_id) == "CASCADE"
    assert _ondelete(_table(UserTokenConfig).c.user_id) == "CASCADE"
    assert _ondelete(_table(ApprovalApproverUser).c.user_id) == "CASCADE"


def test_token_usage_set_null_and_nullable() -> None:
    """Spend history must survive user deletion (install-wide accounting)."""
    column = _table(TokenUsageRecord).c.user_id
    assert column.nullable is True
    assert _ondelete(column) == "SET NULL"


def test_group_created_by_set_null() -> None:
    """A group outlives its creator."""
    column = _table(Group).c.created_by
    assert column.nullable is True
    assert _ondelete(column) == "SET NULL"


def test_owned_resources_do_not_reference_users_id() -> None:
    """created_by/updated_by point at principals, so user delete cannot cascade into owned work."""
    created = _table(Workflow).c.created_by
    updated = _table(Workflow).c.updated_by
    assert _referenced_table(created) == "principals"
    assert _ondelete(created) != "CASCADE"
    assert _referenced_table(updated) == "principals"
    assert _ondelete(updated) != "CASCADE"
