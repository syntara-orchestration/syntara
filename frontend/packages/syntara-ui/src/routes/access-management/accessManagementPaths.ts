import { AppRoute } from '../../app/AppRoute'
import { ACCESS_MANAGEMENT_DETAIL_ROUTES } from '../../app/typed-route-destinations'
import type {
  AccessManagementDetailDestination,
  GroupDetailDestination,
  ProjectDetailDestination,
  ServiceAccountDetailDestination,
  UserDetailDestination,
} from '../../app/typed-route-destinations'

import { RolePrincipalType } from './RoleAssignmentTypes'

/** Build the path to a user's detail page. */
export function getUserDetailPath(userId: string): string {
  return AppRoute.AccessManagement.UserDetail.replace(':userId', userId).replace('/:tab?', '')
}

/** Build a typed destination to a user's detail page. */
export function getUserDetailDestination(userId: string): UserDetailDestination {
  return {
    to: ACCESS_MANAGEMENT_DETAIL_ROUTES.user,
    params: { userId },
  }
}

/** Build the path to a group's detail page. */
export function getGroupDetailPath(groupId: string): string {
  return AppRoute.AccessManagement.GroupDetail.replace(':groupId', groupId)
}

/** Build a typed destination to a group's detail page. */
export function getGroupDetailDestination(groupId: string): GroupDetailDestination {
  return {
    to: ACCESS_MANAGEMENT_DETAIL_ROUTES.group,
    params: { groupId },
  }
}

/** Build the path to a project's detail page. */
export function getProjectDetailPath(projectId: string): string {
  return AppRoute.AccessManagement.ProjectDetail.replace(':projectId', projectId)
}

/** Build a typed destination to a project's detail page. */
export function getProjectDetailDestination(projectId: string): ProjectDetailDestination {
  return {
    to: ACCESS_MANAGEMENT_DETAIL_ROUTES.project,
    params: { projectId },
  }
}

/** Build the path to a service account's detail page. */
export function getServiceAccountDetailPath(serviceAccountId: string): string {
  return AppRoute.AccessManagement.ServiceAccountDetail.replace(':serviceAccountId', serviceAccountId)
}

/** Build a typed destination to a service account's detail page. */
export function getServiceAccountDetailDestination(serviceAccountId: string): ServiceAccountDetailDestination {
  return {
    to: ACCESS_MANAGEMENT_DETAIL_ROUTES.serviceAccount,
    params: { serviceAccountId },
  }
}

/** Build the detail path for a user, group, or service account principal. */
export function getPrincipalDetailPath(principalType: RolePrincipalType, id: string): string {
  switch (principalType) {
    case RolePrincipalType.GROUP:
      return getGroupDetailPath(id)
    case RolePrincipalType.SERVICE_ACCOUNT:
      return getServiceAccountDetailPath(id)
    case RolePrincipalType.USER:
      return getUserDetailPath(id)
  }
}

/** Build a typed destination to the detail page for a user, group, or service account principal. */
export function getPrincipalDetailDestination(
  principalType: RolePrincipalType,
  id: string
): AccessManagementDetailDestination {
  switch (principalType) {
    case RolePrincipalType.GROUP:
      return getGroupDetailDestination(id)
    case RolePrincipalType.SERVICE_ACCOUNT:
      return getServiceAccountDetailDestination(id)
    case RolePrincipalType.USER:
      return getUserDetailDestination(id)
  }
}
