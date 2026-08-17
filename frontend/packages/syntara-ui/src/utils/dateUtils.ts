/**
 * Date utilities (formatting and helpers) using date-fns.
 * Single place for date-related display logic; use for UI only, not logic (per i18n guidelines).
 *
 * Scope: for any **rendered/read-only** timestamp,
 * use `DateCell` / `UserTimestamp` / `ExecutionTimestamp` (`components/table/`), which wrap
 * PatternFly's `Timestamp` component instead. The formatters below are kept because they're
 * needed in **plain-string** contexts where JSX can't be substituted (dropdown option labels,
 * `TextInput value=`, model fields, `Tooltip`/`Truncate` fallback text) — see each function's
 * doc comment for its specific plain-string call sites. `toDisplayDate` is the one exception:
 * it's a shared helper *for* the `Timestamp`-based components, converting an ISO string to the
 * `Date` object `Timestamp` requires.
 */

import { format, intervalToDuration, parseISO } from 'date-fns'

/**
 * Format a Date as YYYY-MM-DD for PatternFly DatePicker display.
 * `DatePicker`'s `dateFormat`/`dateParse` props require plain-string round-trip helpers, not
 * JSX — used by `ScheduleBuilderFields.tsx` and `CredentialExpirationField.tsx`.
 */
export function formatDateYMD(date: Date): string {
  return format(date, 'yyyy-MM-dd')
}

/**
 * Parse a YYYY-MM-DD string into a Date (local timezone).
 * Returns current date for unparseable input.
 */
export function parseDateYMD(val: string): Date {
  const d = new Date(`${val}T00:00:00`)
  return Number.isNaN(d.getTime()) ? new Date() : d
}

/**
 * Format an ISO date string for display (e.g. "Jan 15, 2024").
 * Returns empty string for invalid or empty input.
 *
 * Plain-string helper: composes the interval-summary sentence in `triggerFormatting.ts`
 * (e.g. "Starts Jan 15, 2024 at 2:30 PM") — not a JSX render path, so `Timestamp` doesn't apply.
 */
export function formatDate(isoString: string): string {
  if (!isoString) return ''
  try {
    const date = parseISO(isoString)
    if (Number.isNaN(date.getTime())) return ''
    return format(date, 'MMM d, yyyy')
  } catch {
    return ''
  }
}

/**
 * Format an ISO date string as 12-hour time (e.g. "2:30 PM").
 * Returns empty string for invalid or empty input.
 *
 * Plain-string helper: pairs with `formatDate` in `triggerFormatting.ts`'s interval summary.
 */
export function formatTime(isoString: string): string {
  if (!isoString) return ''
  try {
    const date = parseISO(isoString)
    if (Number.isNaN(date.getTime())) return ''
    return format(date, 'h:mm a')
  } catch {
    return ''
  }
}

/**
 * Parses an ISO date string into a valid Date, or undefined for null/invalid input.
 * Use with PatternFly's `Timestamp` component, which requires a `Date` (not a string).
 */
export function toDisplayDate(isoString?: string | null): Date | undefined {
  if (!isoString) return undefined
  const date = parseISO(isoString)
  return Number.isNaN(date.getTime()) ? undefined : date
}

/**
 * Format an ISO date string as medium date + time with seconds (locale-aware).
 * e.g. "May 27, 2026, 9:55:01 AM" (MMM DD, YYYY, H:MM:SS AM/PM per UX skill §3).
 * Returns '-' for invalid or empty input.
 *
 * Plain-string helper only — do NOT call this from new component render paths; use
 * `<DateCell dateString={...} />` (or `<UserTimestamp>`/`<ExecutionTimestamp>`) instead, which
 * render the same format via PatternFly's `Timestamp`. This function survives for the handful
 * of sites that consume its result as a plain string, not JSX: `executionFilters.ts`,
 * `useIsCurrentVersion.ts`, `useBuilderToolbarHandlers.ts`, `historyRowModel.ts`, and
 * `WorkflowHistoryCard.tsx`'s version-name fallback.
 */
export function formatDateTime(isoString?: string | null): string {
  if (!isoString) return '-'
  try {
    const date = parseISO(isoString)
    if (Number.isNaN(date.getTime())) return '-'
    return format(date, 'PPpp')
  } catch {
    return '-'
  }
}

