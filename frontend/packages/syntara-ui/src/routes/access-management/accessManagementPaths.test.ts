import { describe, expect, expectTypeOf, it } from 'vitest'

import { ACCESS_MANAGEMENT_DETAIL_ROUTES } from '../../app/typed-route-destinations'
import type {
  GroupDetailDestination,
  ProjectDetailDestination,
  ServiceAccountDetailDestination,
  UserDetailDestination,
} from '../../app/typed-route-destinations'

import {
  getGroupDetailDestination,
  getGroupDetailPath,
  getPrincipalDetailDestination,
  getPrincipalDetailPath,
  getProjectDetailDestination,
  getProjectDetailPath,
  getServiceAccountDetailDestination,
  getServiceAccountDetailPath,
  getUserDetailDestination,
  getUserDetailPath,
} from './accessManagementPaths'
import { RolePrincipalType } from './RoleAssignmentTypes'

describe('accessManagementPaths', () => {
  describe('getUserDetailPath', () => {
    it('builds the user detail path', () => {
      expect(getUserDetailPath('u-123')).toBe('/system-administration/access-management/users/u-123')
    })
  })

  describe('typed detail destinations', () => {
    it('builds route options with the correct params', () => {
      expect(getUserDetailDestination('u-123')).toEqual({
        to: ACCESS_MANAGEMENT_DETAIL_ROUTES.user,
        params: { userId: 'u-123' },
      })
      expect(getGroupDetailDestination('g-456')).toEqual({
        to: ACCESS_MANAGEMENT_DETAIL_ROUTES.group,
        params: { groupId: 'g-456' },
      })
      expect(getProjectDetailDestination('proj-456')).toEqual({
        to: ACCESS_MANAGEMENT_DETAIL_ROUTES.project,
        params: { projectId: 'proj-456' },
      })
      expect(getServiceAccountDetailDestination('sa-789')).toEqual({
        to: ACCESS_MANAGEMENT_DETAIL_ROUTES.serviceAccount,
        params: { serviceAccountId: 'sa-789' },
      })
      expect(getPrincipalDetailDestination(RolePrincipalType.GROUP, 'g-456')).toEqual({
        to: ACCESS_MANAGEMENT_DETAIL_ROUTES.group,
        params: { groupId: 'g-456' },
      })
    })

    it('rejects a wrong route or path parameter shape at compile time', () => {
      expectTypeOf<{
        to: typeof ACCESS_MANAGEMENT_DETAIL_ROUTES.user
        params: { userId: string }
      }>().toExtend<UserDetailDestination>()
      expectTypeOf<{
        to: typeof ACCESS_MANAGEMENT_DETAIL_ROUTES.group
        params: { groupId: string }
      }>().toExtend<GroupDetailDestination>()
      expectTypeOf<{
        to: typeof ACCESS_MANAGEMENT_DETAIL_ROUTES.project
        params: { projectId: string }
      }>().toExtend<ProjectDetailDestination>()
      expectTypeOf<{
        to: typeof ACCESS_MANAGEMENT_DETAIL_ROUTES.serviceAccount
        params: { serviceAccountId: string }
      }>().toExtend<ServiceAccountDetailDestination>()
      expectTypeOf<{ to: '/workflows'; params: { userId: string } }>().not.toExtend<UserDetailDestination>()
      expectTypeOf<{
        to: typeof ACCESS_MANAGEMENT_DETAIL_ROUTES.user
        params: { groupId: string }
      }>().not.toExtend<UserDetailDestination>()
      expectTypeOf<{ to: typeof ACCESS_MANAGEMENT_DETAIL_ROUTES.user }>().not.toExtend<UserDetailDestination>()
      expectTypeOf<{
        to: typeof ACCESS_MANAGEMENT_DETAIL_ROUTES.serviceAccount
        params: { userId: string }
      }>().not.toExtend<ServiceAccountDetailDestination>()
    })
  })

  describe('getGroupDetailPath', () => {
    it('builds the group detail path', () => {
      expect(getGroupDetailPath('g-456')).toBe('/system-administration/access-management/groups/g-456')
    })
  })

  describe('getProjectDetailPath', () => {
    it('builds the project detail path', () => {
      expect(getProjectDetailPath('proj-456')).toBe('/system-administration/access-management/projects/proj-456')
    })
  })

  describe('getServiceAccountDetailPath', () => {
    it('builds the service account detail path', () => {
      expect(getServiceAccountDetailPath('sa-789')).toBe(
        '/system-administration/access-management/service-accounts/sa-789'
      )
    })
  })

  describe('getPrincipalDetailPath', () => {
    it('routes users to the user detail page', () => {
      expect(getPrincipalDetailPath(RolePrincipalType.USER, 'u-1')).toBe(
        '/system-administration/access-management/users/u-1'
      )
    })

    it('routes groups to the group detail page', () => {
      expect(getPrincipalDetailPath(RolePrincipalType.GROUP, 'g-1')).toBe(
        '/system-administration/access-management/groups/g-1'
      )
    })

    it('routes service accounts to the service account detail page', () => {
      expect(getPrincipalDetailPath(RolePrincipalType.SERVICE_ACCOUNT, 'sa-1')).toBe(
        '/system-administration/access-management/service-accounts/sa-1'
      )
    })
  })
})
