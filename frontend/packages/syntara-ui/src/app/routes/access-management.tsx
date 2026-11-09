import { createRoute, redirect } from '@tanstack/react-router'

import {
  AccessManagement,
  AccessManagementCheckAccessRoute,
  AccessManagementTokenRevocationRoute,
  AssignmentsTab,
  CreateUser,
  EditUser,
  GroupDetail,
  GroupDetailAssignmentsTabRoute,
  GroupDetailDetailsTabRoute,
  GroupDetailMembersTabRoute,
  GroupDetailUnknownTabRoute,
  GroupsTab,
  PoliciesTab,
  ProjectDetail,
  ProjectDetailAssignmentsTabRoute,
  ProjectDetailDetailsTabRoute,
  ProjectDetailUnknownTabRoute,
  ProjectDetailWorkflowsTabRoute,
  ProjectsTab,
  RolesTab,
  ServiceAccountDetail,
  ServiceAccountDetailAssignmentsTabRoute,
  ServiceAccountDetailCredentialsTabRoute,
  ServiceAccountDetailDetailsTabRoute,
  ServiceAccountDetailUnknownTabRoute,
  ServiceAccountsTab,
  TransferIdentityWizard,
  UserDetail,
  UserDetailTabRoute,
  UsersTab,
} from '../lazyRoutes'
import { makeRouteComponent } from '../makeRouteComponent'
import { listSearchParams } from '../routeSearchParams'

import { rootRoute } from './__root'

const accessMgmtSearch = listSearchParams.catch({})

export const accessManagementRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/system-administration/access-management',
  validateSearch: accessMgmtSearch,
  component: makeRouteComponent(<AccessManagement />),
})

export const accessManagementUsersRoute = createRoute({
  getParentRoute: () => accessManagementRoute,
  path: '/users',
  validateSearch: accessMgmtSearch,
  component: makeRouteComponent(<UsersTab />),
})
export const accessManagementGroupsRoute = createRoute({
  getParentRoute: () => accessManagementRoute,
  path: '/groups',
  validateSearch: accessMgmtSearch,
  component: makeRouteComponent(<GroupsTab />),
})
export const accessManagementProjectsRoute = createRoute({
  getParentRoute: () => accessManagementRoute,
  path: '/projects',
  validateSearch: accessMgmtSearch,
  component: makeRouteComponent(<ProjectsTab />),
})
export const accessManagementPoliciesRoute = createRoute({
  getParentRoute: () => accessManagementRoute,
  path: '/policies',
  validateSearch: accessMgmtSearch,
  component: makeRouteComponent(<PoliciesTab />),
})
export const accessManagementRolesRoute = createRoute({
  getParentRoute: () => accessManagementRoute,
  path: '/roles',
  component: makeRouteComponent(<RolesTab />),
})
export const accessManagementServiceAccountsRoute = createRoute({
  getParentRoute: () => accessManagementRoute,
  path: '/service-accounts',
  validateSearch: accessMgmtSearch,
  component: makeRouteComponent(<ServiceAccountsTab />),
})
export const accessManagementAssignmentsRoute = createRoute({
  getParentRoute: () => accessManagementRoute,
  path: '/assignments',
  component: makeRouteComponent(<AssignmentsTab />),
})
export const accessManagementCheckAccessRoute = createRoute({
  getParentRoute: () => accessManagementRoute,
  path: '/check-access',
  component: makeRouteComponent(<AccessManagementCheckAccessRoute />),
})
export const accessManagementTokenRevocationRoute = createRoute({
  getParentRoute: () => accessManagementRoute,
  path: '/token-revocation',
  component: makeRouteComponent(<AccessManagementTokenRevocationRoute />),
})

const accessManagementTabRoutes = [
  accessManagementUsersRoute,
  accessManagementGroupsRoute,
  accessManagementProjectsRoute,
  accessManagementPoliciesRoute,
  accessManagementRolesRoute,
  accessManagementServiceAccountsRoute,
  accessManagementAssignmentsRoute,
  accessManagementCheckAccessRoute,
  accessManagementTokenRevocationRoute,
]

