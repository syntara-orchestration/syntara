import { describe, expect, it } from 'vitest'

import {
  parseRepeatingInterval,
  durationToHumanReadableCadence,
  formatIntervalDescription,
  formatScheduleSummary,
  frequencyAndIntervalToDuration,
  durationToFrequencyAndInterval,
  buildRepeatingInterval,
  getDefaultRepeatingInterval,
  getTimezoneOffset,
} from './triggerFormatting'

describe('parseRepeatingInterval', () => {
  it('parses interval with start and duration', () => {
    const result = parseRepeatingInterval('R/2024-01-01T10:00:00Z/P1D')

    expect(result).toEqual({
      start: '2024-01-01T10:00:00Z',
      cadence: 'P1D',
    })
  })

  it('parses interval with start, duration, and end', () => {
    const result = parseRepeatingInterval('R/2024-01-01T10:00:00Z/P1D/2024-12-31T23:59:59Z')

    expect(result).toEqual({
      start: '2024-01-01T10:00:00Z',
      cadence: 'P1D',
      end: '2024-12-31T23:59:59Z',
    })
  })

  it('parses run-once interval R1/start/PT0S', () => {
    const result = parseRepeatingInterval('R1/2024-01-15T00:00:00.000Z/PT0S')

    expect(result).toEqual({
      start: '2024-01-15T00:00:00.000Z',
      cadence: 'PT0S',
    })
  })

  it('returns empty values for invalid format', () => {
    expect(parseRepeatingInterval('')).toEqual({ start: '', cadence: '' })
    expect(parseRepeatingInterval('invalid')).toEqual({ start: '', cadence: '' })
    expect(parseRepeatingInterval('2024-01-01/P1D')).toEqual({ start: '', cadence: '' })
  })

  it('returns empty values for null-like input', () => {
    expect(parseRepeatingInterval(null as unknown as string)).toEqual({ start: '', cadence: '' })
  })
})

describe('durationToHumanReadableCadence', () => {
  it('converts P1D to Daily', () => {
    expect(durationToHumanReadableCadence('P1D')).toBe('Daily')
  })

  it('converts P7D to Every 7 days', () => {
    expect(durationToHumanReadableCadence('P7D')).toBe('Every 7 days')
  })

  it('converts P1W to Weekly', () => {
    expect(durationToHumanReadableCadence('P1W')).toBe('Weekly')
  })

  it('converts P1M to Monthly', () => {
    expect(durationToHumanReadableCadence('P1M')).toBe('Monthly')
  })

  it('converts P1Y to Yearly', () => {
    expect(durationToHumanReadableCadence('P1Y')).toBe('Yearly')
  })

  it('converts PT1H to Hourly', () => {
    expect(durationToHumanReadableCadence('PT1H')).toBe('Hourly')
  })

  it('converts multi-unit durations to human-readable', () => {
    expect(durationToHumanReadableCadence('P2D')).toBe('Every 2 days')
    expect(durationToHumanReadableCadence('PT30M')).toBe('Every 30 minutes')
    expect(durationToHumanReadableCadence('P3W')).toBe('Every 3 weeks')
  })

  it('returns "Does not repeat" for compound durations', () => {
    expect(durationToHumanReadableCadence('P1DT12H')).toBe('Does not repeat')
  })

  it('returns "Does not repeat" for empty input', () => {
    expect(durationToHumanReadableCadence('')).toBe('Does not repeat')
  })

  it('handles case-insensitive input', () => {
    expect(durationToHumanReadableCadence('p1d')).toBe('Daily')
    expect(durationToHumanReadableCadence('p1m')).toBe('Monthly')
  })

  it('trims whitespace', () => {
    expect(durationToHumanReadableCadence('  P1D  ')).toBe('Daily')
  })
})

describe('formatIntervalDescription', () => {
  it('formats complete interval description', () => {
    const result = formatIntervalDescription('R/2024-01-15T10:00:00Z/P1D')

    expect(result).toContain('Starts')
    expect(result).toContain('Repeats daily')
  })

  it('includes end date when present', () => {
    const result = formatIntervalDescription('R/2024-01-15T10:00:00Z/P1D/2024-12-31T23:59:59Z')

    expect(result).toContain('Ends')
  })

  it('returns empty string for invalid interval', () => {
    expect(formatIntervalDescription('')).toBe('')
    expect(formatIntervalDescription('invalid')).toBe('')
  })
})

