import type { FilterConfig } from '../types/filters'

/**
 * Creates a filter change handler that resets pagination cursor and manages filter state
 *
 * This handler follows the standard pattern for list views with server-side filtering:
 * 1. Reset pagination cursor to first page when filters change
 * 2. Optionally transform filter values before applying
 * 3. Apply filters atomically to URL state
 *
 * ARCHITECTURE NOTE: Cursor Storage
 * - Cursor is stored in component state (via reducer/useState), NOT in URL
 * - resetCursor() updates component state only (e.g., dispatch({type: 'SET_CURSOR', payload: null}))
 * - setAllFilters() preserves non-filter URL params, but cursor wouldn't be there anyway
 * - This keeps URLs clean and bookmarkable while maintaining pagination state
 *
 * @param options.cursor - Current pagination cursor value from component state
 * @param options.resetCursor - Function to reset the pagination cursor to null
 * @param options.clearAllFilters - Function to clear all active filters
 * @param options.setAllFilters - Function to set all filters atomically
 * @param options.transformFilters - Optional function to transform filters before applying (e.g., convert string to boolean)
 * @returns Filter change handler function
 *
 * @example
 * // Basic usage (Integrations, Integration Tools)
 * const handleFilterChange = createFilterChangeHandler({
 *   cursor,
 *   resetCursor: () => setCursor(null),
 *   clearAllFilters,
 *   setAllFilters,
 * })
 *
 * @example
 * // With value transformation (Workflows - convert is_enabled string to boolean)
 * const handleFilterChange = createFilterChangeHandler({
 *   cursor,
 *   resetCursor: () => dispatch({ type: 'SET_CURSOR', payload: null }),
 *   clearAllFilters,
 *   setAllFilters,
 *   transformFilters: (filters) => filters.map((filter) => {
 *     if (filter.key === 'is_enabled' && typeof filter.value === 'string') {
 *       return { ...filter, value: filter.value === 'true' }
 *     }
 *     return filter
 *   }),
 * })
 */
export const createFilterChangeHandler = ({
  cursor,
  resetCursor,
  clearAllFilters,
  setAllFilters,
  transformFilters,
}: {
  cursor: string | null
  resetCursor: () => void
  clearAllFilters: () => void
  setAllFilters: (filters: FilterConfig[]) => void
  transformFilters?: (filters: FilterConfig[]) => FilterConfig[]
}) => {
  return (newFilters: FilterConfig[]) => {
    // Reset to first page when filters change
    if (cursor) {
      resetCursor()
    }

    // If clearing all filters (empty array), use clearAllFilters
    if (newFilters.length === 0) {
      clearAllFilters()
      return
    }

    // Apply optional transformations (e.g., string to boolean conversion)
    const finalFilters = transformFilters ? transformFilters(newFilters) : newFilters

    // Apply all filters atomically with setAllFilters
    setAllFilters(finalFilters)
  }
}