export const userDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/system-administration/access-management/users/$userId',
  component: makeRouteComponent(<UserDetail />),
})

export const userDetailIndexRoute = createRoute({
  getParentRoute: () => userDetailRoute,
  path: '/',
  component: makeRouteComponent(<UserDetailTabRoute />),
})
export const userDetailDetailsRoute = createRoute({
  getParentRoute: () => userDetailRoute,
  path: 'details',
  component: makeRouteComponent(<UserDetailTabRoute />),
})
export const userDetailGroupsRoute = createRoute({
  getParentRoute: () => userDetailRoute,
  path: 'groups',
  component: makeRouteComponent(<UserDetailTabRoute />),
})
export const userDetailIdentitiesRoute = createRoute({
  getParentRoute: () => userDetailRoute,
  path: 'identities',
  component: makeRouteComponent(<UserDetailTabRoute />),
})
export const userDetailRolesRoute = createRoute({
  getParentRoute: () => userDetailRoute,
  path: 'roles',
  component: makeRouteComponent(<UserDetailTabRoute />),
})
export const userDetailPermissionsRoute = createRoute({
  getParentRoute: () => userDetailRoute,
  path: 'permissions',
  component: makeRouteComponent(<UserDetailTabRoute />),
})
export const userDetailCheckAccessRoute = createRoute({
  getParentRoute: () => userDetailRoute,
  path: 'check-access',
  component: makeRouteComponent(<UserDetailTabRoute />),
})

const userDetailTabRoutes = [
  userDetailIndexRoute,
  userDetailDetailsRoute,
  userDetailGroupsRoute,
  userDetailIdentitiesRoute,
  userDetailRolesRoute,
  userDetailPermissionsRoute,
  userDetailCheckAccessRoute,
]

export const groupDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/system-administration/access-management/groups/$groupId',
  component: makeRouteComponent(<GroupDetail />),
})

export const groupDetailIndexRoute = createRoute({
  getParentRoute: () => groupDetailRoute,
  path: '/',
  component: makeRouteComponent(<GroupDetailDetailsTabRoute />),
})
export const groupDetailDetailsRoute = createRoute({
  getParentRoute: () => groupDetailRoute,
  path: '/details',
  component: makeRouteComponent(<GroupDetailDetailsTabRoute />),
})
export const groupDetailMembersRoute = createRoute({
  getParentRoute: () => groupDetailRoute,
  path: '/members',
  component: makeRouteComponent(<GroupDetailMembersTabRoute />),
})
export const groupDetailRolesRoute = createRoute({
  getParentRoute: () => groupDetailRoute,
  path: '/roles',
  component: makeRouteComponent(<GroupDetailAssignmentsTabRoute />),
})
export const groupDetailUnknownTabRoute = createRoute({
  getParentRoute: () => groupDetailRoute,
  path: '/$tab',
  component: makeRouteComponent(<GroupDetailUnknownTabRoute />),
})

const groupDetailTabRoutes = [
  groupDetailIndexRoute,
  groupDetailDetailsRoute,
  groupDetailMembersRoute,
  groupDetailRolesRoute,
  groupDetailUnknownTabRoute,
]

export const projectDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/system-administration/access-management/projects/$projectId',
  component: makeRouteComponent(<ProjectDetail />),
})

