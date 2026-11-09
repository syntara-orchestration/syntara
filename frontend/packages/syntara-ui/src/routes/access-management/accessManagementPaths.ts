import type { AppRouteNavigationOptions } from '../../app/routeNavigationOptions'
import * as routeRefs from '../../app/routes/routeReferences'

import { RolePrincipalType } from './RoleAssignmentTypes'

export type UserDetailTab = 'details' | 'groups' | 'identities' | 'roles' | 'permissions' | 'check-access'

/** Build typed navigation options for a user's detail page. */
export function getUserDetailOptions(userId: string): AppRouteNavigationOptions {
  return { to: routeRefs.userDetailRoute.fullPath, params: { userId } }
}

/** Build typed navigation options for a group's detail page. */
export function getGroupDetailOptions(groupId: string): AppRouteNavigationOptions {
  return { to: routeRefs.groupDetailRoute.fullPath, params: { groupId } }
}

/** Build typed navigation options for a project's detail page. */
export function getProjectDetailOptions(projectId: string): AppRouteNavigationOptions {
  return { to: routeRefs.projectDetailRoute.fullPath, params: { projectId } }
}

/** Build typed navigation options for a service account's detail page. */
export function getServiceAccountDetailOptions(serviceAccountId: string): AppRouteNavigationOptions {
  return { to: routeRefs.serviceAccountDetailRoute.fullPath, params: { serviceAccountId } }
}

/** Build typed detail navigation options for a user, group, or service account principal. */
export function getPrincipalDetailOptions(principalType: RolePrincipalType, id: string): AppRouteNavigationOptions {
  switch (principalType) {
    case RolePrincipalType.GROUP:
      return getGroupDetailOptions(id)
    case RolePrincipalType.SERVICE_ACCOUNT:
      return getServiceAccountDetailOptions(id)
    case RolePrincipalType.USER:
      return getUserDetailOptions(id)
  }
}

/** Build typed navigation options for a user detail or profile tab. */
export function getUserTabOptions(isMyProfile: boolean, userId: string, tab: UserDetailTab): AppRouteNavigationOptions {
  if (isMyProfile) return { to: routeRefs.myProfileTabRoute.fullPath, params: { tab } }

  const params = { userId }
  switch (tab) {
    case 'details':
      return { to: routeRefs.userDetailDetailsRoute.fullPath, params }
    case 'groups':
      return { to: routeRefs.userDetailGroupsRoute.fullPath, params }
    case 'identities':
      return { to: routeRefs.userDetailIdentitiesRoute.fullPath, params }
    case 'roles':
      return { to: routeRefs.userDetailRolesRoute.fullPath, params }
    case 'permissions':
      return { to: routeRefs.userDetailPermissionsRoute.fullPath, params }
    case 'check-access':
      return { to: routeRefs.userDetailCheckAccessRoute.fullPath, params }
  }
}
