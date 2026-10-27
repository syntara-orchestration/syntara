import { lazy } from 'react'

export const Workflows = lazy(() => import('../routes/workflows/Workflows'))
export const BuilderNew = lazy(() => import('../routes/builder/BuilderNew'))
export const BuilderEdit = lazy(() => import('../routes/builder/BuilderEdit'))
export const Executions = lazy(() => import('../routes/executions/Executions'))
export const ExecutionDetail = lazy(() => import('../routes/executions/ExecutionDetail'))
export const IntegrationForm = lazy(() =>
  import('../routes/configuration/integrations/form/IntegrationForm').then((m) => ({ default: m.IntegrationForm }))
)
export const Integrations = lazy(() => import('../routes/configuration/integrations/Integrations'))
export const IntegrationDetail = lazy(() =>
  import('../routes/configuration/integrations/IntegrationDetail').then((m) => ({ default: m.IntegrationDetail }))
)
export const EditIntegration = lazy(() =>
  import('../routes/configuration/integrations/EditIntegrationForm').then((m) => ({ default: m.EditIntegrationForm }))
)
export const Settings = lazy(() => import('../routes/configuration/settings/Settings'))
export const SettingsCategoryRoute = lazy(() =>
  import('../routes/configuration/settings/SettingsCategoryRoute').then((m) => ({ default: m.SettingsCategoryRoute }))
)
export const Glossary = lazy(() => import('../routes/documentation/glossary/Glossary'))
export const FeatureFlagDemo = lazy(() =>
  import('../routes/feature-flags/feature-flag-demo-page').then((m) => ({ default: m.FeatureFlagDemo }))
)
export const Approvals = lazy(() => import('../routes/approvals/Approvals'))
export const AccessManagement = lazy(() =>
  import('../routes/access-management/AccessManagement').then((m) => ({ default: m.AccessManagement }))
)
export const AccessManagementCheckAccessRoute = lazy(() =>
  import('../routes/access-management/AccessManagementRouteTabs').then((m) => ({
    default: m.AccessManagementCheckAccessRoute,
  }))
)
export const AccessManagementTokenRevocationRoute = lazy(() =>
  import('../routes/access-management/AccessManagementRouteTabs').then((m) => ({
    default: m.AccessManagementTokenRevocationRoute,
  }))
)
export const UsersTab = lazy(() =>
  import('../routes/access-management/UsersTab').then((m) => ({ default: m.UsersTab }))
)
export const GroupsTab = lazy(() =>
  import('../routes/access-management/GroupsTab').then((m) => ({ default: m.GroupsTab }))
)
export const ProjectsTab = lazy(() =>
  import('../routes/access-management/ProjectsTab').then((m) => ({ default: m.ProjectsTab }))
)
export const PoliciesTab = lazy(() => import('../routes/access/PoliciesTab').then((m) => ({ default: m.PoliciesTab })))
export const RolesTab = lazy(() => import('../routes/access/RolesTab').then((m) => ({ default: m.RolesTab })))
export const AssignmentsTab = lazy(() =>
  import('../routes/access/AssignmentsTab').then((m) => ({ default: m.AssignmentsTab }))
)
export const ServiceAccountsTab = lazy(() =>
  import('../routes/access-management/service-accounts/ServiceAccountsTab').then((m) => ({
    default: m.ServiceAccountsTab,
  }))
)
export const Authentication = lazy(() => import('../routes/access-management/authentication/Authentication'))
export const AddIdentityProvider = lazy(() =>
  import('../routes/access-management/authentication/identity-providers/AddIdentityProvider').then((m) => ({
    default: m.AddIdentityProvider,
  }))
)
export const IdentityProviderDetail = lazy(() =>
  import('../routes/access-management/authentication/identity-providers/IdentityProviderDetail').then((m) => ({
    default: m.IdentityProviderDetail,
  }))
)
export const EditIdentityProvider = lazy(() =>
  import('../routes/access-management/authentication/identity-providers/EditIdentityProvider').then((m) => ({
    default: m.EditIdentityProvider,
  }))
)
export const EditGroupMapping = lazy(() =>
  import('../routes/access-management/authentication/identity-providers/EditGroupMapping').then((m) => ({
    default: m.EditGroupMapping,
  }))
)
export const CreateUser = lazy(() =>
  import('../routes/access-management/users/CreateUser').then((m) => ({
    default: m.CreateUser,
  }))
)
export const UserDetail = lazy(() =>
  import('../routes/access-management/users/UserDetail').then((m) => ({
    default: m.UserDetail,
  }))
)
export const UserDetailTabRoute = lazy(() =>
  import('../routes/access-management/users/UserDetail').then((m) => ({
    default: m.UserDetailTabRoute,
  }))
)
export const MyProfile = lazy(() =>
  import('../routes/access-management/users/MyProfile').then((m) => ({
    default: m.MyProfile,
  }))
)
export const EditUser = lazy(() =>
  import('../routes/access-management/users/EditUser').then((m) => ({
    default: m.EditUser,
  }))
)
export const TransferIdentityWizard = lazy(() =>
  import('../routes/access-management/users/TransferIdentityWizard').then((m) => ({
    default: m.TransferIdentityWizard,
  }))
)
export const GroupDetail = lazy(() =>
  import('../routes/access-management/groups/GroupDetail').then((m) => ({
    default: m.GroupDetail,
  }))
)
export const GroupDetailDetailsTabRoute = lazy(() =>
  import('../routes/access-management/groups/GroupDetail').then((m) => ({ default: m.GroupDetailDetailsTabRoute }))
)
export const GroupDetailMembersTabRoute = lazy(() =>
  import('../routes/access-management/groups/GroupDetail').then((m) => ({ default: m.GroupDetailMembersTabRoute }))
)
export const GroupDetailAssignmentsTabRoute = lazy(() =>
  import('../routes/access-management/groups/GroupDetail').then((m) => ({
    default: m.GroupDetailAssignmentsTabRoute,
  }))
)
export const GroupDetailUnknownTabRoute = lazy(() =>
  import('../routes/access-management/groups/GroupDetail').then((m) => ({ default: m.GroupDetailUnknownTabRoute }))
)
export const ProjectDetail = lazy(() =>
  import('../routes/access-management/projects/ProjectDetail').then((m) => ({
    default: m.ProjectDetail,
  }))
)
export const ProjectDetailDetailsTabRoute = lazy(() =>
  import('../routes/access-management/projects/ProjectDetail').then((m) => ({
    default: m.ProjectDetailDetailsTabRoute,
  }))
)
export const ProjectDetailWorkflowsTabRoute = lazy(() =>
  import('../routes/access-management/projects/ProjectDetail').then((m) => ({
    default: m.ProjectDetailWorkflowsTabRoute,
  }))
)
export const ProjectDetailAssignmentsTabRoute = lazy(() =>
  import('../routes/access-management/projects/ProjectDetail').then((m) => ({
    default: m.ProjectDetailAssignmentsTabRoute,
  }))
)
export const ProjectDetailUnknownTabRoute = lazy(() =>
  import('../routes/access-management/projects/ProjectDetail').then((m) => ({
    default: m.ProjectDetailUnknownTabRoute,
  }))
)
export const IdentityProviderDetailsTabRoute = lazy(() =>
  import('../routes/access-management/authentication/identity-providers/IdentityProviderDetail').then((m) => ({
    default: m.IdentityProviderDetailsTabRoute,
  }))
)
export const IdentityProviderGroupMappingTabRoute = lazy(() =>
  import('../routes/access-management/authentication/identity-providers/IdentityProviderDetail').then((m) => ({
    default: m.IdentityProviderGroupMappingTabRoute,
  }))
)
export const IdentityProviderUnknownTabRoute = lazy(() =>
  import('../routes/access-management/authentication/identity-providers/IdentityProviderDetail').then((m) => ({
    default: m.IdentityProviderUnknownTabRoute,
  }))
)
export const ServiceAccountDetail = lazy(() =>
  import('../routes/access-management/service-accounts/ServiceAccountDetail').then((m) => ({
    default: m.ServiceAccountDetail,
  }))
)
export const Credentials = lazy(() => import('../routes/configuration/credentials/Credentials'))
export const CredentialDetail = lazy(() => import('../routes/configuration/credentials/CredentialDetail'))
export const CredentialDetailsTabRoute = lazy(() =>
  import('../routes/configuration/credentials/CredentialDetail').then((m) => ({
    default: m.CredentialDetailsTabRoute,
  }))
)
export const CredentialWorkflowsTabRoute = lazy(() =>
  import('../routes/configuration/credentials/CredentialDetail').then((m) => ({
    default: m.CredentialWorkflowsTabRoute,
  }))
)
export const CredentialIntegrationsTabRoute = lazy(() =>
  import('../routes/configuration/credentials/CredentialDetail').then((m) => ({
    default: m.CredentialIntegrationsTabRoute,
  }))
)
