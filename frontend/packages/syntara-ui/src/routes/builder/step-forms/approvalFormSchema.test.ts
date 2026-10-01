import { describe, expect, it } from 'vitest'

import { approvalFormSchema } from './approvalFormSchema'

describe('approvalFormSchema', () => {
  describe('MAX_APPROVER_USERS limit (100)', () => {
    it('accepts exactly 100 approver users', () => {
      const validData = {
        name: 'Test Approval',
        prompt: 'Please approve',
        approver_users: Array.from({ length: 100 }, (_, i) => `user-${i}`),
      }

      const result = approvalFormSchema.safeParse(validData)
      expect(result.success).toBe(true)
    })

    it('rejects 101 approver users', () => {
      const invalidData = {
        name: 'Test Approval',
        prompt: 'Please approve',
        approver_users: Array.from({ length: 101 }, (_, i) => `user-${i}`),
      }

      const result = approvalFormSchema.safeParse(invalidData)
      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues[0]?.message).toBe('Cannot select more than 100 users')
      }
    })

    it('accepts empty approver_users array', () => {
      const validData = {
        name: 'Test Approval',
        prompt: 'Please approve',
        approver_users: [],
      }

      const result = approvalFormSchema.safeParse(validData)
      expect(result.success).toBe(true)
    })

    it('accepts undefined approver_users', () => {
      const validData = {
        name: 'Test Approval',
        prompt: 'Please approve',
        approver_users: undefined,
      }

      const result = approvalFormSchema.safeParse(validData)
      expect(result.success).toBe(true)
    })
  })

  describe('MAX_APPROVER_GROUPS limit (50)', () => {
    it('accepts exactly 50 approver groups', () => {
      const validData = {
        name: 'Test Approval',
        prompt: 'Please approve',
        approver_groups: Array.from({ length: 50 }, (_, i) => `group-${i}`),
      }

      const result = approvalFormSchema.safeParse(validData)
      expect(result.success).toBe(true)
    })

    it('rejects 51 approver groups', () => {
      const invalidData = {
        name: 'Test Approval',
        prompt: 'Please approve',
        approver_groups: Array.from({ length: 51 }, (_, i) => `group-${i}`),
      }

      const result = approvalFormSchema.safeParse(invalidData)
      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues[0]?.message).toBe('Cannot select more than 50 groups')
      }
    })

    it('accepts empty approver_groups array', () => {
      const validData = {
        name: 'Test Approval',
        prompt: 'Please approve',
        approver_groups: [],
      }

      const result = approvalFormSchema.safeParse(validData)
      expect(result.success).toBe(true)
    })

    it('accepts undefined approver_groups', () => {
      const validData = {
        name: 'Test Approval',
        prompt: 'Please approve',
        approver_groups: undefined,
      }

      const result = approvalFormSchema.safeParse(validData)
      expect(result.success).toBe(true)
    })
  })

  describe('Required fields', () => {
    it('requires name field', () => {
      const invalidData = {
        prompt: 'Please approve',
      }

      const result = approvalFormSchema.safeParse(invalidData)
      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues.some((issue) => issue.path.includes('name'))).toBe(true)
      }
    })

    it('prompt field is optional', () => {
      const validData = {
        name: 'Test Approval',
      }

      const result = approvalFormSchema.safeParse(validData)
      expect(result.success).toBe(true)
    })
  })

  describe('Valid form data', () => {
    it('accepts valid data with all fields', () => {
      const validData = {
        name: 'Production Deployment',
        prompt: 'Please approve this deployment to production',
        approver_users: ['alice', 'bob'],
        approver_groups: ['admins', 'deployers'],
      }

      const result = approvalFormSchema.safeParse(validData)
      expect(result.success).toBe(true)
    })

    it('accepts valid data with only required fields', () => {
      const validData = {
        name: 'Test Approval',
        prompt: 'Please approve',
      }

      const result = approvalFormSchema.safeParse(validData)
      expect(result.success).toBe(true)
    })
  })
})
