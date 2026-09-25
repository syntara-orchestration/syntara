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
export const Approvals = lazy(() => import('../routes/approvals/Approvals'))
export const AccessManagement = lazy(() =>
  import('../routes/access-management/AccessManagement').then((m) => ({ default: m.AccessManagement }))
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
export const ProjectDetail = lazy(() =>
  import('../routes/access-management/projects/ProjectDetail').then((m) => ({
    default: m.ProjectDetail,
  }))
)
export const ServiceAccountDetail = lazy(() =>
  import('../routes/access-management/service-accounts/ServiceAccountDetail').then((m) => ({
    default: m.ServiceAccountDetail,
  }))
)
export const Credentials = lazy(() => import('../routes/configuration/credentials/Credentials'))
export const CredentialDetail = lazy(() => import('../routes/configuration/credentials/CredentialDetail'))
