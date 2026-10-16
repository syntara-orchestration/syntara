import type { FilterConfig, FilterOperator } from '../types/filters'
import { isValidFilterOperator } from '../types/filters'

import { formatDateForApi } from './dateUtils'

/**
 * Converts filter configurations to API query parameters
 *
 * @param filters - Array of filter configurations
 * @returns Object with API query parameter keys and values
 *
 * @example
 * ```typescript
 * // Single filter with operator
 * buildFilterParams([
 *   { key: 'name', operator: 'contains', value: 'deploy' }
 * ])
 * // → { 'name[contains]': 'deploy' }
 *
 * // Multiple values with 'in' operator
 * buildFilterParams([
 *   { key: 'status', operator: 'in', value: ['running', 'failed'] }
 * ])
 * // → { 'status[in]': 'running,failed' }
 *
 * // Date filter
 * buildFilterParams([
 *   { key: 'created_at', operator: 'gte', value: new Date('2024-01-01') }
 * ])
 * // → { 'created_at[gte]': '2024-01-01T00:00:00.000Z' }
 *
 * // Filter without operator (defaults to 'eq')
 * buildFilterParams([
 *   { key: 'is_enabled', value: true }
 * ])
 * // → { 'is_enabled': true }
 * ```
 */
export function buildFilterParams(filters: FilterConfig[]): Record<string, string | number | boolean> {
  const params: Record<string, string | number | boolean> = {}

  for (const filter of filters) {
    // Skip filters with null/undefined values
    if (filter.value === null || filter.value === undefined) {
      continue
    }

    // Skip empty arrays
    if (Array.isArray(filter.value) && filter.value.length === 0) {
      continue
    }

    // Skip empty strings
    if (typeof filter.value === 'string' && filter.value.trim() === '') {
      continue
    }

    // Build the parameter key
    const operator = filter.operator ?? 'eq'
    const paramKey = buildParamKey(filter.key, operator)

    // Build the parameter value
    const paramValue = buildParamValue(filter.value)

    params[paramKey] = paramValue
  }

  return params
}

/**
 * Builds API query parameter key with operator syntax
 *
 * @param key - Filter field key
 * @param operator - Filter operator
 * @returns Parameter key with operator notation
 *
 * @example
 * ```typescript
 * buildParamKey('name', 'contains') // → 'name[contains]'
 * buildParamKey('status', 'eq')     // → 'status'
 * ```
 */
function buildParamKey(key: string, operator: FilterOperator): string {
  // For 'eq' operator, use the key directly without brackets
  if (operator === 'eq') {
    return key
  }

  // For other operators, use bracket notation
  return `${key}[${operator}]`
}

/**
 * Builds API query parameter value from filter value
 *
 * @param value - Filter value
 * @returns Formatted parameter value
 *
 * @example
 * ```typescript
 * buildParamValue('deploy')                  // → 'deploy'
 * buildParamValue(['running', 'failed'])     // → 'running,failed'
 * buildParamValue(new Date('2024-01-01'))    // → '2024-01-01T00:00:00.000Z'
 * buildParamValue(true)                      // → true
 * ```
 */
function buildParamValue(value: FilterConfig['value']): string | number | boolean {
  // Handle array values (for 'in' operator) - join with comma
  if (Array.isArray(value)) {
    return value.join(',')
  }

  // Handle Date values - format to ISO 8601
  if (value instanceof Date) {
    return formatDateForApi(value)
  }

  // Return primitive values as-is (string, boolean, number)
  return value
}

/**
 * Builds label filter params from key-value pairs
 *
 * Uses the API's label filter syntax: labels[key]=value
 * Multiple labels are combined with AND logic by the API.
 *
 * @param labels - Label key-value pairs
 * @returns Object with label filter parameters
 *
 * @example
 * ```typescript
 * buildLabelParams({
 *   environment: 'production',
 *   team: 'platform'
 * })
 * // → {
 * //   'labels[environment]': 'production',
 * //   'labels[team]': 'platform'
 * // }
 * ```
 */
export function buildLabelParams(labels: Record<string, string>): Record<string, string> {
  const params: Record<string, string> = {}

  for (const [key, value] of Object.entries(labels)) {
    // Skip empty values
    if (!value || value.trim() === '') {
      continue
    }

    // Build label parameter key
    params[`labels[${key}]`] = value
  }

  return params
}

/**
 * Parses URL query parameters into FilterConfig array
 *
 * @param searchParams - URLSearchParams object
 * @returns Array of filter configurations
 *
 * @example
 * ```typescript
 * const params = new URLSearchParams('name[contains]=deploy&status[in]=running,failed')
 * parseFiltersFromUrl(params)
 * // → [
 * //   { key: 'name', operator: 'contains', value: 'deploy' },
 * //   { key: 'status', operator: 'in', value: ['running', 'failed'] }
 * // ]
 * ```
 */
export function parseFiltersFromUrl(searchParams: URLSearchParams): FilterConfig[] {
  const filters: FilterConfig[] = []

  for (const [key, value] of searchParams.entries()) {
    const filter = parseFilterParam(key, value)
    if (filter) {
      filters.push(filter)
    }
  }

  return filters
}

/**
 * Parses a single URL query parameter into a FilterConfig
 *
 * @param key - Parameter key (may include operator in brackets)
 * @param value - Parameter value
 * @returns FilterConfig or null if invalid
 *
 * @example
 * ```typescript
 * parseFilterParam('name[contains]', 'deploy')
 * // → { key: 'name', operator: 'contains', value: 'deploy' }
 *
 * parseFilterParam('status[in]', 'running,failed')
 * // → { key: 'status', operator: 'in', value: ['running', 'failed'] }
 *
 * parseFilterParam('is_enabled', 'true')
 * // → { key: 'is_enabled', operator: 'eq', value: 'true' }
 *
 * parseFilterParam('name[invalid]', 'test')
 * // → null (invalid operator)
 * ```
 */
/** Pagination / sort / page chrome — never treat these as filter fields. */
const RESERVED_URL_PARAMS = new Set([
  'sort',
  'page',
  'perPage',
  'cursor',
  'history',
  'version',
  'form_prompt',
  'approval',
])

function isReservedUrlParam(key: string): boolean {
  // Namespaced sorts (e.g. `activity_sort` on execution detail) share the URL with list filters.
  return RESERVED_URL_PARAMS.has(key) || key.endsWith('_sort')
}

function parseFilterParam(key: string, value: string): FilterConfig | null {
  if (isReservedUrlParam(key)) return null

  // Match pattern: key[operator] — e.g. "name[contains]"
  // Negated character classes ([^[]+, [^\]]+) prevent backtracking; avoids ReDoS on malformed input like "aaa[aaa"
  // regex.exec(string) preferred over string.match(regex) for performance (SonarQube S5852)
  const match = /^([^[]+)\[([^\]]+)\]$/.exec(key)

  if (match) {
    // Has operator in brackets
    const [, fieldKey, operatorString] = match

    // Validate operator before casting
    if (!isValidFilterOperator(operatorString)) {
      // Invalid operator - skip this filter
      return null
    }

    // Parse value based on operator (only after validation)
    const parsedValue = operatorString === 'in' ? value.split(',') : value

    return {
      key: fieldKey,
      operator: operatorString,
      value: parsedValue,
    }
  }

  // No operator - default to 'eq'
  return {
    key,
    operator: 'eq',
    value,
  }
}
