import { Timestamp } from '@patternfly/react-core'

import { isSameDay, toDisplayDate } from '../../utils/dateUtils'

type ExecutionTimestampProps = Readonly<{
  dateString?: string | null
  /** Render time only (no date portion) — used for range starts that share a day with the end. */
  timeOnly?: boolean
  /** Time precision; defaults to "medium" (seconds included). Use "short" to omit seconds
   * (e.g. run history lists, per the "Jul 9, 2026, 9:43 AM" UX mockup). */
  timeFormat?: 'medium' | 'short'
}>

/**
 * Renders a single execution-scoped timestamp via PatternFly's Timestamp. Renders nothing
 * for null/invalid input — callers that need a placeholder (e.g. a dash) should handle
 * that themselves around this component.
 */
export function ExecutionTimestamp({ dateString, timeOnly = false, timeFormat = 'medium' }: ExecutionTimestampProps) {
  const date = toDisplayDate(dateString)
  if (!date) return null
  return timeOnly ? (
    <Timestamp date={date} timeFormat={timeFormat} />
  ) : (
    <Timestamp date={date} dateFormat="medium" timeFormat={timeFormat} />
  )
}

type ExecutionTimeRangeProps = Readonly<{
  startedAt?: string | null
  completedAt?: string | null
}>

/**
 * Renders a start-end execution time range, collapsing the start to time-only when
 * both timestamps fall on the same calendar day
 * (e.g. "10:00:00 AM - 10:01:30 AM, Apr 16, 2026").
 * Renders nothing when there's no start time.
 */
export function ExecutionTimeRange({ startedAt, completedAt }: ExecutionTimeRangeProps) {
  if (!startedAt) return null
  if (!completedAt) return <ExecutionTimestamp dateString={startedAt} />

  const sameDay = isSameDay(startedAt, completedAt)
  return (
    <>
      <ExecutionTimestamp dateString={startedAt} timeOnly={sameDay} />
      {' - '}
      <ExecutionTimestamp dateString={completedAt} />
    </>
  )
}
