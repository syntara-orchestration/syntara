import { describe, expect, it } from 'vitest'

import { isValidIsoCalendarDate } from './isoCalendarDate'

describe('isValidIsoCalendarDate', () => {
  it('accepts typical calendar dates', () => {
    expect(isValidIsoCalendarDate('2026-03-15')).toBe(true)
  })

  it('accepts year 0001', () => {
    expect(isValidIsoCalendarDate('0001-06-15')).toBe(true)
  })

  it('accepts year 0099', () => {
    expect(isValidIsoCalendarDate('0099-12-31')).toBe(true)
  })

  it('rejects invalid month/day combinations', () => {
    expect(isValidIsoCalendarDate('2026-02-30')).toBe(false)
  })

  it('rejects malformed strings', () => {
    expect(isValidIsoCalendarDate('2026/03/15')).toBe(false)
  })
})
