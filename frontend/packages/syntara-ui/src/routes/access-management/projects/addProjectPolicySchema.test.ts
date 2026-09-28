import { describe, expect, it } from 'vitest'

import { addProjectPolicySchema, policyStatementSchema } from './addProjectPolicySchema'

describe('policyStatementSchema', () => {
  const validStatement = { effect: 'allow', actions: ['read'], scope: 'any' }

  it('accepts a valid statement', () => {
    expect(policyStatementSchema.safeParse(validStatement).success).toBe(true)
  })

  it('accepts deny effect', () => {
    expect(policyStatementSchema.safeParse({ ...validStatement, effect: 'deny' }).success).toBe(true)
  })

  it('rejects invalid effect', () => {
    expect(policyStatementSchema.safeParse({ ...validStatement, effect: 'permit' }).success).toBe(false)
  })

  it('rejects empty actions array', () => {
    expect(policyStatementSchema.safeParse({ ...validStatement, actions: [] }).success).toBe(false)
  })

  it('accepts self scope', () => {
    expect(policyStatementSchema.safeParse({ ...validStatement, scope: 'self' }).success).toBe(true)
  })

  it('rejects invalid scope', () => {
    expect(policyStatementSchema.safeParse({ ...validStatement, scope: 'global' }).success).toBe(false)
  })

  it('accepts optional conditions', () => {
    expect(policyStatementSchema.safeParse({ ...validStatement, conditions: { key: 'val' } }).success).toBe(true)
  })

  it('accepts null conditions', () => {
    expect(policyStatementSchema.safeParse({ ...validStatement, conditions: null }).success).toBe(true)
  })

  it('accepts omitted conditions', () => {
    const noConditions = { effect: validStatement.effect, actions: validStatement.actions, scope: validStatement.scope }
    expect(policyStatementSchema.safeParse(noConditions).success).toBe(true)
  })
})

describe('addProjectPolicySchema', () => {
  const validStatements = JSON.stringify([{ effect: 'allow', actions: ['read'], scope: 'any' }])
  const validData = { name: 'my-policy', description: '', statementsJson: validStatements }

  describe('name', () => {
    it('accepts valid lowercase alphanumeric name', () => {
      expect(addProjectPolicySchema.safeParse(validData).success).toBe(true)
    })

    it('rejects empty name', () => {
      expect(addProjectPolicySchema.safeParse({ ...validData, name: '' }).success).toBe(false)
    })

    it('rejects uppercase characters', () => {
      expect(addProjectPolicySchema.safeParse({ ...validData, name: 'MyPolicy' }).success).toBe(false)
    })

    it('rejects name starting with a hyphen', () => {
      expect(addProjectPolicySchema.safeParse({ ...validData, name: '-policy' }).success).toBe(false)
    })

    it('rejects name exceeding 255 characters', () => {
      expect(addProjectPolicySchema.safeParse({ ...validData, name: 'a'.repeat(256) }).success).toBe(false)
    })
  })

  describe('description', () => {
    it('accepts empty string', () => {
      expect(addProjectPolicySchema.safeParse({ ...validData, description: '' }).success).toBe(true)
    })

    it('accepts omitted description', () => {
      const noDesc = { name: validData.name, statementsJson: validData.statementsJson }
      expect(addProjectPolicySchema.safeParse(noDesc).success).toBe(true)
    })

    it('rejects description exceeding 1024 characters', () => {
      expect(addProjectPolicySchema.safeParse({ ...validData, description: 'x'.repeat(1025) }).success).toBe(false)
    })
  })

  describe('statementsJson', () => {
    it('accepts valid JSON array of statements', () => {
      expect(addProjectPolicySchema.safeParse(validData).success).toBe(true)
    })

    it('rejects empty string', () => {
      expect(addProjectPolicySchema.safeParse({ ...validData, statementsJson: '' }).success).toBe(false)
    })

    it('rejects invalid JSON', () => {
      expect(addProjectPolicySchema.safeParse({ ...validData, statementsJson: 'not json' }).success).toBe(false)
    })

    it('rejects non-array JSON', () => {
      expect(addProjectPolicySchema.safeParse({ ...validData, statementsJson: '{}' }).success).toBe(false)
    })

    it('rejects statement with missing required fields', () => {
      const statementsJson = JSON.stringify([{ effect: 'allow' }])
      expect(addProjectPolicySchema.safeParse({ ...validData, statementsJson }).success).toBe(false)
    })

    it('rejects statement with empty actions', () => {
      const statementsJson = JSON.stringify([{ effect: 'allow', actions: [], scope: 'any' }])
      expect(addProjectPolicySchema.safeParse({ ...validData, statementsJson }).success).toBe(false)
    })

    it('rejects statement with invalid effect enum', () => {
      const statementsJson = JSON.stringify([{ effect: 'permit', actions: ['read'], scope: 'any' }])
      expect(addProjectPolicySchema.safeParse({ ...validData, statementsJson }).success).toBe(false)
    })

    it('rejects statement with invalid scope enum', () => {
      const statementsJson = JSON.stringify([{ effect: 'allow', actions: ['read'], scope: 'global' }])
      expect(addProjectPolicySchema.safeParse({ ...validData, statementsJson }).success).toBe(false)
    })

    it('accepts multiple valid statements', () => {
      const statementsJson = JSON.stringify([
        { effect: 'allow', actions: ['read'], scope: 'any' },
        { effect: 'deny', actions: ['write', 'delete'], scope: 'self' },
      ])
      expect(addProjectPolicySchema.safeParse({ ...validData, statementsJson }).success).toBe(true)
    })
  })
})
