// Route metadata such as `fullPath` is assigned when TanStack initializes the route tree.
// Ensure the shared references are read after that initialization.
import '../tanstackRouter'

export { accessManagementRoute } from './access-management'
export { accessManagementAssignmentsRoute } from './access-management'
export { accessManagementCheckAccessRoute } from './access-management'
export { accessManagementGroupsRoute } from './access-management'
export { accessManagementPoliciesRoute } from './access-management'
export { accessManagementProjectsRoute } from './access-management'
export { accessManagementRolesRoute } from './access-management'
export { accessManagementServiceAccountsRoute } from './access-management'
export { accessManagementTokenRevocationRoute } from './access-management'
export { accessManagementUsersRoute } from './access-management'
export { createUserRoute, editUserRoute, transferIdentityRoute } from './access-management'
export {
  groupDetailDetailsRoute,
  groupDetailMembersRoute,
  groupDetailRoute,
  groupDetailRolesRoute,
} from './access-management'
export {
  projectDetailDetailsRoute,
  projectDetailRoleAssignmentsRoute,
  projectDetailRoute,
  projectDetailWorkflowsRoute,
} from './access-management'
export {
  serviceAccountDetailAssignmentsRoute,
  serviceAccountDetailCredentialsRoute,
  serviceAccountDetailDetailsRoute,
  serviceAccountDetailRoute,
  serviceAccountDetailUnknownTabRoute,
} from './access-management'
export {
  userDetailCheckAccessRoute,
  userDetailDetailsRoute,
  userDetailGroupsRoute,
  userDetailIdentitiesRoute,
  userDetailPermissionsRoute,
  userDetailRolesRoute,
  userDetailRoute,
} from './access-management'
export { approvalsRoute } from './approvals'
export {
  addIdentityProviderRoute,
  authenticationRootRoute,
  editIdentityProviderGroupMappingRoute,
  editIdentityProviderRoute,
  identityProviderDetailRoute,
  identityProviderDetailsRoute,
  identityProviderGroupMappingRoute,
  identityProviderUnknownTabRoute,
} from './authentication'
export { builderEditRoute, builderNewRoute } from './builder'
export {
  configurationOverviewRoute,
  configureIntegrationRoute,
  credentialDetailRoute,
  credentialDetailsRoute,
  credentialIntegrationsRoute,
  credentialWorkflowsRoute,
  credentialsRoute,
  editIntegrationRoute,
  integrationDetailRoute,
  integrationDetailTabRoute,
  integrationsRoute,
} from './configuration'
export { executionDetailRoute, executionsListRoute } from './executions'
export { featureFlagDemoRoute } from './feature-flag-demo'
export { myProfileRootRoute, myProfileTabRoute } from './my-profile'
export { settingsCategoryRoute, settingsRoute } from './settings'
export { workflowsRoute } from './workflows'
