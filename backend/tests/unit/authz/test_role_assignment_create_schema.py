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


class TestRoleAssignmentCreateProjectPattern:
    """project_pattern is optional, exclusive with project_id and syntax-checked."""

    def test_pattern_only_valid(self) -> None:
        body = RoleAssignmentCreate(principal_id=uuid4(), role_name="no-script", project_pattern="pay*")
        assert body.project_pattern == "pay*"
        assert body.project_id is None

    def test_pattern_and_project_id_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Provide project_id or project_pattern, not both"):
            RoleAssignmentCreate(
                principal_id=uuid4(), role_name="no-script", project_id=uuid4(), project_pattern="pay*"
            )

    def test_pattern_without_wildcard_rejected(self) -> None:
        with pytest.raises(ValidationError, match="use project_id for a single project"):
            RoleAssignmentCreate(principal_id=uuid4(), role_name="no-script", project_pattern="payments")

    @pytest.mark.parametrize("pattern", ["*", "**"])
    def test_match_everything_rejected(self, pattern: str) -> None:
        with pytest.raises(ValidationError, match="matches every project"):
            RoleAssignmentCreate(principal_id=uuid4(), role_name="no-script", project_pattern=pattern)

    @pytest.mark.parametrize("pattern", ["pay%", "pay?*", "pay *", "pay.*"])
    def test_disallowed_characters_rejected(self, pattern: str) -> None:
        with pytest.raises(ValidationError, match="may only contain letters"):
            RoleAssignmentCreate(principal_id=uuid4(), role_name="no-script", project_pattern=pattern)
