import { render, screen } from '@testing-library/react'
import { Suspense } from 'react'
import { describe, it, vi } from 'vitest'

import * as lazyRouteComponents from './lazyRoutes'

// Stub route components so the test exercises the lazy import mappings without
// pulling in each route's data hooks and page dependencies.
vi.mock('../routes/workflows/Workflows', () => ({ default: () => <div>Workflows</div> }))
vi.mock('../routes/builder/BuilderNew', () => ({ default: () => <div>BuilderNew</div> }))
vi.mock('../routes/builder/BuilderEdit', () => ({ default: () => <div>BuilderEdit</div> }))
vi.mock('../routes/executions/Executions', () => ({ default: () => <div>Executions</div> }))
vi.mock('../routes/executions/ExecutionDetail', () => ({ default: () => <div>ExecutionDetail</div> }))
vi.mock('../routes/configuration/integrations/form/IntegrationForm', () => ({
  IntegrationForm: () => <div>IntegrationForm</div>,
}))
vi.mock('../routes/configuration/integrations/Integrations', () => ({ default: () => <div>Integrations</div> }))
vi.mock('../routes/configuration/integrations/IntegrationDetail', () => ({
  IntegrationDetail: () => <div>IntegrationDetail</div>,
}))
vi.mock('../routes/configuration/integrations/EditIntegrationForm', () => ({
  EditIntegrationForm: () => <div>EditIntegration</div>,
}))
vi.mock('../routes/configuration/settings/Settings', () => ({ default: () => <div>Settings</div> }))
vi.mock('../routes/configuration/settings/SettingsCategoryRoute', () => ({
  SettingsCategoryRoute: () => <div>SettingsCategoryRoute</div>,
}))
vi.mock('../routes/documentation/glossary/Glossary', () => ({ default: () => <div>Glossary</div> }))
vi.mock('../routes/feature-flags/feature-flag-demo-page', () => ({
  FeatureFlagDemo: () => <div>FeatureFlagDemo</div>,
}))
vi.mock('../routes/approvals/Approvals', () => ({ default: () => <div>Approvals</div> }))
vi.mock('../routes/access-management/AccessManagement', () => ({
  AccessManagement: () => <div>AccessManagement</div>,
}))
vi.mock('../routes/access-management/AccessManagementRouteTabs', () => ({
  AccessManagementCheckAccessRoute: () => <div>AccessManagementCheckAccessRoute</div>,
  AccessManagementTokenRevocationRoute: () => <div>AccessManagementTokenRevocationRoute</div>,
}))
vi.mock('../routes/access-management/UsersTab', () => ({ UsersTab: () => <div>UsersTab</div> }))
vi.mock('../routes/access-management/GroupsTab', () => ({ GroupsTab: () => <div>GroupsTab</div> }))
vi.mock('../routes/access-management/ProjectsTab', () => ({ ProjectsTab: () => <div>ProjectsTab</div> }))
vi.mock('../routes/access/PoliciesTab', () => ({ PoliciesTab: () => <div>PoliciesTab</div> }))
vi.mock('../routes/access/RolesTab', () => ({ RolesTab: () => <div>RolesTab</div> }))
vi.mock('../routes/access/AssignmentsTab', () => ({ AssignmentsTab: () => <div>AssignmentsTab</div> }))
vi.mock('../routes/access-management/service-accounts/ServiceAccountsTab', () => ({
  ServiceAccountsTab: () => <div>ServiceAccountsTab</div>,
}))
vi.mock('../routes/access-management/authentication/Authentication', () => ({
  default: () => <div>Authentication</div>,
}))
vi.mock('../routes/access-management/authentication/identity-providers/AddIdentityProvider', () => ({
  AddIdentityProvider: () => <div>AddIdentityProvider</div>,
}))
vi.mock('../routes/access-management/authentication/identity-providers/IdentityProviderDetail', () => ({
  IdentityProviderDetail: () => <div>IdentityProviderDetail</div>,
  IdentityProviderDetailsTabRoute: () => <div>IdentityProviderDetailsTabRoute</div>,
  IdentityProviderGroupMappingTabRoute: () => <div>IdentityProviderGroupMappingTabRoute</div>,
  IdentityProviderUnknownTabRoute: () => <div>IdentityProviderUnknownTabRoute</div>,
}))
vi.mock('../routes/access-management/authentication/identity-providers/EditIdentityProvider', () => ({
  EditIdentityProvider: () => <div>EditIdentityProvider</div>,
}))
vi.mock('../routes/access-management/authentication/identity-providers/EditGroupMapping', () => ({
  EditGroupMapping: () => <div>EditGroupMapping</div>,
}))
vi.mock('../routes/access-management/users/CreateUser', () => ({ CreateUser: () => <div>CreateUser</div> }))
vi.mock('../routes/access-management/users/UserDetail', () => ({
  UserDetail: () => <div>UserDetail</div>,
  UserDetailTabRoute: () => <div>UserDetailTabRoute</div>,
}))
vi.mock('../routes/access-management/users/MyProfile', () => ({ MyProfile: () => <div>MyProfile</div> }))
vi.mock('../routes/access-management/users/EditUser', () => ({ EditUser: () => <div>EditUser</div> }))
vi.mock('../routes/access-management/users/TransferIdentityWizard', () => ({
  TransferIdentityWizard: () => <div>TransferIdentityWizard</div>,
}))
vi.mock('../routes/access-management/groups/GroupDetail', () => ({
  GroupDetail: () => <div>GroupDetail</div>,
  GroupDetailAssignmentsTabRoute: () => <div>GroupDetailAssignmentsTabRoute</div>,
  GroupDetailDetailsTabRoute: () => <div>GroupDetailDetailsTabRoute</div>,
  GroupDetailMembersTabRoute: () => <div>GroupDetailMembersTabRoute</div>,
  GroupDetailUnknownTabRoute: () => <div>GroupDetailUnknownTabRoute</div>,
}))
vi.mock('../routes/access-management/projects/ProjectDetail', () => ({
  ProjectDetail: () => <div>ProjectDetail</div>,
  ProjectDetailAssignmentsTabRoute: () => <div>ProjectDetailAssignmentsTabRoute</div>,
  ProjectDetailDetailsTabRoute: () => <div>ProjectDetailDetailsTabRoute</div>,
  ProjectDetailUnknownTabRoute: () => <div>ProjectDetailUnknownTabRoute</div>,
  ProjectDetailWorkflowsTabRoute: () => <div>ProjectDetailWorkflowsTabRoute</div>,
}))
vi.mock('../routes/access-management/service-accounts/ServiceAccountDetail', () => ({
  ServiceAccountDetail: () => <div>ServiceAccountDetail</div>,
  ServiceAccountDetailDetailsTabRoute: () => <div>ServiceAccountDetailDetailsTabRoute</div>,
  ServiceAccountDetailCredentialsTabRoute: () => <div>ServiceAccountDetailCredentialsTabRoute</div>,
  ServiceAccountDetailAssignmentsTabRoute: () => <div>ServiceAccountDetailAssignmentsTabRoute</div>,
  ServiceAccountDetailUnknownTabRoute: () => <div>ServiceAccountDetailUnknownTabRoute</div>,
}))
vi.mock('../routes/configuration/credentials/Credentials', () => ({ default: () => <div>Credentials</div> }))
vi.mock('../routes/configuration/credentials/CredentialDetail', () => ({
  default: () => <div>CredentialDetail</div>,
  CredentialDetailsTabRoute: () => <div>CredentialDetailsTabRoute</div>,
  CredentialWorkflowsTabRoute: () => <div>CredentialWorkflowsTabRoute</div>,
  CredentialIntegrationsTabRoute: () => <div>CredentialIntegrationsTabRoute</div>,
}))

