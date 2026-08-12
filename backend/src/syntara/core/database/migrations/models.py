"""Application database models."""

from __future__ import annotations

from syntara.agent_orchestrator.models.invocation import Invocation
from syntara.agent_orchestrator.token_manager.models import TokenUsageRecord, UserTokenConfig
from syntara.approvals.models.approval_request import ApprovalRequest
from syntara.audit.outbox.models import AuditOutboxRecord, AuditTableMetadata
from syntara.auth.models.global_revocation_timestamp import GlobalRevocationTimestamp
from syntara.auth.session.models import RefreshSession
from syntara.authz.models import (
    Policy,
    Project,
    Role,
    RoleAssignment,
)
from syntara.core.models import User
from syntara.core.models.group import Group
from syntara.core.models.installation import Installation
from syntara.core.models.principal import Principal
from syntara.core.models.secret import EncryptedSecret, Secret
from syntara.credentials.models.credential import Credential
from syntara.credentials.models.credential_type import CredentialType
from syntara.files.models import FileMetadata
from syntara.identity_providers.models.identity_provider import IdentityProvider
from syntara.identity_providers.models.idp_group_mapping import IdpGroupMappingEntry
from syntara.integrations.models.integration import Integration, IntegrationProjectAssignment
from syntara.service_accounts.models.service_account import ServiceAccount
from syntara.service_accounts.models.service_account_credential import ServiceAccountCredential
from syntara.settings.models.runtime_setting import RuntimeSetting
from syntara.settings.models.setting_category import SettingCategoryModel
from syntara.tool_manager.models.rate_limit_config import RateLimit
from syntara.tool_manager.models.tool import Tool, ToolParameter
from syntara.tool_manager.models.tool_execution import ToolExecution
from syntara.tool_manager.models.usage_counter import UsageCounter
from syntara.workflows.models import WebhookTrigger, Workflow, WorkflowVersion
from syntara.workflows.models.activity_execution import ActivityExecution
from syntara.workflows.models.execution import Execution

# Ensure models are registered with SQLModel metadata

ALL_MODELS = [
    Principal,
    GlobalRevocationTimestamp,
    Installation,
    Invocation,
    User,
    Workflow,
    WorkflowVersion,
    Execution,
    ActivityExecution,
    Tool,
    ToolParameter,
    RateLimit,
    ToolExecution,
    UsageCounter,
    UserTokenConfig,
    TokenUsageRecord,
    FileMetadata,
    ApprovalRequest,
    IdentityProvider,
    IdpGroupMappingEntry,
    Integration,
    IntegrationProjectAssignment,
    RuntimeSetting,
    SettingCategoryModel,
    Secret,
    EncryptedSecret,
    Credential,
    CredentialType,
    ServiceAccount,
    ServiceAccountCredential,
    Project,
    Group,
    Role,
    Policy,
    RoleAssignment,
    RefreshSession,
    WebhookTrigger,
    AuditOutboxRecord,
    AuditTableMetadata,
]
