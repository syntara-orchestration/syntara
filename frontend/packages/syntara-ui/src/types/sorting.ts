/**
 * Sort direction for ascending or descending order.
 *
 * @example
 * ```typescript
 * const direction: SortDirection = 'asc'
 * ```
 */
export type SortDirection = 'asc' | 'desc'

/**
 * Sort configuration used to build API query parameters and drive table UI state.
 *
 * @example
 * ```typescript
 * // Ascending by name → API param: sort=name
 * { field: 'name', direction: 'asc' }
 *
 * // Descending by created_at → API param: sort=-created_at
 * { field: 'created_at', direction: 'desc' }
 * ```
 */
export type SortConfig = {
  /** API field name to sort by (e.g., 'name', 'created_at') */
  field: string
  /** Sort direction — ascending or descending */
  direction: SortDirection
}

/**
 * UI column definition for table columns that may opt into sorting.
 *
 * @example
 * ```typescript
 * const columns: SortableColumn[] = [
 *   { field: 'name', label: 'Name', isSortable: true },
 *   { field: 'status', label: 'Status' }, // not sortable
 * ]
 * ```
 */
export type SortableColumn = {
  /** API field name used when sorting by this column */
  field: string
  /** Display label for the column header */
  label: string
  /** Whether the column supports sorting. Defaults to `false` when omitted. */
  isSortable?: boolean
}

/**
 * API query parameters for list endpoints that support sorting.
 *
 * Matches the Syntara API convention where `sort` is a single string:
 * - `field` for ascending
 * - `-field` for descending
 *
 * @example
 * ```typescript
 * const params: SortParams = { sort: 'name' }       // ascending
 * const params: SortParams = { sort: '-created_at' } // descending
 * const params: SortParams = {}                      // no sort applied
 * ```
 */
export type SortParams = {
  /** Sort value in API format (`field` or `-field`). Omit when unsorted. */
  sort?: string
}