const lazyRouteNames = [
  'Workflows',
  'BuilderNew',
  'BuilderEdit',
  'Executions',
  'ExecutionDetail',
  'IntegrationForm',
  'Integrations',
  'IntegrationDetail',
  'EditIntegration',
  'Settings',
  'SettingsCategoryRoute',
  'Glossary',
  'FeatureFlagDemo',
  'Approvals',
  'AccessManagement',
  'AccessManagementCheckAccessRoute',
  'AccessManagementTokenRevocationRoute',
  'AssignmentsTab',
  'Authentication',
  'AddIdentityProvider',
  'IdentityProviderDetail',
  'EditIdentityProvider',
  'EditGroupMapping',
  'CreateUser',
  'UserDetail',
  'UserDetailTabRoute',
  'MyProfile',
  'EditUser',
  'TransferIdentityWizard',
  'GroupDetail',
  'GroupDetailAssignmentsTabRoute',
  'GroupDetailDetailsTabRoute',
  'GroupDetailMembersTabRoute',
  'GroupDetailUnknownTabRoute',
  'GroupsTab',
  'IdentityProviderDetailsTabRoute',
  'IdentityProviderGroupMappingTabRoute',
  'IdentityProviderUnknownTabRoute',
  'PoliciesTab',
  'ProjectDetail',
  'ProjectDetailAssignmentsTabRoute',
  'ProjectDetailDetailsTabRoute',
  'ProjectDetailUnknownTabRoute',
  'ProjectDetailWorkflowsTabRoute',
  'ProjectsTab',
  'RolesTab',
  'ServiceAccountDetail',
  'ServiceAccountDetailDetailsTabRoute',
  'ServiceAccountDetailCredentialsTabRoute',
  'ServiceAccountDetailAssignmentsTabRoute',
  'ServiceAccountDetailUnknownTabRoute',
  'ServiceAccountsTab',
  'Credentials',
  'CredentialDetail',
  'CredentialDetailsTabRoute',
  'CredentialWorkflowsTabRoute',
  'CredentialIntegrationsTabRoute',
  'UsersTab',
] as const

describe('lazyRoutes', () => {
  it('covers every lazy route export', () => {
    expect(Object.keys(lazyRouteComponents).sort()).toEqual([...lazyRouteNames].sort())
  })

  it.each(lazyRouteNames)('resolves %s', async (name) => {
    const Component = lazyRouteComponents[name]

    render(
      <Suspense fallback={<div>loading</div>}>
        <Component />
      </Suspense>
    )

    expect(await screen.findByText(name)).toBeInTheDocument()
  })
})
