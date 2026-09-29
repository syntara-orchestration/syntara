import { describe, expect, it } from 'vitest'

import {
  buildAssignmentBody,
  principalTypeDisplay,
  principalTypeLabel,
  RoleAssignmentScope,
  RolePrincipalType,
} from './RoleAssignmentTypes'

describe('RoleAssignmentTypes', () => {
  describe('RoleAssignmentScope', () => {
    it('defines system and project API scope values', () => {
      expect(RoleAssignmentScope).toEqual({ SYSTEM: 'system', PROJECT: 'project' })
    })
  })

  describe('principalTypeDisplay', () => {
    it('maps user principal type to teal User label', () => {
      expect(principalTypeDisplay[RolePrincipalType.USER]).toEqual({ text: 'User', color: 'teal' })
    })

    it('maps group principal type to orange Group label', () => {
      expect(principalTypeDisplay[RolePrincipalType.GROUP]).toEqual({ text: 'Group', color: 'orange' })
    })

    it('maps service account principal type to purple Service account label', () => {
      expect(principalTypeDisplay[RolePrincipalType.SERVICE_ACCOUNT]).toEqual({
        text: 'Service account',
        color: 'purple',
      })
    })
  })

  describe('principalTypeLabel', () => {
    it('provides lowercase labels for each principal type', () => {
      expect(principalTypeLabel).toEqual({
        user: 'user',
        group: 'group',
        service_account: 'service account',
      })
    })
  })

  describe('buildAssignmentBody', () => {
    it('uses group_id for group principals', () => {
      expect(buildAssignmentBody(RolePrincipalType.GROUP, 'g-1', 'admin')).toEqual({
        group_id: 'g-1',
        role_name: 'admin',
      })
    })

    it('uses principal_id for user principals', () => {
      expect(buildAssignmentBody(RolePrincipalType.USER, 'u-1', 'viewer')).toEqual({
        principal_id: 'u-1',
        role_name: 'viewer',
      })
    })

    it('uses principal_id for service account principals', () => {
      expect(buildAssignmentBody(RolePrincipalType.SERVICE_ACCOUNT, 'sa-1', 'editor')).toEqual({
        principal_id: 'sa-1',
        role_name: 'editor',
      })
    })
  })
})
