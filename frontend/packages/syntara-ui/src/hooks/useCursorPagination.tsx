import type { ThProps } from '@patternfly/react-table'
import { useCallback, useEffect, useMemo, useState } from 'react'

import type { PaginationFooterProps } from '../components/table/PaginationFooter'
import type { FilterConfig } from '../types/filters'
import type { SortableColumn, SortConfig } from '../types/sorting'
import { buildFilterParams } from '../utils/filterUtils'

import { createFilterChangeHandler } from './useFilterChangeHandler'
import { useFilterState } from './useFilterState'
import { useSortableTableControls } from './useSortableTable'
import { useSortState } from './useSortState'

type PaginatedResponse = {
  resources?: unknown[]
  prev?: string | null
  next?: string | null
  total?: number | null
}

type UseCursorPaginationOptions = {
  /** Default page size (defaults to 20) */
  limit?: number
  /** Default filters from URL or other sources */
  defaultFilters?: FilterConfig[]
  /** Optional transform for filter values before applying (e.g., string → boolean) */
  transformFilters?: (filters: FilterConfig[]) => FilterConfig[]
  /**
   * Extra query params merged into every request (e.g., provider_id).
   * Do not pass `sort` here — use `defaultSort` / URL sort instead. When owned
   * `sortParam` is set, it overwrites `extraParams.sort`.
   */
  extraParams?: Record<string, unknown>
  /**
   * Default sort when the URL has no valid `sort` param.
   * Sort is URL-synced via {@link useSortState} and merged into `queryParams`.
   */
  defaultSort?: SortConfig
  /**
   * Sortable column definitions for PatternFly table headers.
   * When provided (or omitted as `[]`), exposes `getSortParams` / `handleSort`.
   */
  columns?: SortableColumn[]
}

export type UseCursorPaginationResult = {
  /** Current pagination cursor */
  cursor: string | null
  /** Set cursor directly */
  setCursor: (cursor: string | null) => void
  /** Reset both cursor and page to initial state */
  resetPagination: () => void
  /** Current active filters */
  filters: FilterConfig[]
  /** Whether any filters are active */
  hasActiveFilters: boolean
  /** Built query params ready to pass to useQuery (includes `sort` when active) */
  queryParams: Record<string, unknown>
  /** Handler for FilterBar onFilterChange */
  handleFilterChange: (newFilters: FilterConfig[]) => void
  /** Handler for "Clear all filters" button */
  handleClearAllFilters: () => void
  /** Current page number (1-based) */
  page: number
  /** Current items per page */
  perPage: number
  /** Handler for changing items per page */
  handlePerPageChange: (perPage: number) => void
  /** Build footer props for SynScrollableTableContainer from a query response */
  getFooterProps: (data: PaginatedResponse | undefined) => PaginationFooterProps
  /** Current sort configuration (URL-synced) */
  sort: SortConfig | null
  /** Syntara API `sort` query param (`field` / `-field`), or `undefined` when unsorted */
  sortParam: string | undefined
  /** Set sort and reset pagination to page 1 */
  setSort: (sort: SortConfig) => void
  /** Clear sort from the URL and reset pagination */
  clearSort: () => void
  /** Toggle sort for a field; resets pagination */
  toggleSort: (field: string) => void
  /**
   * PatternFly `<Th sort={...}>` props for a column field.
   * Useful when `columns` is passed; returns `undefined` for non-sortable fields.
   */
  getSortParams: (columnField: string) => ThProps['sort']
  /**
   * Toggle sort for a column field (same field flips; different field → asc).
   * No-op when the field is missing or not sortable.
   */
  handleSort: (columnField: string) => void
}

/**
 * Encapsulates the cursor-based pagination pattern used across all list views.
 *
 * Handles:
 * - Cursor state management
 * - Filter state (via useFilterState) with optional transform
 * - Sort state (via useSortState) merged into query params
 * - Optional PatternFly sortable headers via `columns`
 * - Query params building (filters + sort + cursor + limit + extras)
 * - Cursor reset when data is empty and no filters active
 * - handleClearAllFilters (reset cursor + clear filters)
 * - Footer props for SynScrollableTableContainer
 */
