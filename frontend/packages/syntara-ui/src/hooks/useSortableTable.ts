import type { ThProps } from '@patternfly/react-table'
import { useCallback, useMemo } from 'react'

import type { SortableColumn, SortConfig, SortDirection } from '../types/sorting'
import { buildSortParam } from '../utils/sortUtils'

import type { UseSortStateOptions, UseSortStateResult } from './useSortState'
import { useSortState } from './useSortState'

/**
 * Result from {@link useSortableTable}.
 */
export type UseSortableTableResult = {
  /**
   * Current sort configuration for API queries.
   * Synced to the URL via {@link useSortState}.
   */
  sort: SortConfig | null
  /**
   * Nexus API `sort` query parameter (`field` / `-field`) for
   * {@link useFilteredQuery} and other list queries. `undefined` when unsorted.
   */
  sortParam: string | undefined
  /**
   * PatternFly `<Th sort={...}>` props for a column field.
   * Returns `undefined` when the field is missing or not sortable.
   */
  getSortParams: (columnField: string) => ThProps['sort']
  /**
   * Toggle sort for a column field.
   * Same field flips direction; a different field resets to ascending.
   * No-op when the field is missing or not sortable.
   */
  handleSort: (columnField: string) => void
}

export type UseSortableTableControlsResult = Pick<UseSortableTableResult, 'sortParam' | 'getSortParams' | 'handleSort'>

type SortStateControls = Pick<UseSortStateResult, 'sort' | 'setSort' | 'toggleSort'>

/**
 * PatternFly table sort helpers bound to an existing sort state.
 *
 * Prefer {@link useCursorPagination} with `columns` / `defaultSort` on list pages.
 * Use this when you already own {@link useSortState} (or wrapped setters) and only
 * need header wiring.
 */
export function useSortableTableControls(
  columns: SortableColumn[],
  sortState: SortStateControls
): UseSortableTableControlsResult {
  const { sort, setSort, toggleSort } = sortState

  const { columnIndexByField, sortableFields } = useMemo(() => {
    const indexByField = new Map<string, number>()
    const sortable = new Set<string>()

    for (const [index, column] of columns.entries()) {
      indexByField.set(column.field, index)
      if (column.isSortable === true) {
        sortable.add(column.field)
      }
    }

    return { columnIndexByField: indexByField, sortableFields: sortable }
  }, [columns])

  const activeSortIndex = useMemo(() => {
    if (sort === null) {
      return undefined
    }
    return columnIndexByField.get(sort.field)
  }, [sort, columnIndexByField])

  const sortParam = useMemo(() => buildSortParam(sort) ?? undefined, [sort])

  const handleSort = useCallback(
    (columnField: string) => {
      if (!sortableFields.has(columnField)) {
        return
      }
      toggleSort(columnField)
    },
    [sortableFields, toggleSort]
  )

  const getSortParams = useCallback(
    (columnField: string): ThProps['sort'] => {
      const columnIndex = columnIndexByField.get(columnField)
      if (columnIndex === undefined || !sortableFields.has(columnField)) {
        return undefined
      }

      return {
        sortBy: {
          index: activeSortIndex,
          direction: sort?.direction ?? 'asc',
          defaultDirection: 'asc',
        },
        onSort: (_event, _index, direction) => {
          setSort({ field: columnField, direction: direction as SortDirection })
        },
        columnIndex,
      }
    },
    [activeSortIndex, columnIndexByField, setSort, sort?.direction, sortableFields]
  )

  return {
    sortParam,
    getSortParams,
    handleSort,
  }
}

/**
 * PatternFly table header sorting backed by URL-persisted {@link useSortState}.
 *
 * **When to use this hook**
 * - Non-paginated tables
 * - Standalone sort without cursor / filter integration (e.g. with {@link useFilteredQuery})
 * - Building custom list wiring that does not use {@link useCursorPagination}
 *
 * **When to prefer {@link useCursorPagination}**
 * - Standard paginated list pages — pass `defaultSort` / `columns` so filters,
 *   cursor, and sort share one hook and `queryParams` already includes `sort`
 *
 * Maps `SortableColumn[]` field names to PatternFly column indexes and exposes
 * `getSortParams` / `handleSort` for sortable headers. Pass `sortParam` into
 * {@link useFilteredQuery} (or any list query) for API-based sorting.
 *
 * @param columns - Table column definitions (`field`, `label`, optional `isSortable`)
 * @param defaultSort - Optional default sort when the URL has no valid sort param
 * @param options - Optional `paramName` when multiple sorts share a route
 * @returns Sort state, PatternFly sort helpers, and API `sortParam`
 *
 * @example
 * ```typescript
 * // Standalone / non-paginated table (useCursorPagination is the list-page path)
 * const columns: SortableColumn[] = [
 *   { field: 'name', label: 'Name', isSortable: true },
 *   { field: 'created_at', label: 'Created', isSortable: true },
 *   { field: 'status', label: 'Status' },
 * ]
 *
 * function FilteredWorkflowsPanel() {
 *   const { sortParam, getSortParams } = useSortableTable(columns, {
 *     field: 'name',
 *     direction: 'asc',
 *   })
 *
 *   const { data, queryState } = useFilteredQuery({
 *     client: workflowClient,
 *     method: 'get',
 *     path: '/workflows',
 *     sort: sortParam,
 *     filters,
 *   })
 *
 *   return (
 *     <Table>
 *       <Thead>
 *         <Tr>
 *           <Th sort={getSortParams('name')}>Name</Th>
 *           <Th sort={getSortParams('created_at')}>Created</Th>
 *           <Th>Status</Th>
 *         </Tr>
 *       </Thead>
 *     </Table>
 *   )
 * }
 * ```
 */
export function useSortableTable(
  columns: SortableColumn[],
  defaultSort?: SortConfig,
  options?: UseSortStateOptions
): UseSortableTableResult {
  const sortState = useSortState(defaultSort, options)
  const controls = useSortableTableControls(columns, sortState)

  return {
    sort: sortState.sort,
    ...controls,
  }
}
