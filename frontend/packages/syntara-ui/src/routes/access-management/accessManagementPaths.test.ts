import { describe, expect, it } from 'vitest'

import * as routeRefs from '../../app/routes/routeReferences'
import { tanstackRouter } from '../../app/tanstackRouter'

import {
  getGroupDetailOptions,
  getPrincipalDetailOptions,
  getProjectDetailOptions,
  getServiceAccountDetailOptions,
  getUserDetailOptions,
} from './accessManagementPaths'
import { RolePrincipalType } from './RoleAssignmentTypes'

describe('accessManagementPaths', () => {
  it('builds typed options and preserves parameter URL encoding', () => {
    const userOptions = getUserDetailOptions('user id')
    expect(userOptions).toEqual({ to: routeRefs.userDetailRoute.fullPath, params: { userId: 'user id' } })
    expect(tanstackRouter.buildLocation(userOptions).href).toBe(
      '/system-administration/access-management/users/user%20id'
    )
  })

  it('builds typed group options', () => {
    expect(getGroupDetailOptions('g-456')).toEqual({
      to: routeRefs.groupDetailRoute.fullPath,
      params: { groupId: 'g-456' },
    })
  })

  it('builds typed project options', () => {
    expect(getProjectDetailOptions('proj-456')).toEqual({
      to: routeRefs.projectDetailRoute.fullPath,
      params: { projectId: 'proj-456' },
    })
  })

  it('builds typed service account options', () => {
    expect(getServiceAccountDetailOptions('sa-789')).toEqual({
      to: routeRefs.serviceAccountDetailRoute.fullPath,
      params: { serviceAccountId: 'sa-789' },
    })
  })

  it('selects the correct route for each principal type', () => {
    expect(getPrincipalDetailOptions(RolePrincipalType.USER, 'u-1')).toEqual(getUserDetailOptions('u-1'))
    expect(getPrincipalDetailOptions(RolePrincipalType.GROUP, 'g-1')).toEqual(getGroupDetailOptions('g-1'))
    expect(getPrincipalDetailOptions(RolePrincipalType.SERVICE_ACCOUNT, 'sa-1')).toEqual(
      getServiceAccountDetailOptions('sa-1')
    )
  })
})