export const projectDetailIndexRoute = createRoute({
  getParentRoute: () => projectDetailRoute,
  path: '/',
  component: makeRouteComponent(<ProjectDetailDetailsTabRoute />),
})
export const projectDetailDetailsRoute = createRoute({
  getParentRoute: () => projectDetailRoute,
  path: '/details',
  component: makeRouteComponent(<ProjectDetailDetailsTabRoute />),
})
export const projectDetailWorkflowsRoute = createRoute({
  getParentRoute: () => projectDetailRoute,
  path: '/workflows',
  component: makeRouteComponent(<ProjectDetailWorkflowsTabRoute />),
})
export const projectDetailRoleAssignmentsRoute = createRoute({
  getParentRoute: () => projectDetailRoute,
  path: '/role-assignments',
  component: makeRouteComponent(<ProjectDetailAssignmentsTabRoute />),
})
export const projectDetailUnknownTabRoute = createRoute({
  getParentRoute: () => projectDetailRoute,
  path: '/$tab',
  component: makeRouteComponent(<ProjectDetailUnknownTabRoute />),
})

const projectDetailTabRoutes = [
  projectDetailIndexRoute,
  projectDetailDetailsRoute,
  projectDetailWorkflowsRoute,
  projectDetailRoleAssignmentsRoute,
  projectDetailUnknownTabRoute,
]

export const serviceAccountDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/system-administration/access-management/service-accounts/$serviceAccountId',
  component: makeRouteComponent(<ServiceAccountDetail />),
})

export const serviceAccountDetailIndexRoute = createRoute({
  getParentRoute: () => serviceAccountDetailRoute,
  path: '/',
  component: makeRouteComponent(<ServiceAccountDetailDetailsTabRoute />),
})
export const serviceAccountDetailDetailsRoute = createRoute({
  getParentRoute: () => serviceAccountDetailRoute,
  path: '/details',
  component: makeRouteComponent(<ServiceAccountDetailDetailsTabRoute />),
})
export const serviceAccountDetailCredentialsRoute = createRoute({
  getParentRoute: () => serviceAccountDetailRoute,
  path: '/credentials',
  component: makeRouteComponent(<ServiceAccountDetailCredentialsTabRoute />),
})
export const serviceAccountDetailAssignmentsRoute = createRoute({
  getParentRoute: () => serviceAccountDetailRoute,
  path: '/assignments',
  component: makeRouteComponent(<ServiceAccountDetailAssignmentsTabRoute />),
})
export const serviceAccountDetailUnknownTabRoute = createRoute({
  getParentRoute: () => serviceAccountDetailRoute,
  path: '/$tab',
  component: makeRouteComponent(<ServiceAccountDetailUnknownTabRoute />),
})

const serviceAccountDetailTabRoutes = [
  serviceAccountDetailIndexRoute,
  serviceAccountDetailDetailsRoute,
  serviceAccountDetailCredentialsRoute,
  serviceAccountDetailAssignmentsRoute,
  serviceAccountDetailUnknownTabRoute,
]

export const userDetailUnknownTabRoute = createRoute({
  getParentRoute: () => userDetailRoute,
  path: '$tab',
  beforeLoad: ({ params }) =>
    redirect({
      to: '/system-administration/access-management/users/$userId/details',
      params: { userId: params.userId },
      replace: true,
    }),
})

export const createUserRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/system-administration/access-management/users/create',
  component: makeRouteComponent(<CreateUser />, { action: 'create', resourceType: 'user' }),
})
export const editUserRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/system-administration/access-management/users/$userId/edit',
  component: makeRouteComponent(<EditUser />, { action: 'update', resourceType: 'user' }),
})
export const transferIdentityRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/system-administration/access-management/users/$userId/transfer-identity',
  component: makeRouteComponent(<TransferIdentityWizard />),
})

export const accessManagementRoutes = [
  accessManagementRoute.addChildren(accessManagementTabRoutes),
  createUserRoute,
  editUserRoute,
  transferIdentityRoute,
  userDetailRoute.addChildren([...userDetailTabRoutes, userDetailUnknownTabRoute]),
  groupDetailRoute.addChildren(groupDetailTabRoutes),
  projectDetailRoute.addChildren(projectDetailTabRoutes),
  serviceAccountDetailRoute.addChildren(serviceAccountDetailTabRoutes),
]
