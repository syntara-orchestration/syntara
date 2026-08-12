"""Unit tests for the RoleAssignmentCreate request schema XOR validator."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from syntara.authz.role_assignment_router import RoleAssignmentCreate


class TestRoleAssignmentCreateXOR:
    """Pydantic model_validator enforces exactly one of principal_id / group_id."""

    def test_principal_id_only_valid(self) -> None:
        body = RoleAssignmentCreate(principal_id=uuid4(), role_name="user")
        assert body.principal_id is not None
        assert body.group_id is None

    def test_group_id_only_valid(self) -> None:
        body = RoleAssignmentCreate(group_id=uuid4(), role_name="user")
        assert body.group_id is not None
        assert body.principal_id is None

    def test_both_ids_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Exactly one"):
            RoleAssignmentCreate(principal_id=uuid4(), group_id=uuid4(), role_name="user")

    def test_neither_id_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Exactly one"):
            RoleAssignmentCreate(role_name="user")
