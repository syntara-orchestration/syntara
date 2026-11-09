import { testSignInCallbackPath } from '../src/app/routes/appLevelPaths'
import * as routeRefs from '../src/app/routes/routeReferences'
import { tanstackRouter } from '../src/app/tanstackRouter'

function workflowDetail(workflowId: string) {
  return tanstackRouter.buildLocation({ to: routeRefs.builderEditRoute.fullPath, params: { workflowId } }).href
}

function executionDetail(executionId: string) {
  return tanstackRouter.buildLocation({ to: routeRefs.executionDetailRoute.fullPath, params: { executionId } }).href
}

function integrationDetail(integrationId: string) {
  return tanstackRouter.buildLocation({ to: routeRefs.integrationDetailRoute.fullPath, params: { integrationId } }).href
}

function integrationTab(integrationId: string, tab: string) {
  return tanstackRouter.buildLocation({
    to: routeRefs.integrationDetailTabRoute.fullPath,
    params: { integrationId, tab },
  }).href
}

function integrationEdit(integrationId: string) {
  return tanstackRouter.buildLocation({ to: routeRefs.editIntegrationRoute.fullPath, params: { integrationId } }).href
}

function credentialDetail(credentialId: string) {
  return tanstackRouter.buildLocation({ to: routeRefs.credentialDetailRoute.fullPath, params: { credentialId } }).href
}

function credentialTab(credentialId: string, tab: string) {
  const params = { credentialId }
  switch (tab) {
    case 'details':
      return tanstackRouter.buildLocation({ to: routeRefs.credentialDetailsRoute.fullPath, params }).href
    case 'workflows':
      return tanstackRouter.buildLocation({ to: routeRefs.credentialWorkflowsRoute.fullPath, params }).href
    case 'integrations':
      return tanstackRouter.buildLocation({ to: routeRefs.credentialIntegrationsRoute.fullPath, params }).href
    default:
      throw new Error(`Unsupported credential tab: ${tab}`)
  }
}

function settingsCategory(category: string) {
  return tanstackRouter.buildLocation({ to: routeRefs.settingsCategoryRoute.fullPath, params: { category } }).href
}

function identityProviderDetail(providerId: string) {
  return tanstackRouter.buildLocation({ to: routeRefs.identityProviderDetailRoute.fullPath, params: { providerId } })
    .href
}

function identityProviderTab(providerId: string, tab: string) {
  const to =
    tab === 'group-mapping'
      ? routeRefs.identityProviderGroupMappingRoute.fullPath
      : routeRefs.identityProviderDetailsRoute.fullPath
  return tanstackRouter.buildLocation({ to, params: { providerId } }).href
}

function identityProviderEdit(providerId: string) {
  return tanstackRouter.buildLocation({ to: routeRefs.editIdentityProviderRoute.fullPath, params: { providerId } }).href
}

function editGroupMapping(providerId: string) {
  return tanstackRouter.buildLocation({
    to: routeRefs.editIdentityProviderGroupMappingRoute.fullPath,
    params: { providerId },
  }).href
}

function userDetail(userId: string) {
  return tanstackRouter.buildLocation({ to: routeRefs.userDetailRoute.fullPath, params: { userId } }).href
}

function userTab(userId: string, tab: string) {
  const params = { userId }
  switch (tab) {
    case 'details':
      return tanstackRouter.buildLocation({ to: routeRefs.userDetailDetailsRoute.fullPath, params }).href
    case 'groups':
      return tanstackRouter.buildLocation({ to: routeRefs.userDetailGroupsRoute.fullPath, params }).href
    case 'identities':
      return tanstackRouter.buildLocation({ to: routeRefs.userDetailIdentitiesRoute.fullPath, params }).href
    case 'roles':
      return tanstackRouter.buildLocation({ to: routeRefs.userDetailRolesRoute.fullPath, params }).href
    case 'permissions':
      return tanstackRouter.buildLocation({ to: routeRefs.userDetailPermissionsRoute.fullPath, params }).href
    case 'check-access':
      return tanstackRouter.buildLocation({ to: routeRefs.userDetailCheckAccessRoute.fullPath, params }).href
    default:
      throw new Error(`Unsupported user tab: ${tab}`)
  }
}

function groupDetail(groupId: string) {
  return tanstackRouter.buildLocation({ to: routeRefs.groupDetailRoute.fullPath, params: { groupId } }).href
}

function groupTab(groupId: string, tab: string) {
  const params = { groupId }
  switch (tab) {
    case 'details':
      return tanstackRouter.buildLocation({ to: routeRefs.groupDetailDetailsRoute.fullPath, params }).href
    case 'members':
      return tanstackRouter.buildLocation({ to: routeRefs.groupDetailMembersRoute.fullPath, params }).href
    case 'roles':
      return tanstackRouter.buildLocation({ to: routeRefs.groupDetailRolesRoute.fullPath, params }).href
    default:
      throw new Error(`Unsupported group tab: ${tab}`)
  }
}

function projectDetail(projectId: string) {
  return tanstackRouter.buildLocation({ to: routeRefs.projectDetailRoute.fullPath, params: { projectId } }).href
}

