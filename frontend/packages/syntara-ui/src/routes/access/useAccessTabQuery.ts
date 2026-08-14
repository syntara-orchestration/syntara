import { useMemo } from 'react'

import { useCursorPagination } from '../../hooks/useCursorPagination'
import { useTableSort } from '../../hooks/useTableSort'
import type { FilterConfig, FilterFieldDefinition } from '../../types/filters'
import { buildFilterParams } from '../../utils/filterUtils'

import { buildSortParam } from './assignmentUtils'
import { buildProjectFilterDefs } from './scopeFilterUtils'
import { useProjectNameMap } from './useProjectNameMap'

type UseAccessTabQueryOptions = {
  baseFilterDefs: FilterFieldDefinition[]
  sortFields: Record<number, string>
  defaultSortField: string
  initialSortIndex?: number
  transformFilters: (filters: FilterConfig[]) => FilterConfig[]
}

export function useAccessTabQuery({
  baseFilterDefs,
  sortFields,
  defaultSortField,
  initialSortIndex,
  transformFilters,
}: UseAccessTabQueryOptions) {
  const {
    cursor,
    resetPagination,
    filters,
    hasActiveFilters,
    handleFilterChange,
    handleClearAllFilters,
    getFooterProps,
    perPage,
  } = useCursorPagination()

  const { activeSortIndex, sortDirection, getSortParams } = useTableSort({
    initialSortIndex,
    initialDirection: 'asc',
    onSortChange: resetPagination,
  })

  const { projectNameMap } = useProjectNameMap()

  const filterFieldDefinitions = useMemo(
    () => buildProjectFilterDefs([...baseFilterDefs], projectNameMap),
    [baseFilterDefs, projectNameMap]
  )

  const sort = buildSortParam(sortFields, activeSortIndex, defaultSortField, sortDirection)

  const queryParams = useMemo(() => {
    const params: Record<string, unknown> = { limit: perPage, include_total: true, sort }
    if (cursor) params.cursor = cursor
    Object.assign(params, buildFilterParams(transformFilters(filters)))
    return params
  }, [sort, perPage, cursor, transformFilters, filters])

  return {
    cursor,
    resetPagination,
    filters,
    hasActiveFilters,
    handleFilterChange,
    handleClearAllFilters,
    getFooterProps,
    perPage,
    getSortParams,
    projectNameMap,
    filterFieldDefinitions,
    queryParams,
  }
}
