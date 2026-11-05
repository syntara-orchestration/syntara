import { describe, expect, it } from 'vitest'

import { parseSynNumberInputDisplayValue } from './synNumberInputDisplayValue'

describe('parseSynNumberInputDisplayValue', () => {
  it('returns finite numbers as-is', () => {
    expect(parseSynNumberInputDisplayValue(12)).toBe(12)
    expect(parseSynNumberInputDisplayValue(-3.5)).toBe(-3.5)
  })

  it('returns empty string for null, undefined, and empty string', () => {
    expect(parseSynNumberInputDisplayValue(null)).toBe('')
    expect(parseSynNumberInputDisplayValue(undefined)).toBe('')
    expect(parseSynNumberInputDisplayValue('')).toBe('')
  })

  it('parses numeric strings', () => {
    expect(parseSynNumberInputDisplayValue('42')).toBe(42)
    expect(parseSynNumberInputDisplayValue('12.5')).toBe(12.5)
  })

  it('returns empty string for partial or invalid numeric input', () => {
    expect(parseSynNumberInputDisplayValue('-')).toBe('')
    expect(parseSynNumberInputDisplayValue('abc')).toBe('')
  })

  it('returns empty string for non-finite numbers', () => {
    expect(parseSynNumberInputDisplayValue(Number.NaN)).toBe('')
    expect(parseSynNumberInputDisplayValue(Number.POSITIVE_INFINITY)).toBe('')
  })
})
