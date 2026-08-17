import { describe, expect, it } from 'vitest'

import {
  formatDate,
  formatDateChipValue,
  formatDateYMD,
  formatDateTime,
  formatElapsedTime,
  formatExpirationDate,
  formatTime,
  isSameDay,
  parseDateYMD,
} from './dateUtils'

describe('formatDateYMD', () => {
  it('formats a Date as YYYY-MM-DD', () => {
    expect(formatDateYMD(new Date(2026, 0, 15))).toBe('2026-01-15')
  })

  it('zero-pads single-digit month and day', () => {
    expect(formatDateYMD(new Date(2026, 2, 5))).toBe('2026-03-05')
  })

  it('handles end of year', () => {
    expect(formatDateYMD(new Date(2026, 11, 31))).toBe('2026-12-31')
  })
})

describe('parseDateYMD', () => {
  it('parses a valid YYYY-MM-DD string into a Date', () => {
    const d = parseDateYMD('2026-07-15')
    expect(d.getFullYear()).toBe(2026)
    expect(d.getMonth()).toBe(6)
    expect(d.getDate()).toBe(15)
  })

  it('returns current date for empty string', () => {
    const d = parseDateYMD('')
    const now = new Date()
    expect(d.getFullYear()).toBe(now.getFullYear())
    expect(d.getMonth()).toBe(now.getMonth())
    expect(d.getDate()).toBe(now.getDate())
  })

  it('returns current date for malformed input', () => {
    const d = parseDateYMD('not-a-date')
    expect(Number.isNaN(d.getTime())).toBe(false)
  })
})

describe('formatExpirationDate', () => {
  it('formats an ISO expiration timestamp as "MMM d, yyyy"', () => {
    expect(formatExpirationDate('2026-07-22T00:00:00Z')).toBe('Jul 22, 2026')
  })

  it('extracts date from ISO string to avoid timezone shift', () => {
    expect(formatExpirationDate('2026-01-01T00:00:00Z')).toBe('Jan 1, 2026')
  })

  it('returns "-" for null', () => {
    expect(formatExpirationDate(null)).toBe('-')
  })

  it('returns "-" for undefined', () => {
    expect(formatExpirationDate(undefined)).toBe('-')
  })

  it('returns "-" for empty string', () => {
    expect(formatExpirationDate('')).toBe('-')
  })

  it('returns "-" for malformed ISO string', () => {
    expect(formatExpirationDate('not-a-date')).toBe('-')
  })

  it('returns "-" for string missing date part', () => {
    expect(formatExpirationDate('T00:00:00Z')).toBe('-')
  })
})

describe('formatDate', () => {
  it('formats ISO date string as MMM d, yyyy', () => {
    expect(formatDate('2024-01-15T10:00:00Z')).toMatch(/Jan.*15.*2024/)
  })

  it('returns empty string for empty input', () => {
    expect(formatDate('')).toBe('')
  })

  it('returns empty string for invalid date', () => {
    expect(formatDate('not-a-date')).toBe('')
  })
})

describe('formatTime', () => {
  it('formats time in 12-hour format', () => {
    const result = formatTime('2024-01-15T14:30:00Z')
    expect(result).toMatch(/\d{1,2}:\d{2}\s*(AM|PM)/i)
  })

  it('returns empty string for empty input', () => {
    expect(formatTime('')).toBe('')
  })

  it('returns empty string for invalid date', () => {
    expect(formatTime('not-a-date')).toBe('')
  })
})

describe('formatDateTime', () => {
  it('formats ISO string as date and time', () => {
    const result = formatDateTime('2024-01-15T14:30:00Z')
    expect(result).not.toBe('-')
    expect(result.length).toBeGreaterThan(5)
  })

  it('returns "-" for null', () => {
    expect(formatDateTime(null)).toBe('-')
  })

  it('returns "-" for undefined', () => {
    expect(formatDateTime(undefined)).toBe('-')
  })

  it('returns "-" for empty string', () => {
    expect(formatDateTime('')).toBe('-')
  })

  it('returns "-" for invalid date', () => {
    expect(formatDateTime('not-a-date')).toBe('-')
  })

  it('uses abbreviated month name, not numeric format (AAP-76836)', () => {
    const result = formatDateTime('2026-05-27T09:55:01Z')
    expect(result).toMatch(/May/)
    expect(result).not.toMatch(/^5\//)
  })

  it('includes comma between date and time', () => {
    const result = formatDateTime('2026-01-15T14:30:00Z')
    expect(result).toContain(',')
  })
})

describe('formatElapsedTime', () => {
  it('formats milliseconds as Xh Ym Zs', () => {
    expect(formatElapsedTime(3661000)).toBe('1h 1m 1s')
  })

  it('formats seconds only when under a minute', () => {
    expect(formatElapsedTime(45000)).toBe('45s')
  })

  it('formats hours and minutes', () => {
    expect(formatElapsedTime(7320000)).toBe('2h 2m 0s')
  })

  it('handles zero', () => {
    expect(formatElapsedTime(0)).toBe('0s')
  })

  it('floors negative to zero', () => {
    expect(formatElapsedTime(-1000)).toBe('0s')
  })

  it('formats durations >= 24h as total hours', () => {
    expect(formatElapsedTime(25 * 60 * 60 * 1000)).toBe('25h 0m 0s')
  })

  it('formats 1d 1h 1m 1s as 25h 1m 1s', () => {
    const ms = 24 * 60 * 60 * 1000 + 60 * 60 * 1000 + 60 * 1000 + 1000 // 90061000
    expect(formatElapsedTime(ms)).toBe('25h 1m 1s')
  })
})

describe('isSameDay', () => {
  it('returns true for timestamps on the same day', () => {
    expect(isSameDay('2026-04-16T10:00:00Z', '2026-04-16T23:59:59Z')).toBe(true)
  })

  it('returns false for timestamps on different days', () => {
    expect(isSameDay('2026-04-15T12:00:00Z', '2026-04-17T12:00:00Z')).toBe(false)
  })

  it('returns false for different months', () => {
    expect(isSameDay('2026-03-16T10:00:00Z', '2026-04-16T10:00:00Z')).toBe(false)
  })

  it('returns false for different years', () => {
    expect(isSameDay('2025-04-16T10:00:00Z', '2026-04-16T10:00:00Z')).toBe(false)
  })
})

describe('formatDateChipValue', () => {
  it('extracts date from ISO string', () => {
    expect(formatDateChipValue('2026-04-26T00:00:00.000Z')).toBe('2026-04-26')
  })

  it('extracts date from end-of-day ISO string', () => {
    expect(formatDateChipValue('2026-05-01T23:59:59.999Z')).toBe('2026-05-01')
  })

  it('returns empty string for invalid input', () => {
    expect(formatDateChipValue('')).toBe('')
  })
})