/**
 * Format an elapsed duration in milliseconds as "Xh Ym Zs" (e.g. "1h 2m 3s").
 * Always includes seconds; includes minutes/hours when non-zero.
 * Durations >= 24h are shown as total hours (e.g. 25h 0m 0s).
 *
 * A duration, not a calendar timestamp — no PF `Timestamp` equivalent applies here.
 */
export function formatElapsedTime(elapsedMs: number): string {
  const totalMs = Math.max(0, Math.floor(elapsedMs))
  const duration = intervalToDuration({ start: new Date(0), end: new Date(totalMs) })
  const totalHours = (duration.days ?? 0) * 24 + (duration.hours ?? 0)
  const minutes = duration.minutes ?? 0
  const seconds = duration.seconds ?? 0

  const parts: string[] = []
  if (totalHours > 0) parts.push(`${totalHours}h`)
  if (minutes > 0 || totalHours > 0) parts.push(`${minutes}m`)
  parts.push(`${seconds}s`)
  return parts.join(' ')
}

/**
 * Check whether two ISO date strings fall on the same calendar day.
 * Used by `ExecutionTimestamp`/`ExecutionTimeRange` (`components/table/ExecutionTimestamp.tsx`)
 * to decide whether a range's start renders time-only or with the full date.
 */
export function isSameDay(a: string, b: string): boolean {
  const da = parseISO(a)
  const db = parseISO(b)
  return da.getFullYear() === db.getFullYear() && da.getMonth() === db.getMonth() && da.getDate() === db.getDate()
}

/**
 * Format a Date object to ISO 8601 string for API compatibility.
 * Use this for sending dates to the API in filter parameters — not a display formatter.
 *
 * @example
 * formatDateForApi(new Date('2024-01-01T12:00:00Z'))
 * // → '2024-01-01T12:00:00.000Z'
 */
export function formatDateForApi(date: Date): string {
  return date.toISOString()
}

/**
 * Format a UTC ISO expiration timestamp as a locale date string (e.g. "Jul 22, 2026").
 * Extracts year/month/day directly from the ISO string to avoid local-timezone shifts
 * (a midnight-UTC timestamp would display as the previous day in western timezones).
 *
 * Plain-string helper: feeds read-only `TextInput value=` fields (`CredentialsTab.tsx`,
 * `SecretRevealModal.tsx`, `Create*ServiceAccount*Modal.tsx`), which can't render JSX.
 */
export function formatExpirationDate(isoString?: string | null): string {
  if (!isoString) return '-'
  const datePart = isoString.split('T')[0]
  if (!datePart) return '-'
  const [y, m, d] = datePart.split('-').map(Number)
  if (!y || !m || !d) return '-'
  return format(new Date(y, m - 1, d), 'MMM d, yyyy')
}

/**
 * Extracts the calendar date (YYYY-MM-DD) from a UTC ISO string for chip display.
 * Avoids timezone shifts by using only the date portion.
 * Plain-string helper: feeds `ActiveFilterChips.tsx` chip label text.
 *
 * @example
 * formatDateChipValue('2026-04-26T00:00:00.000Z') // → '2026-04-26'
 * formatDateChipValue('2026-05-01T23:59:59.999Z') // → '2026-05-01'
 */
export function formatDateChipValue(isoValue: string): string {
  return isoValue.split('T')[0] ?? ''
}

/**
 * Format an ISO date string as a compact relative time (e.g. "5m ago", "2h ago").
 * Returns "Never" for null/undefined input, "Just now" for future dates.
 *
 * Intentionally manual rather than date-fns formatDistanceToNow, which
 * produces verbose strings ("about 5 minutes ago") unsuitable for compact UI.
 * No PF `Timestamp` equivalent for relative time — used as-is in `IntegrationModelsTab.tsx`
 * and `IntegrationResourcesTab.tsx` ("Last refreshed: 5m ago").
 */
const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })

export function formatTimeAgo(isoString: string | null | undefined): string {
  if (!isoString) return 'Never'
  const diff = Date.now() - new Date(isoString).getTime()
  if (diff < 0) return 'Just now'
  const seconds = Math.floor(diff / 1000)
  if (seconds < 60) return rtf.format(-seconds, 'second')
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return rtf.format(-minutes, 'minute')
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return rtf.format(-hours, 'hour')
  const days = Math.floor(hours / 24)
  return rtf.format(-days, 'day')
}