describe('formatScheduleSummary', () => {
  it('formats daily schedule', () => {
    const result = formatScheduleSummary('R/2024-01-01T10:00:00Z/P1D')
    expect(result).toMatch(/^Daily at \d{1,2}:\d{2} [AP]M starting \w{3} \d{1,2}, 2024$/)
  })

  it('formats weekly schedule with P7D', () => {
    const result = formatScheduleSummary('R/2024-03-15T14:30:00Z/P7D')
    expect(result).toMatch(/^Every 7 days at \d{1,2}:\d{2} [AP]M starting \w{3} \d{1,2}, 2024$/)
  })

  it('formats weekly schedule with P1W', () => {
    const result = formatScheduleSummary('R/2024-03-15T14:30:00Z/P1W')
    expect(result).toMatch(/^Weekly at \d{1,2}:\d{2} [AP]M starting \w{3} \d{1,2}, 2024$/)
  })

  it('formats monthly schedule', () => {
    const result = formatScheduleSummary('R/2026-06-05T10:00:00Z/P1M')
    expect(result).toMatch(/^Monthly at \d{1,2}:\d{2} [AP]M starting \w{3} \d{1,2}, 2026$/)
  })

  it('formats yearly schedule', () => {
    const result = formatScheduleSummary('R/2024-01-01T00:00:00Z/P1Y')
    expect(result).toMatch(/^Yearly at \d{1,2}:\d{2} [AP]M starting \w{3} \d{1,2}, 202[34]$/)
  })

  it('includes end date when present', () => {
    const result = formatScheduleSummary('R/2024-01-01T10:00:00Z/P1D/2024-12-31T23:59:59Z')
    expect(result).toMatch(/^Daily at .+ starting .+, ending \w{3} \d{1,2}, 2024$/)
  })

  it('formats run-once schedule', () => {
    const result = formatScheduleSummary('R1/2024-01-15T00:00:00Z/PT0S')
    expect(result).toMatch(/^Once on \w{3} \d{1,2}, 2024 at \d{1,2}:\d{2} [AP]M$/)
  })

  it('formats hourly schedule', () => {
    const result = formatScheduleSummary('R/2024-01-01T10:00:00Z/PT1H')
    expect(result).toMatch(/^Hourly at \d{1,2}:\d{2} [AP]M starting \w{3} \d{1,2}, 2024$/)
  })

  it('returns null for non-ISO format', () => {
    expect(formatScheduleSummary('1h')).toBeNull()
  })

  it('returns null for empty input', () => {
    expect(formatScheduleSummary('')).toBeNull()
  })

  it('returns null for invalid input', () => {
    expect(formatScheduleSummary('invalid')).toBeNull()
  })
})

describe('frequencyAndIntervalToDuration', () => {
  it('converts daily frequency', () => {
    expect(frequencyAndIntervalToDuration('daily', 1)).toBe('P1D')
    expect(frequencyAndIntervalToDuration('daily', 3)).toBe('P3D')
  })

  it('converts weekly frequency', () => {
    expect(frequencyAndIntervalToDuration('weekly', 1)).toBe('P1W')
    expect(frequencyAndIntervalToDuration('weekly', 2)).toBe('P2W')
  })

  it('converts monthly frequency', () => {
    expect(frequencyAndIntervalToDuration('monthly', 1)).toBe('P1M')
  })

  it('converts yearly frequency', () => {
    expect(frequencyAndIntervalToDuration('yearly', 1)).toBe('P1Y')
  })

  it('converts minutely frequency', () => {
    expect(frequencyAndIntervalToDuration('minutely', 5)).toBe('PT5M')
  })

  it('converts hourly frequency', () => {
    expect(frequencyAndIntervalToDuration('hourly', 2)).toBe('PT2H')
  })

  it('returns empty string for none', () => {
    expect(frequencyAndIntervalToDuration('none', 1)).toBe('')
  })

  it('clamps count to minimum 1', () => {
    expect(frequencyAndIntervalToDuration('daily', 0)).toBe('P1D')
    expect(frequencyAndIntervalToDuration('daily', -5)).toBe('P1D')
  })
})

