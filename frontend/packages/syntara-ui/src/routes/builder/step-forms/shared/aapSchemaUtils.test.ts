import { describe, expect, it } from 'vitest'
import type { z } from 'zod'

import { hasAnyExpressionValue, isValidTemplateId, validateExtraVars } from './aapSchemaUtils'

describe('aapSchemaUtils', () => {
  describe('validateExtraVars', () => {
    it('allows valid JSON object', () => {
      const issues: unknown[] = []
      const mockCtx = {
        addIssue: (issue: unknown) => {
          issues.push(issue)
        },
      } as z.RefinementCtx
      validateExtraVars('{"key": "value"}', mockCtx)
      expect(issues).toHaveLength(0)
    })

    it('rejects null value', () => {
      const issues: unknown[] = []
      const mockCtx = {
        addIssue: (issue: unknown) => {
          issues.push(issue)
        },
      } as z.RefinementCtx
      validateExtraVars('null', mockCtx)
      expect(issues).toHaveLength(1)
      expect((issues[0] as { message: string }).message).toBe('Extra variables must be a JSON object')
    })

    it('rejects array value', () => {
      const issues: unknown[] = []
      const mockCtx = {
        addIssue: (issue: unknown) => {
          issues.push(issue)
        },
      } as z.RefinementCtx
      validateExtraVars('["item"]', mockCtx)
      expect(issues).toHaveLength(1)
      expect((issues[0] as { message: string }).message).toBe('Extra variables must be a JSON object')
    })

    it('rejects invalid JSON', () => {
      const issues: unknown[] = []
      const mockCtx = {
        addIssue: (issue: unknown) => {
          issues.push(issue)
        },
      } as z.RefinementCtx
      validateExtraVars('{invalid}', mockCtx)
      expect(issues).toHaveLength(1)
      expect((issues[0] as { message: string }).message).toBe('Invalid JSON format')
    })

    it('allows empty or undefined value', () => {
      const issues: unknown[] = []
      const mockCtx = {
        addIssue: (issue: unknown) => {
          issues.push(issue)
        },
      } as z.RefinementCtx
      validateExtraVars('', mockCtx)
      validateExtraVars('   ', mockCtx)
      validateExtraVars(undefined, mockCtx)
      expect(issues).toHaveLength(0)
    })

    it('uses custom field path', () => {
      const issues: unknown[] = []
      const mockCtx = {
        addIssue: (issue: unknown) => {
          issues.push(issue)
        },
      } as z.RefinementCtx
      validateExtraVars('invalid', mockCtx, ['custom', 'path'])
      expect(issues).toHaveLength(1)
      expect((issues[0] as { path: string[] }).path).toEqual(['custom', 'path'])
    })
  })

  describe('isValidTemplateId', () => {
    it('returns true for valid positive integers', () => {
      expect(isValidTemplateId(1)).toBe(true)
      expect(isValidTemplateId(100)).toBe(true)
      expect(isValidTemplateId(999999)).toBe(true)
    })

    it('returns true for undefined', () => {
      expect(isValidTemplateId(undefined)).toBe(true)
    })

    it('returns false for zero', () => {
      expect(isValidTemplateId(0)).toBe(false)
    })

    it('returns false for negative numbers', () => {
      expect(isValidTemplateId(-1)).toBe(false)
      expect(isValidTemplateId(-100)).toBe(false)
    })

    it('returns false for non-integers', () => {
      expect(isValidTemplateId(1.5)).toBe(false)
      expect(isValidTemplateId(Number.NaN)).toBe(false)
      expect(isValidTemplateId(Number.POSITIVE_INFINITY)).toBe(false)
    })
  })

  describe('hasAnyExpressionValue', () => {
    it('detects ${...} expressions', () => {
      expect(hasAnyExpressionValue('${variable}')).toBe(true)
      expect(hasAnyExpressionValue('prefix ${var} suffix')).toBe(true)
    })

    it('detects {{...}} expressions', () => {
      expect(hasAnyExpressionValue('{{variable}}')).toBe(true)
      expect(hasAnyExpressionValue('prefix {{var}} suffix')).toBe(true)
    })

    it('returns false for plain strings', () => {
      expect(hasAnyExpressionValue('plain text')).toBe(false)
      expect(hasAnyExpressionValue('no expressions here')).toBe(false)
    })

    it('returns false for empty or undefined values', () => {
      expect(hasAnyExpressionValue('')).toBe(false)
      expect(hasAnyExpressionValue('   ')).toBe(false)
      expect(hasAnyExpressionValue(undefined)).toBe(false)
    })

    it('returns true if any value has expression', () => {
      expect(hasAnyExpressionValue('plain', '${expr}', 'another')).toBe(true)
      expect(hasAnyExpressionValue('plain', 'another', '{{expr}}')).toBe(true)
    })

    it('returns false if no values have expressions', () => {
      expect(hasAnyExpressionValue('plain', 'another', 'text')).toBe(false)
      expect(hasAnyExpressionValue(undefined, '', '   ')).toBe(false)
    })

    it('handles mixed undefined and expression values', () => {
      expect(hasAnyExpressionValue(undefined, '${expr}', undefined)).toBe(true)
      expect(hasAnyExpressionValue(undefined, 'plain', undefined)).toBe(false)
    })
  })
})
