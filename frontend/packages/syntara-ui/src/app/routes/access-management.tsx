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

const accessManagementRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/system-administration/access-management',
  validateSearch: accessMgmtSearch,
  component: makeRouteComponent(<AccessManagement />),
})

const accessManagementTabRoutes = [
  createRoute({
    getParentRoute: () => accessManagementRoute,
    path: '/users',
    validateSearch: accessMgmtSearch,
    component: makeRouteComponent(<UsersTab />),
  }),
  createRoute({
    getParentRoute: () => accessManagementRoute,
    path: '/groups',
    validateSearch: accessMgmtSearch,
    component: makeRouteComponent(<GroupsTab />),
  }),
  createRoute({
    getParentRoute: () => accessManagementRoute,
    path: '/projects',
    validateSearch: accessMgmtSearch,
    component: makeRouteComponent(<ProjectsTab />),
  }),
  createRoute({
    getParentRoute: () => accessManagementRoute,
    path: '/policies',
    validateSearch: accessMgmtSearch,
    component: makeRouteComponent(<PoliciesTab />),
  }),
  createRoute({
    getParentRoute: () => accessManagementRoute,
    path: '/roles',
    component: makeRouteComponent(<RolesTab />),
  }),
  createRoute({
    getParentRoute: () => accessManagementRoute,
    path: '/service-accounts',
    validateSearch: accessMgmtSearch,
    component: makeRouteComponent(<ServiceAccountsTab />),
  }),
  createRoute({
    getParentRoute: () => accessManagementRoute,
    path: '/assignments',
    component: makeRouteComponent(<AssignmentsTab />),
  }),
  createRoute({
    getParentRoute: () => accessManagementRoute,
    path: '/check-access',
    component: makeRouteComponent(<AccessManagementCheckAccessRoute />),
  }),
  createRoute({
    getParentRoute: () => accessManagementRoute,
    path: '/token-revocation',
    component: makeRouteComponent(<AccessManagementTokenRevocationRoute />),
  }),
]

const userDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/system-administration/access-management/users/$userId',
  component: makeRouteComponent(<UserDetail />),
})

const userDetailTabRoutes = [
  createRoute({
    getParentRoute: () => userDetailRoute,
    path: '/',
    component: makeRouteComponent(<UserDetailTabRoute />),
  }),
  createRoute({
    getParentRoute: () => userDetailRoute,
    path: 'details',
    component: makeRouteComponent(<UserDetailTabRoute />),
  }),
  createRoute({
    getParentRoute: () => userDetailRoute,
    path: 'groups',
    component: makeRouteComponent(<UserDetailTabRoute />),
  }),
  createRoute({
    getParentRoute: () => userDetailRoute,
    path: 'identities',
    component: makeRouteComponent(<UserDetailTabRoute />),
  }),
  createRoute({
    getParentRoute: () => userDetailRoute,
    path: 'roles',
    component: makeRouteComponent(<UserDetailTabRoute />),
  }),
  createRoute({
    getParentRoute: () => userDetailRoute,
    path: 'permissions',
    component: makeRouteComponent(<UserDetailTabRoute />),
  }),
  createRoute({
    getParentRoute: () => userDetailRoute,
    path: 'check-access',
    component: makeRouteComponent(<UserDetailTabRoute />),
  }),
]

const groupDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/system-administration/access-management/groups/$groupId',
  component: makeRouteComponent(<GroupDetail />),
})

const groupDetailTabRoutes = [
  createRoute({
    getParentRoute: () => groupDetailRoute,
    path: '/',
    component: makeRouteComponent(<GroupDetailDetailsTabRoute />),
  }),
  createRoute({
    getParentRoute: () => groupDetailRoute,
    path: '/details',
    component: makeRouteComponent(<GroupDetailDetailsTabRoute />),
  }),
  createRoute({
    getParentRoute: () => groupDetailRoute,
    path: '/members',
    component: makeRouteComponent(<GroupDetailMembersTabRoute />),
  }),
  createRoute({
    getParentRoute: () => groupDetailRoute,
    path: '/roles',
    component: makeRouteComponent(<GroupDetailAssignmentsTabRoute />),
  }),
  createRoute({
    getParentRoute: () => groupDetailRoute,
    path: '/$tab',
    component: makeRouteComponent(<GroupDetailUnknownTabRoute />),
  }),
]

const projectDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/system-administration/access-management/projects/$projectId',
  component: makeRouteComponent(<ProjectDetail />),
})

const projectDetailTabRoutes = [
  createRoute({
    getParentRoute: () => projectDetailRoute,
    path: '/',
    component: makeRouteComponent(<ProjectDetailDetailsTabRoute />),
  }),
  createRoute({
    getParentRoute: () => projectDetailRoute,
    path: '/details',
    component: makeRouteComponent(<ProjectDetailDetailsTabRoute />),
  }),
  createRoute({
    getParentRoute: () => projectDetailRoute,
    path: '/workflows',
    component: makeRouteComponent(<ProjectDetailWorkflowsTabRoute />),
  }),
  createRoute({
    getParentRoute: () => projectDetailRoute,
    path: '/role-assignments',
    component: makeRouteComponent(<ProjectDetailAssignmentsTabRoute />),
  }),
  createRoute({
    getParentRoute: () => projectDetailRoute,
    path: '/$tab',
    component: makeRouteComponent(<ProjectDetailUnknownTabRoute />),
  }),
]

const userDetailUnknownTabRoute = createRoute({
  getParentRoute: () => userDetailRoute,
  path: '$tab',
  beforeLoad: ({ params }) =>
    redirect({
      to: '/system-administration/access-management/users/$userId/details',
      params: { userId: params.userId },
      replace: true,
    }),
})

export const accessManagementRoutes = [
  accessManagementRoute.addChildren(accessManagementTabRoutes),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/system-administration/access-management/users/create',
    component: makeRouteComponent(<CreateUser />, { action: 'create', resourceType: 'user' }),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/system-administration/access-management/users/$userId/edit',
    component: makeRouteComponent(<EditUser />, { action: 'update', resourceType: 'user' }),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/system-administration/access-management/users/$userId/transfer-identity',
    component: makeRouteComponent(<TransferIdentityWizard />),
  }),
  userDetailRoute.addChildren([...userDetailTabRoutes, userDetailUnknownTabRoute]),
  groupDetailRoute.addChildren(groupDetailTabRoutes),
  projectDetailRoute.addChildren(projectDetailTabRoutes),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/system-administration/access-management/service-accounts/$serviceAccountId',
    component: makeRouteComponent(<ServiceAccountDetail />),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/system-administration/access-management/service-accounts/$serviceAccountId/$tab',
    component: makeRouteComponent(<ServiceAccountDetail />),
  }),
]