describe('durationToFrequencyAndInterval', () => {
  it('parses daily duration', () => {
    expect(durationToFrequencyAndInterval('P1D')).toEqual({ frequency: 'daily', count: 1 })
    expect(durationToFrequencyAndInterval('P3D')).toEqual({ frequency: 'daily', count: 3 })
  })

  it('parses weekly duration', () => {
    expect(durationToFrequencyAndInterval('P1W')).toEqual({ frequency: 'weekly', count: 1 })
    expect(durationToFrequencyAndInterval('P2W')).toEqual({ frequency: 'weekly', count: 2 })
  })

  it('parses monthly duration', () => {
    expect(durationToFrequencyAndInterval('P1M')).toEqual({ frequency: 'monthly', count: 1 })
  })

  it('parses yearly duration', () => {
    expect(durationToFrequencyAndInterval('P1Y')).toEqual({ frequency: 'yearly', count: 1 })
  })

  it('parses minutely duration', () => {
    expect(durationToFrequencyAndInterval('PT5M')).toEqual({ frequency: 'minutely', count: 5 })
  })

  it('parses hourly duration', () => {
    expect(durationToFrequencyAndInterval('PT2H')).toEqual({ frequency: 'hourly', count: 2 })
  })

  it('returns none for empty input', () => {
    expect(durationToFrequencyAndInterval('')).toEqual({ frequency: 'none', count: 1 })
  })

  it('returns none for PT0S (run-once)', () => {
    expect(durationToFrequencyAndInterval('PT0S')).toEqual({ frequency: 'none', count: 1 })
  })

  it('returns none for compound durations', () => {
    expect(durationToFrequencyAndInterval('P1DT12H')).toEqual({ frequency: 'none', count: 1 })
    expect(durationToFrequencyAndInterval('P1MT5M')).toEqual({ frequency: 'none', count: 1 })
  })

  it('round-trips with frequencyAndIntervalToDuration', () => {
    const cases: Array<[string, number]> = [
      ['daily', 2],
      ['weekly', 3],
      ['monthly', 1],
      ['yearly', 1],
      ['minutely', 15],
      ['hourly', 4],
    ]
    for (const [freq, count] of cases) {
      const duration = frequencyAndIntervalToDuration(freq as 'daily', count)
      const result = durationToFrequencyAndInterval(duration)
      expect(result).toEqual({ frequency: freq, count })
    }
  })
})

describe('buildRepeatingInterval', () => {
  it('builds a daily interval from explicit start fields', () => {
    const result = buildRepeatingInterval({
      startDate: '2024-01-15',
      startTime: '10:00',
      frequency: 'daily',
      intervalCount: 1,
      timezone: 'UTC',
    })

    expect(result).toContain('2024-01-15T10:00:00')
    expect(result).toContain('/P1D')
    expect(result.startsWith('R/')).toBe(true)
  })

  it('appends end date when provided', () => {
    const result = buildRepeatingInterval({
      startDate: '2024-01-15',
      startTime: '10:00',
      endDate: '2024-12-31',
      frequency: 'daily',
      intervalCount: 1,
      timezone: 'UTC',
    })

    expect(result).toContain('2024-12-31T23:59:59')
  })

  it('builds a run-once interval when frequency is none', () => {
    const result = buildRepeatingInterval({
      startDate: '2024-01-15',
      startTime: '10:00',
      frequency: 'none',
      intervalCount: 1,
      timezone: 'UTC',
    })

    expect(result.startsWith('R1/')).toBe(true)
    expect(result.endsWith('/PT0S')).toBe(true)
  })
})

describe('getDefaultRepeatingInterval', () => {
  it('returns a run-once interval starting from now', () => {
    const now = new Date('2026-08-14T18:05:00')
    const result = getDefaultRepeatingInterval('UTC', now)

    expect(result.startsWith('R1/')).toBe(true)
    expect(result.endsWith('/PT0S')).toBe(true)
    expect(result).toContain('2026-08-14')
  })
})

describe('getTimezoneOffset', () => {
  it('returns a zero offset for UTC', () => {
    const offset = getTimezoneOffset('UTC', '2026-01-15')

    expect(offset === 'Z' || offset === '+00:00').toBe(true)
  })

  it('returns the winter offset for America/New_York', () => {
    expect(getTimezoneOffset('America/New_York', '2026-01-15')).toBe('-05:00')
  })

  it('returns Z for an invalid timezone', () => {
    expect(getTimezoneOffset('Not/AZone', '2026-01-15')).toBe('Z')
  })
})
