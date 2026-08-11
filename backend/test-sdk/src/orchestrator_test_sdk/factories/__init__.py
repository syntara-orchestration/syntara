"""Factory fixtures for Nexus E2E tests."""

from orchestrator_test_sdk.factories.credentials import (
    CredentialFactory,
    create_credential,
    get_basic_auth_type_id,
    get_bearer_token_type_id,
)
from orchestrator_test_sdk.factories.groups import GroupFactory, add_to_group, create_group, remove_from_group
from orchestrator_test_sdk.factories.identity_providers import IdentityProviderFactory, identity_provider_factory
from orchestrator_test_sdk.factories.policies import PolicyFactory, create_policy
from orchestrator_test_sdk.factories.projects import (
    AssignProjectRoleFactory,
    ProjectFactory,
    ProjectRoleFactory,
    assign_project_role_to_group,
    assign_project_role_to_user,
    create_project,
    create_project_role,
)
from orchestrator_test_sdk.factories.roles import RoleFactory, create_role
from orchestrator_test_sdk.factories.users import (
    UserFactory,
    UserRoleAssignmentFactory,
    assign_system_role,
    create_user,
)
from orchestrator_test_sdk.factories.workflows import WorkflowFactory, create_workflow

__all__ = [
    "AssignProjectRoleFactory",
    "CredentialFactory",
    "GroupFactory",
    "IdentityProviderFactory",
    "PolicyFactory",
    "ProjectFactory",
    "ProjectRoleFactory",
    "RoleFactory",
    "UserFactory",
    "UserRoleAssignmentFactory",
    "WorkflowFactory",
    "add_to_group",
    "assign_project_role_to_group",
    "assign_project_role_to_user",
    "assign_system_role",
    "create_credential",
    "create_group",
    "create_policy",
    "create_project",
    "create_project_role",
    "create_role",
    "create_user",
    "create_workflow",
    "get_basic_auth_type_id",
    "get_bearer_token_type_id",
    "identity_provider_factory",
    "remove_from_group",
]
