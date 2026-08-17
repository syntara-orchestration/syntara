/**
 * Utilities for formatting and parsing trigger-related data
 * Used for displaying human-readable trigger information in nodes and forms
 */

import { formatDate, formatTime } from './dateUtils'

/**
 * Parsed repeating interval structure
 */
export type ParsedRepeatingInterval = {
  start: string
  cadence: string
  end?: string
}

/**
 * Parse an ISO 8601 repeating interval string into components.
 * Supports: "R/start/duration", "R/start/duration/end", and run-once "R1/start/PT0S".
 */
export function parseRepeatingInterval(interval: string): ParsedRepeatingInterval {
  if (!interval?.startsWith('R')) {
    return { start: '', cadence: '' }
  }

  // R1/start/PT0S (run once) or R/start/duration[/end]
  const withoutPrefix = interval.startsWith('R/')
    ? interval.substring(2)
    : interval.substring(interval.indexOf('/') + 1)
  const parts = withoutPrefix.split('/')

  if (parts.length === 2) {
    return { start: parts[0], cadence: parts[1] }
  }
  if (parts.length === 3) {
    return { start: parts[0], cadence: parts[1], end: parts[2] }
  }

  return { start: '', cadence: '' }
}

export type ScheduleFrequency = 'none' | 'minutely' | 'hourly' | 'daily' | 'weekly' | 'monthly' | 'yearly'

const DATE_COMPONENT_PATTERN = /(\d+)([YMWD])/g
const TIME_COMPONENT_PATTERN = /(\d+)([HMS])/g

function parseComponents(pattern: RegExp, str: string): Record<string, number> {
  const result: Record<string, number> = {}
  let m: RegExpExecArray | null = null
  while ((m = pattern.exec(str)) !== null) {
    result[m[2]] = Number(m[1])
  }
  pattern.lastIndex = 0
  return result
}

function parseDurationComponents(duration: string): Record<string, number> {
  const upper = duration.toUpperCase()
  const tIndex = upper.indexOf('T')
  const datePart = tIndex === -1 ? upper : upper.substring(0, tIndex)
  const result = parseComponents(DATE_COMPONENT_PATTERN, datePart)
  if (tIndex !== -1) {
    const timePart = upper.substring(tIndex + 1)
    const timeComponents = parseComponents(TIME_COMPONENT_PATTERN, timePart)
    if (timeComponents.M !== undefined) {
      result.Min = timeComponents.M
      delete timeComponents.M
    }
    Object.assign(result, timeComponents)
  }
  return result
}

/**
 * Convert a schedule frequency and interval count to an ISO 8601 duration string.
 * Example: ('daily', 2) -> 'P2D', ('weekly', 3) -> 'P3W'
 */
export function frequencyAndIntervalToDuration(frequency: ScheduleFrequency, count: number): string {
  const n = Math.max(1, Math.floor(count))
  switch (frequency) {
    case 'minutely':
      return `PT${n}M`
    case 'hourly':
      return `PT${n}H`
    case 'daily':
      return `P${n}D`
    case 'weekly':
      return `P${n}W`
    case 'monthly':
      return `P${n}M`
    case 'yearly':
      return `P${n}Y`
    case 'none':
    default:
      return ''
  }
}

/**
 * Convert an ISO 8601 duration string to a schedule frequency and interval count.
 * Example: 'P2D' -> { frequency: 'daily', count: 2 }
 */
export function durationToFrequencyAndInterval(duration: string): { frequency: ScheduleFrequency; count: number } {
  if (!duration || duration === 'PT0S') return { frequency: 'none', count: 1 }

  const components = parseDurationComponents(duration.trim())
  const entries = Object.entries(components).filter(([, v]) => v > 0)

  if (entries.length !== 1) return { frequency: 'none', count: 1 }

  const [unit, count] = entries[0]
  const unitToFrequency: Record<string, ScheduleFrequency> = {
    Y: 'yearly',
    M: 'monthly',
    W: 'weekly',
    D: 'daily',
    H: 'hourly',
    Min: 'minutely',
  }

  return { frequency: unitToFrequency[unit] ?? 'none', count }
}

/**
 * Convert ISO 8601 duration string to human-readable cadence
 */
export function durationToHumanReadableCadence(duration: string): string {
  if (!duration) return 'Does not repeat'

  const { frequency, count } = durationToFrequencyAndInterval(duration)
  if (frequency === 'none') return 'Does not repeat'

  const labels: Record<ScheduleFrequency, [string, string]> = {
    none: ['Does not repeat', 'Does not repeat'],
    minutely: ['Every minute', 'minutes'],
    hourly: ['Hourly', 'hours'],
    daily: ['Daily', 'days'],
    weekly: ['Weekly', 'weeks'],
    monthly: ['Monthly', 'months'],
    yearly: ['Yearly', 'years'],
  }
  const [singular, plural] = labels[frequency]
  return count === 1 ? singular : `Every ${count} ${plural}`
}

/**
 * Format ISO 8601 interval string to human-readable description
 * Example: "Starts Jan 1, 2026 at 12:00 AM\nRepeats weekly\nEnds Feb 6, 2026"
 */
