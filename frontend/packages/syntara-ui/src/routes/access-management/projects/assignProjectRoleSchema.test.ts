import { describe, expect, it } from 'vitest'

import { RolePrincipalType } from '../RoleAssignmentTypes'

import { assignProjectRoleSchema } from './assignProjectRoleSchema'

const validBase = {
  userId: '',
  groupId: '',
  serviceAccountId: '',
  roleName: '',
}

describe('assignProjectRoleSchema', () => {
  describe('user assignment', () => {
    it('passes when userId and roleName are provided', () => {
      const result = assignProjectRoleSchema.safeParse({
        ...validBase,
        principalType: RolePrincipalType.USER,
        userId: 'u1',
        roleName: 'admin',
      })
      expect(result.success).toBe(true)
    })

    it('fails when userId is empty', () => {
      const result = assignProjectRoleSchema.safeParse({
        ...validBase,
        principalType: RolePrincipalType.USER,
        roleName: 'admin',
      })
      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues.some((i) => i.path.includes('userId'))).toBe(true)
      }
    })

    it('fails when roleName is empty', () => {
      const result = assignProjectRoleSchema.safeParse({
        ...validBase,
        principalType: RolePrincipalType.USER,
        userId: 'u1',
      })
      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues.some((i) => i.path.includes('roleName'))).toBe(true)
      }
    })
  })

  describe('group assignment', () => {
    it('passes when groupId and roleName are provided', () => {
      const result = assignProjectRoleSchema.safeParse({
        ...validBase,
        principalType: RolePrincipalType.GROUP,
        groupId: 'g1',
        roleName: 'viewer',
      })
      expect(result.success).toBe(true)
    })

    it('fails when groupId is empty', () => {
      const result = assignProjectRoleSchema.safeParse({
        ...validBase,
        principalType: RolePrincipalType.GROUP,
        roleName: 'viewer',
      })
      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues.some((i) => i.path.includes('groupId'))).toBe(true)
      }
    })
  })

  describe('service_account assignment', () => {
    it('passes when serviceAccountId and roleName are provided', () => {
      const result = assignProjectRoleSchema.safeParse({
        ...validBase,
        principalType: RolePrincipalType.SERVICE_ACCOUNT,
        serviceAccountId: 'sa-1',
        roleName: 'editor',
      })
      expect(result.success).toBe(true)
    })

    it('fails when serviceAccountId is empty', () => {
      const result = assignProjectRoleSchema.safeParse({
        ...validBase,
        principalType: RolePrincipalType.SERVICE_ACCOUNT,
        roleName: 'editor',
      })
      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues.some((i) => i.path.includes('serviceAccountId'))).toBe(true)
      }
    })

    it('fails when roleName is empty', () => {
      const result = assignProjectRoleSchema.safeParse({
        ...validBase,
        principalType: RolePrincipalType.SERVICE_ACCOUNT,
        serviceAccountId: 'sa-1',
      })
      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues.some((i) => i.path.includes('roleName'))).toBe(true)
      }
    })
  })

  describe('invalid principalType', () => {
    it('fails for unknown principal type', () => {
      const result = assignProjectRoleSchema.safeParse({
        ...validBase,
        principalType: 'invalid',
      })
      expect(result.success).toBe(false)
    })
  })
})
