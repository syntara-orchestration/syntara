import type { SortConfig, SortDirection } from '../types/sorting'

/**
 * Valid sort field pattern: starts with a letter or underscore, then
 * letters, digits, or underscores. Rejects empty strings, whitespace,
 * and characters that are not valid API field names.
 */
const VALID_SORT_FIELD = /^[a-zA-Z_]\w*$/

/**
 * Returns true when `field` is a non-empty, well-formed API sort field name.
 */
function isValidSortField(field: string): boolean {
  return VALID_SORT_FIELD.test(field)
}

/**
 * Converts a sort configuration to the Nexus API `sort` query parameter value.
 *
 * API format:
 * - ascending: `field`
 * - descending: `-field`
 *
 * @param sort - Sort configuration, or null when no sort is applied
 * @returns API sort string, or null when no valid sort is provided
 *
 * @example
 * ```typescript
 * buildSortParam({ field: 'name', direction: 'asc' })
 * // → 'name'
 *
 * buildSortParam({ field: 'created_at', direction: 'desc' })
 * // → '-created_at'
 *
 * buildSortParam(null)
 * // → null
 * ```
 */
export function buildSortParam(sort: SortConfig | null): string | null {
  if (sort == null) {
    return null
  }

  const field = sort.field.trim()
  if (!isValidSortField(field)) {
    return null
  }

  return sort.direction === 'desc' ? `-${field}` : field
}

/**
 * Parses a Nexus API `sort` query parameter value into a SortConfig.
 *
 * Handles a leading `-` as descending; otherwise ascending.
 *
 * @param sortParam - API sort string (`field` or `-field`), or null
 * @returns Parsed SortConfig, or null when the value is missing or invalid
 *
 * @example
 * ```typescript
 * parseSortParam('name')
 * // → { field: 'name', direction: 'asc' }
 *
 * parseSortParam('-created_at')
 * // → { field: 'created_at', direction: 'desc' }
 *
 * parseSortParam(null)
 * // → null
 *
 * parseSortParam('-')
 * // → null (empty field after prefix)
 * ```
 */
export function parseSortParam(sortParam: string | null): SortConfig | null {
  if (sortParam == null) {
    return null
  }

  const trimmed = sortParam.trim()
  if (trimmed === '') {
    return null
  }

  const isDescending = trimmed.startsWith('-')
  const field = (isDescending ? trimmed.slice(1) : trimmed).trim()

  if (!isValidSortField(field)) {
    return null
  }

  return {
    field,
    direction: isDescending ? 'desc' : 'asc',
  }
}

/**
 * Toggles sort direction between ascending and descending.
 *
 * @param current - Current sort direction
 * @returns The opposite direction
 *
 * @example
 * ```typescript
 * toggleSortDirection('asc')  // → 'desc'
 * toggleSortDirection('desc') // → 'asc'
 * ```
 */
export function toggleSortDirection(current: SortDirection): SortDirection {
  return current === 'asc' ? 'desc' : 'asc'
}
