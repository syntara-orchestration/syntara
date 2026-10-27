import { createRoute, redirect } from '@tanstack/react-router'

import {
  AccessManagement,
  CreateUser,
  EditUser,
  GroupDetail,
  ProjectDetail,
  ServiceAccountDetail,
  TransferIdentityWizard,
  UserDetail,
  UserDetailTabRoute,
} from '../lazyRoutes'
import { makeRouteComponent } from '../makeRouteComponent'
import { listSearchParams } from '../routeSearchParams'

import { rootRoute } from './__root'

const accessMgmtSearch = listSearchParams.catch({})

const userDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/system-administration/access-management/users/$userId',
  component: makeRouteComponent(<UserDetail />),
})

const userDetailIndexRoute = createRoute({
  getParentRoute: () => userDetailRoute,
  path: '/',
  component: makeRouteComponent(<UserDetailTabRoute />),
})

const userDetailsTabRoute = createRoute({
  getParentRoute: () => userDetailRoute,
  path: 'details',
  component: makeRouteComponent(<UserDetailTabRoute />),
})

const userGroupsTabRoute = createRoute({
  getParentRoute: () => userDetailRoute,
  path: 'groups',
  component: makeRouteComponent(<UserDetailTabRoute />),
})

const userIdentitiesTabRoute = createRoute({
  getParentRoute: () => userDetailRoute,
  path: 'identities',
  component: makeRouteComponent(<UserDetailTabRoute />),
})

const userAssignmentsTabRoute = createRoute({
  getParentRoute: () => userDetailRoute,
  path: 'roles',
  component: makeRouteComponent(<UserDetailTabRoute />),
})

const userPermissionsTabRoute = createRoute({
  getParentRoute: () => userDetailRoute,
  path: 'permissions',
  component: makeRouteComponent(<UserDetailTabRoute />),
})

const userCheckAccessTabRoute = createRoute({
  getParentRoute: () => userDetailRoute,
  path: 'check-access',
  component: makeRouteComponent(<UserDetailTabRoute />),
})

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
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/system-administration/access-management',
    validateSearch: accessMgmtSearch,
    component: makeRouteComponent(<AccessManagement />),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/system-administration/access-management/users',
    validateSearch: accessMgmtSearch,
    component: makeRouteComponent(<AccessManagement />),
  }),
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
  userDetailRoute.addChildren([
    userDetailIndexRoute,
    userDetailsTabRoute,
    userGroupsTabRoute,
    userIdentitiesTabRoute,
    userAssignmentsTabRoute,
    userPermissionsTabRoute,
    userCheckAccessTabRoute,
    userDetailUnknownTabRoute,
  ]),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/system-administration/access-management/groups',
    validateSearch: accessMgmtSearch,
    component: makeRouteComponent(<AccessManagement />),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/system-administration/access-management/groups/$groupId',
    component: makeRouteComponent(<GroupDetail />),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/system-administration/access-management/groups/$groupId/$tab',
    component: makeRouteComponent(<GroupDetail />),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/system-administration/access-management/policies',
    validateSearch: accessMgmtSearch,
    component: makeRouteComponent(<AccessManagement />),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/system-administration/access-management/roles',
    component: makeRouteComponent(<AccessManagement />),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/system-administration/access-management/projects',
    validateSearch: accessMgmtSearch,
    component: makeRouteComponent(<AccessManagement />),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/system-administration/access-management/projects/$projectId',
    component: makeRouteComponent(<ProjectDetail />),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/system-administration/access-management/projects/$projectId/$tab',
    component: makeRouteComponent(<ProjectDetail />),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/system-administration/access-management/service-accounts',
    validateSearch: accessMgmtSearch,
    component: makeRouteComponent(<AccessManagement />),
  }),
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
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/system-administration/access-management/assignments',
    component: makeRouteComponent(<AccessManagement />),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/system-administration/access-management/check-access',
    component: makeRouteComponent(<AccessManagement />),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/system-administration/access-management/token-revocation',
    component: makeRouteComponent(<AccessManagement />),
  }),
]