export function formatIntervalDescription(interval: string): string {
  const parsed = parseRepeatingInterval(interval)
  if (!parsed.start || !parsed.cadence) return ''

  const startDate = formatDate(parsed.start)
  const startTime = formatTime(parsed.start)
  const cadence = durationToHumanReadableCadence(parsed.cadence)
  const endDate = parsed.end ? formatDate(parsed.end) : null

  const parts: string[] = []

  if (startDate) {
    const startLine = startTime ? `Starts ${startDate} at ${startTime}` : `Starts ${startDate}`
    parts.push(startLine)
  }

  // Check the raw duration value instead of the translated string
  if (parsed.cadence) {
    parts.push(`Repeats ${cadence.toLowerCase()}`)
  }

  if (endDate) {
    parts.push(`Ends ${endDate}`)
  }

  return parts.join('\n')
}

/**
 * Format an ISO 8601 repeating interval as a single-line plain-language summary.
 * Returns null if the interval cannot be parsed into a supported format.
 *
 * Examples:
 * - "Daily at 10:00 AM starting Jan 1, 2024"
 * - "Weekly at 2:30 PM starting Jan 1, 2024, ending Dec 31, 2024"
 * - "Once on Jan 15, 2024 at 12:00 AM"
 */
export function formatScheduleSummary(interval: string): string | null {
  const parsed = parseRepeatingInterval(interval)
  if (!parsed.start || !parsed.cadence) return null

  const cadence = durationToHumanReadableCadence(parsed.cadence)
  const startDate = formatDate(parsed.start)
  if (!startDate) return null

  const startTime = formatTime(parsed.start)

  if (cadence === 'Does not repeat') {
    if (interval.startsWith('R1')) {
      return startTime ? `Once on ${startDate} at ${startTime}` : `Once on ${startDate}`
    }
    return null
  }

  let summary = startTime ? `${cadence} at ${startTime}` : cadence
  summary += ` starting ${startDate}`

  if (parsed.end) {
    const endDate = formatDate(parsed.end)
    if (endDate) {
      summary += `, ending ${endDate}`
    }
  }

  return summary
}

function padTwoDigits(n: number): string {
  return String(n).padStart(2, '0')
}

function toDateTimeOffset(dateStr: string, timeStr: string, tzOffset: string): string {
  if (!dateStr) return ''
  return `${dateStr}T${timeStr}${tzOffset}`
}

/**
 * IANA timezone offset for a calendar date (`+00:00`, `-05:00`, or `Z`).
 * Used when composing ISO 8601 repeating intervals for scheduled triggers.
 */
export function getTimezoneOffset(timezone: string, referenceDate?: string): string {
  try {
    const refDate = referenceDate ? new Date(`${referenceDate}T12:00:00`) : new Date()
    const formatter = new Intl.DateTimeFormat('en-US', {
      timeZone: timezone,
      timeZoneName: 'longOffset',
    })
    const parts = formatter.formatToParts(refDate)
    const tzPart = parts.find((p) => p.type === 'timeZoneName')
    if (!tzPart) return 'Z'
    const offset = tzPart.value.replace('GMT', '')
    return offset || '+00:00'
  } catch {
    return 'Z'
  }
}

type BuildRepeatingIntervalInput = {
  startDate: string
  startTime: string
  endDate?: string
  frequency: ScheduleFrequency
  intervalCount: number
  timezone: string
  now?: Date
}

/**
 * Build an ISO 8601 repeating interval from visual schedule builder fields.
 * Empty start date/time fall back to `now` so a valid schedule exists before
 * the builder's first paint (save must send `interval` when type is interval).
 */
export function buildRepeatingInterval(input: BuildRepeatingIntervalInput): string {
  const now = input.now ?? new Date()
  const effectiveDate =
    input.startDate || `${now.getFullYear()}-${padTwoDigits(now.getMonth() + 1)}-${padTwoDigits(now.getDate())}`
  const effectiveTime = input.startDate
    ? input.startTime || '00:00'
    : `${padTwoDigits(now.getHours())}:${padTwoDigits(now.getMinutes())}`

  const tzOffset = getTimezoneOffset(input.timezone, effectiveDate)
  const start = toDateTimeOffset(effectiveDate, `${effectiveTime}:00`, tzOffset)
  if (!start) return ''

  const duration = frequencyAndIntervalToDuration(input.frequency, input.intervalCount)
  if (!duration) {
    return `R1/${start}/PT0S`
  }

  let interval = `R/${start}/${duration}`
  if (input.endDate) {
    const endTzOffset = getTimezoneOffset(input.timezone, input.endDate)
    interval += `/${toDateTimeOffset(input.endDate, '23:59:59', endTzOffset)}`
  }
  return interval
}

/** Default visual-builder interval: run once, starting now, in `timezone`. */
export function getDefaultRepeatingInterval(timezone: string, now?: Date): string {
  return buildRepeatingInterval({
    startDate: '',
    startTime: '',
    frequency: 'none',
    intervalCount: 1,
    timezone,
    now,
  })
}
