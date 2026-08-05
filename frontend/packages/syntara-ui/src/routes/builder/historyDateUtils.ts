import { format, isToday, isYesterday, parseISO } from 'date-fns'

function safeParseDate(isoString: string): Date | null {
  if (!isoString) return null
  try {
    const date = parseISO(isoString)
    return Number.isNaN(date.getTime()) ? null : date
  } catch {
    return null
  }
}

/**
 * Format timestamp for run history list items.
 * Returns format like "Jul 9, 2026, 9:43 AM" (no seconds per UX mockup).
 *
 * Plain-string helper only — for rendered/read-only
 * timestamps use `<ExecutionTimestamp timeFormat="short" />` (`components/table/`) instead, which
 * renders this same "short" format via PatternFly's `Timestamp`. This function survives for
 * plain-string contexts where JSX can't be substituted: the version-name-or-date fallback label
 * in `VersionConflictDialog.tsx`, the confirm-dialog title in `useBuilderVersionHistory.ts`, the
 * embedded-substring replace in `VersionInfoCard.tsx`'s `formatSourceInfo`, and the title-fallback
 * string in `VersionInfoCard.tsx` (its truncation logic needs a plain string).
 */
export function formatHistoryDateTime(isoString: string): string {
  const date = safeParseDate(isoString)
  if (!date) return '-'
  // PPp format: "MMM d, yyyy, h:mm a" (no seconds)
  return format(date, 'PPp')
}

export function getDateGroupLabel(isoString: string): string {
  const date = safeParseDate(isoString)
  if (!date) return 'Unknown'
  if (isToday(date)) return 'Today'
  if (isYesterday(date)) return 'Yesterday'
  return format(date, 'MMMM d, yyyy')
}
