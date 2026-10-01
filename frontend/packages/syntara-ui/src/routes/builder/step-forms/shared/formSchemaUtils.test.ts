import { describe, expect, it } from 'vitest'

import { optionalNumber } from './formSchemaUtils'

describe('formSchemaUtils', () => {
  describe('optionalNumber', () => {
    it('accepts a finite number', () => {
      expect(optionalNumber.parse(5)).toBe(5)
      expect(optionalNumber.parse(0)).toBe(0)
    })

    it('transforms NaN to undefined', () => {
      expect(optionalNumber.parse(Number.NaN)).toBeUndefined()
    })

    it('can be chained with optional() for form fields', () => {
      const schema = optionalNumber.optional()
      expect(schema.parse(undefined)).toBeUndefined()
      expect(schema.parse(10)).toBe(10)
      expect(schema.parse(Number.NaN)).toBeUndefined()
    })
  })
})
