import { describe, expect, it } from 'vitest'

import { createServiceAccountSchema, editServiceAccountSchema } from './serviceAccountFormSchema'

const NAME_REGEX_MESSAGE =
  'Use lowercase letters, numbers, and hyphens only. Must start and end with a letter or number.'

describe('createServiceAccountSchema', () => {
  describe('name validation', () => {
    it('accepts valid service account names', () => {
      const validNames = ['my-sa', 'a', '1', 'sa-123', 'my-service-account', 'a1b2c3']

      validNames.forEach((name) => {
        const result = createServiceAccountSchema.safeParse({ name })
        expect(result.success, `"${name}" should be valid`).toBe(true)
      })
    })

    it('rejects empty name', () => {
      const result = createServiceAccountSchema.safeParse({
        name: '',
      })

      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues[0].message).toBe('Name is required')
      }
    })

    it('enforces max length of 255 characters', () => {
      const result = createServiceAccountSchema.safeParse({
        name: 'a'.repeat(256),
      })

      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues[0].message).toBe('Name must be 255 characters or fewer')
      }
    })

    it('accepts name at exactly 255 characters', () => {
      const result = createServiceAccountSchema.safeParse({
        name: 'a'.repeat(255),
      })

      expect(result.success).toBe(true)
    })

    it('rejects uppercase letters', () => {
      const result = createServiceAccountSchema.safeParse({
        name: 'MyAccount',
      })

      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues[0].message).toBe(NAME_REGEX_MESSAGE)
      }
    })

    it('rejects names with spaces', () => {
      const result = createServiceAccountSchema.safeParse({
        name: 'my account',
      })

      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues[0].message).toBe(NAME_REGEX_MESSAGE)
      }
    })

    it('rejects names starting with a hyphen', () => {
      const result = createServiceAccountSchema.safeParse({
        name: '-my-sa',
      })

      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues[0].message).toBe(NAME_REGEX_MESSAGE)
      }
    })

    it('rejects names ending with a hyphen', () => {
      const result = createServiceAccountSchema.safeParse({
        name: 'my-sa-',
      })

      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues[0].message).toBe(NAME_REGEX_MESSAGE)
      }
    })

    it('rejects names with special characters', () => {
      const invalidNames = ['sa@test', 'sa#test', 'sa_test', 'sa.test', 'sa/test', 'sa:test']

      invalidNames.forEach((name) => {
        const result = createServiceAccountSchema.safeParse({
          name,
        })
        expect(result.success, `"${name}" should be invalid`).toBe(false)
        if (!result.success) {
          expect(result.error.issues[0].message).toBe(NAME_REGEX_MESSAGE)
        }
      })
    })
  })

  describe('description validation', () => {
    it('accepts descriptions up to 2000 characters', () => {
      const result = createServiceAccountSchema.safeParse({
        name: 'my-sa',
        description: 'a'.repeat(2000),
      })

      expect(result.success).toBe(true)
    })

    it('rejects descriptions over 2000 characters', () => {
      const result = createServiceAccountSchema.safeParse({
        name: 'my-sa',
        description: 'a'.repeat(2001),
      })

      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues[0].message).toBe('Description must be 2000 characters or fewer')
      }
    })

    it('accepts null description', () => {
      const result = createServiceAccountSchema.safeParse({
        name: 'my-sa',
        description: null,
      })

      expect(result.success).toBe(true)
    })

    it('accepts undefined description', () => {
      const result = createServiceAccountSchema.safeParse({
        name: 'my-sa',
      })

      expect(result.success).toBe(true)
    })
  })

  it('creates an identity without a project', () => {
    expect(createServiceAccountSchema.parse({ name: 'my-sa' })).toEqual({ name: 'my-sa' })
  })
})

describe('editServiceAccountSchema', () => {
  it('accepts valid name and description', () => {
    const result = editServiceAccountSchema.safeParse({
      name: 'my-service-account',
      description: 'A test service account',
    })

    expect(result.success).toBe(true)
  })

  it('does not require project_id', () => {
    const result = editServiceAccountSchema.safeParse({
      name: 'my-sa',
    })

    expect(result.success).toBe(true)
  })

  it('applies the same name validation as create', () => {
    const result = editServiceAccountSchema.safeParse({
      name: 'Invalid Name',
    })

    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues[0].message).toBe(NAME_REGEX_MESSAGE)
    }
  })

  it('rejects empty name', () => {
    const result = editServiceAccountSchema.safeParse({
      name: '',
    })

    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues[0].message).toBe('Name is required')
    }
  })

  it('applies the same description limits as create', () => {
    const result = editServiceAccountSchema.safeParse({
      name: 'my-sa',
      description: 'a'.repeat(2001),
    })

    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues[0].message).toBe('Description must be 2000 characters or fewer')
    }
  })
})