export function useCursorPagination(options: UseCursorPaginationOptions = {}): UseCursorPaginationResult {
  const { limit = 20, defaultFilters, transformFilters, extraParams, defaultSort, columns = [] } = options

  const [cursor, setCursor] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(limit)
  const { filters, clearAllFilters, setAllFilters } = useFilterState(defaultFilters)
  const {
    sort,
    setSort: setSortState,
    clearSort: clearSortState,
    toggleSort: toggleSortState,
  } = useSortState(defaultSort)

  const hasActiveFilters = filters.length > 0

  const resetPagination = useCallback(() => {
    setCursor(null)
    setPage(1)
  }, [])

  const setSort = useCallback(
    (newSort: SortConfig) => {
      setSortState(newSort)
      resetPagination()
    },
    [setSortState, resetPagination]
  )

  const clearSort = useCallback(() => {
    clearSortState()
    resetPagination()
  }, [clearSortState, resetPagination])

  const toggleSort = useCallback(
    (field: string) => {
      toggleSortState(field)
      resetPagination()
    },
    [toggleSortState, resetPagination]
  )

  const { sortParam, getSortParams, handleSort } = useSortableTableControls(columns, {
    sort,
    setSort,
    toggleSort,
  })

  const handleFilterChange = useMemo(
    () => createFilterChangeHandler(cursor, resetPagination, clearAllFilters, setAllFilters, transformFilters),
    [cursor, resetPagination, clearAllFilters, setAllFilters, transformFilters]
  )

  const handleClearAllFilters = useCallback(() => {
    clearAllFilters()
    resetPagination()
  }, [clearAllFilters, resetPagination])

  const handlePerPageChange = useCallback(
    (newPerPage: number) => {
      setPerPage(newPerPage)
      resetPagination()
    },
    [resetPagination]
  )

  // Reset pagination when extraParams or sortParam change (e.g., project selection,
  // or browser back/forward updating `?sort=`). Uses the React "store previous value"
  // pattern to detect change during render so queryParams excludes the stale cursor
  // in the same render cycle.
  //
  // Timing: setCursor(null) clears the cursor state, but React batches state updates
  // so `cursor` still holds its previous value during this render. The
  // `extraParamsChanged` / `sortParamChanged` guards below prevent the stale cursor
  // from leaking into queryParams for this one render cycle. On the next render both
  // `cursor` and the previous-value trackers are up to date, so the guards become
  // false and normal cursor inclusion resumes.
  const extraParamsKey = JSON.stringify(extraParams)
  const [prevExtraParamsKey, setPrevExtraParamsKey] = useState(extraParamsKey)
  const extraParamsChanged = prevExtraParamsKey !== extraParamsKey
  if (extraParamsChanged) {
    setPrevExtraParamsKey(extraParamsKey)
    setCursor(null)
    setPage(1)
  }

  const [prevSortParam, setPrevSortParam] = useState(sortParam)
  const sortParamChanged = prevSortParam !== sortParam
  if (sortParamChanged) {
    setPrevSortParam(sortParam)
    setCursor(null)
    setPage(1)
  }

  const queryParams = useMemo(() => {
    const params: Record<string, unknown> = {
      limit: perPage,
      include_total: true,
      ...extraParams,
    }

    const filterParams = buildFilterParams(filters)
    Object.assign(params, filterParams)

    if (sortParam !== undefined) {
      params.sort = sortParam
    }

    if (cursor && !extraParamsChanged && !sortParamChanged) {
      params.cursor = cursor
    }

    return params
  }, [filters, cursor, perPage, extraParams, extraParamsChanged, sortParam, sortParamChanged])

  const getFooterProps = useCallback(
    (data: PaginatedResponse | undefined): PaginationFooterProps => ({
      page,
      perPage,
      total: data?.total ?? null,
      hasNext: !!data?.next,
      onPrev: () => {
        setCursor(data?.prev ?? null)
        setPage((p) => Math.max(1, p - 1))
      },
      onNext: () => {
        setCursor(data?.next ?? null)
        setPage((p) => p + 1)
      },
      onPerPageChange: handlePerPageChange,
    }),
    [page, perPage, handlePerPageChange]
  )

  return {
    cursor,
    setCursor,
    resetPagination,
    filters,
    hasActiveFilters,
    queryParams,
    handleFilterChange,
    handleClearAllFilters,
    page,
    perPage,
    handlePerPageChange,
    getFooterProps,
    sort,
    sortParam,
    setSort,
    clearSort,
    toggleSort,
    getSortParams,
    handleSort,
  }
}

/**
 * Auto-resets pagination when:
 * - There are no items to display
 * - No active filters (i.e., it's not a "no results" from filtering)
 * - A cursor is currently set
 * - The query is not fetching (to avoid resetting mid-pagination)
 *
 * Use this in list views after getting query results.
 */
export function useCursorReset(
  itemCount: number,
  hasActiveFilters: boolean,
  cursor: string | null,
  isFetching: boolean,
  resetPagination: () => void
): void {
  useEffect(() => {
    if (itemCount === 0 && !hasActiveFilters && cursor && !isFetching) {
      resetPagination()
    }
  }, [itemCount, hasActiveFilters, cursor, isFetching, resetPagination])
}