function projectTab(projectId: string, tab: string) {
  const params = { projectId }
  switch (tab) {
    case 'details':
      return tanstackRouter.buildLocation({ to: routeRefs.projectDetailDetailsRoute.fullPath, params }).href
    case 'workflows':
      return tanstackRouter.buildLocation({ to: routeRefs.projectDetailWorkflowsRoute.fullPath, params }).href
    case 'role-assignments':
      return tanstackRouter.buildLocation({ to: routeRefs.projectDetailRoleAssignmentsRoute.fullPath, params }).href
    default:
      throw new Error(`Unsupported project tab: ${tab}`)
  }
}

function serviceAccountDetail(serviceAccountId: string) {
  return tanstackRouter.buildLocation({
    to: routeRefs.serviceAccountDetailRoute.fullPath,
    params: { serviceAccountId },
  }).href
}

function serviceAccountTab(serviceAccountId: string, tab: string) {
  const params = { serviceAccountId }
  switch (tab) {
    case 'details':
      return tanstackRouter.buildLocation({ to: routeRefs.serviceAccountDetailDetailsRoute.fullPath, params }).href
    case 'credentials':
      return tanstackRouter.buildLocation({ to: routeRefs.serviceAccountDetailCredentialsRoute.fullPath, params }).href
    case 'assignments':
      return tanstackRouter.buildLocation({ to: routeRefs.serviceAccountDetailAssignmentsRoute.fullPath, params }).href
    default:
      throw new Error(`Unsupported service account tab: ${tab}`)
  }
}

function userEdit(userId: string) {
  return tanstackRouter.buildLocation({ to: routeRefs.editUserRoute.fullPath, params: { userId } }).href
}

function userTransferIdentity(userId: string) {
  return tanstackRouter.buildLocation({ to: routeRefs.transferIdentityRoute.fullPath, params: { userId } }).href
}

export const routePaths = {
  FeatureFlagDemo: routeRefs.featureFlagDemoRoute.fullPath,
  WorkflowBuilder: {
    New: routeRefs.builderNewRoute.fullPath,
    Edit: workflowDetail,
  },
  Workflows: { Root: routeRefs.workflowsRoute.fullPath },
  Executions: { Root: routeRefs.executionsListRoute.fullPath, Execution: executionDetail },
  Approvals: { Root: routeRefs.approvalsRoute.fullPath },
  Configuration: {
    Overview: routeRefs.configurationOverviewRoute.fullPath,
    Integrations: {
      Root: routeRefs.integrationsRoute.fullPath,
      Configure: routeRefs.configureIntegrationRoute.fullPath,
      Detail: integrationDetail,
      DetailTab: integrationTab,
      Edit: integrationEdit,
    },
    Credentials: { Root: routeRefs.credentialsRoute.fullPath, Detail: credentialDetail, DetailTab: credentialTab },
  },
  SystemAdministration: {
    Settings: routeRefs.settingsRoute.fullPath,
    SettingsTab: settingsCategory,
    Authentication: {
      Root: routeRefs.authenticationRootRoute.fullPath,
      AddIdentityProvider: routeRefs.addIdentityProviderRoute.fullPath,
      IdentityProviderDetail: identityProviderDetail,
      IdentityProviderDetailTab: identityProviderTab,
      EditIdentityProvider: identityProviderEdit,
      EditGroupMapping: editGroupMapping,
    },
  },
  AccessManagement: {
    Root: routeRefs.accessManagementRoute.fullPath,
    Users: routeRefs.accessManagementUsersRoute.fullPath,
    CreateUser: routeRefs.createUserRoute.fullPath,
    UserDetail: userDetail,
    UserDetailTab: userTab,
    EditUser: userEdit,
    TransferIdentity: userTransferIdentity,
    Groups: routeRefs.accessManagementGroupsRoute.fullPath,
    GroupDetail: groupDetail,
    GroupDetailTab: groupTab,
    Policies: routeRefs.accessManagementPoliciesRoute.fullPath,
    Roles: routeRefs.accessManagementRolesRoute.fullPath,
    Projects: routeRefs.accessManagementProjectsRoute.fullPath,
    ProjectDetail: projectDetail,
    ProjectDetailTab: projectTab,
    ServiceAccounts: routeRefs.accessManagementServiceAccountsRoute.fullPath,
    ServiceAccountDetail: serviceAccountDetail,
    ServiceAccountDetailTab: serviceAccountTab,
    Assignments: routeRefs.accessManagementAssignmentsRoute.fullPath,
    CheckAccess: routeRefs.accessManagementCheckAccessRoute.fullPath,
    TokenRevocation: routeRefs.accessManagementTokenRevocationRoute.fullPath,
  },
  Auth: { TestSignInCallback: testSignInCallbackPath },
  MyProfile: {
    Root: routeRefs.myProfileRootRoute.fullPath,
    Tab: (tab: string) =>
      tanstackRouter.buildLocation({ to: routeRefs.myProfileTabRoute.fullPath, params: { tab } }).href,
  },
}
