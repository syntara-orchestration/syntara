import type { ThProps } from '@patternfly/react-table'
import { useState, useCallback, useMemo } from 'react'

import type { SortDirection } from '../types/sorting'

export type { SortDirection }

export type UseTableSortOptions = {
  initialSortIndex?: number
  initialDirection?: SortDirection
  /** Called whenever sort column or direction changes (e.g. to reset pagination) */
  onSortChange?: () => void
}

export function useTableSort(options: UseTableSortOptions = {}) {
  const { initialSortIndex = 0, initialDirection = 'asc', onSortChange } = options

  const [activeSortIndex, setActiveSortIndex] = useState(initialSortIndex)
  const [sortDirection, setSortDirection] = useState<SortDirection>(initialDirection)

  const getSortParams = useCallback(
    (columnIndex: number): ThProps['sort'] => ({
      sortBy: {
        index: activeSortIndex,
        direction: sortDirection,
        defaultDirection: 'asc',
      },
      onSort: (_event, _index, direction) => {
        setActiveSortIndex(columnIndex)
        setSortDirection(direction)
        onSortChange?.()
      },
      columnIndex,
    }),
    [activeSortIndex, sortDirection, onSortChange]
  )

  const sortData = useCallback(
    <T>(data: T[], getValue: (item: T) => string | number | Date | null | undefined): T[] => {
      const sorted = [...data]
      sorted.sort((a, b) => {
        const aValue = getValue(a)
        const bValue = getValue(b)

        if (aValue == null && bValue == null) return 0
        if (aValue == null) return 1
        if (bValue == null) return -1

        let comparison: number
        if (aValue instanceof Date && bValue instanceof Date) {
          comparison = aValue.getTime() - bValue.getTime()
        } else if (typeof aValue === 'string' && typeof bValue === 'string') {
          comparison = aValue.localeCompare(bValue)
        } else {
          comparison = Number(aValue) - Number(bValue)
        }

        return sortDirection === 'asc' ? comparison : -comparison
      })
      return sorted
    },
    [sortDirection]
  )

  return useMemo(
    () => ({ activeSortIndex, sortDirection, getSortParams, sortData }),
    [activeSortIndex, sortDirection, getSortParams, sortData]
  )
}
