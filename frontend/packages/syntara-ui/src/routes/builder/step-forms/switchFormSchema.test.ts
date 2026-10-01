import { describe, expect, it } from 'vitest'

import { switchFormSchema } from './switchFormSchema'

describe('switchFormSchema', () => {
  const validCase = {
    caseId: 'test-id',
    condition: '${status} == "active"',
  }

  describe('valid data', () => {
    it('accepts valid switch data with one case', () => {
      const result = switchFormSchema.safeParse({
        name: 'My Switch',
        cases: [validCase],
      })

      expect(result.success).toBe(true)
    })

    it('accepts valid switch data with multiple cases', () => {
      const result = switchFormSchema.safeParse({
        name: '',
        cases: [validCase, { caseId: 'test-2', condition: '${priority} > 5' }],
      })

      expect(result.success).toBe(true)
    })

    it('accepts empty name', () => {
      const result = switchFormSchema.safeParse({
        name: '',
        cases: [validCase],
      })

      expect(result.success).toBe(true)
    })
  })

  describe('permissive validation', () => {
    it('accepts empty cases array', () => {
      const result = switchFormSchema.safeParse({
        name: 'My Switch',
        cases: [],
      })

      expect(result.success).toBe(true)
    })

    it('accepts case with empty condition', () => {
      const result = switchFormSchema.safeParse({
        name: 'My Switch',
        cases: [{ caseId: 'test-id', condition: '' }],
      })

      expect(result.success).toBe(true)
    })

    it('accepts case with no condition', () => {
      const result = switchFormSchema.safeParse({
        name: 'My Switch',
        cases: [{ caseId: 'test-id' }],
      })

      expect(result.success).toBe(true)
    })
  })
})
