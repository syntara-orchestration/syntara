import type { BaseCellProps } from '@patternfly/react-table'

type ColumnWidth = NonNullable<BaseCellProps['width']>

/**
 * Standard column width constants for list tables.
 *
 * Use these on `<Th width={…}>` for **predictable** columns only — columns whose
 * content length is known and bounded (dates, badges, toggles, counts, short labels).
 * Leave **dynamic** columns (names, descriptions, URLs) without a width so they
 * absorb the remaining space.
 *
 * PatternFly `Th width` accepts: 10 | 15 | 20 | 25 | 30 | 35 | 40 | 45 | 50 | 60 | 70 | 80 | 90 | 100
 */
export const columnWidths = {
  actions: 10 as ColumnWidth,
  authSource: 15 as ColumnWidth,
  count: 10 as ColumnWidth,
  dateTime: 20 as ColumnWidth,
  dateTimeCompact: 15 as ColumnWidth,
  enumLabel: 15 as ColumnWidth,
  expand: 10 as ColumnWidth,
  policies: 15 as ColumnWidth,
  select: 10 as ColumnWidth,
  status: 10 as ColumnWidth,
  switch: 10 as ColumnWidth,
  type: 15 as ColumnWidth,
  version: 10 as ColumnWidth,
} as const
