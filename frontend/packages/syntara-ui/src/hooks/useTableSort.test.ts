import type { SortByDirection } from '@patternfly/react-table'
import { renderHook, act } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useTableSort } from './useTableSort'

type TestItem = {
  id: number
  name: string
  value: number
  date: Date | null
}

describe('useTableSort', () => {
  const testData: TestItem[] = [
    { id: 1, name: 'Charlie', value: 30, date: new Date('2024-03-01') },
    { id: 2, name: 'Alice', value: 10, date: new Date('2024-01-01') },
    { id: 3, name: 'Bob', value: 20, date: new Date('2024-02-01') },
    { id: 4, name: 'David', value: 40, date: null },
  ]

  describe('initialization', () => {
    it('uses default options when none provided', () => {
      const { result } = renderHook(() => useTableSort())

      expect(result.current.activeSortIndex).toBe(0)
      expect(result.current.sortDirection).toBe('asc')
    })

    it('uses custom initial options', () => {
      const { result } = renderHook(() => useTableSort({ initialSortIndex: 2, initialDirection: 'desc' }))

      expect(result.current.activeSortIndex).toBe(2)
      expect(result.current.sortDirection).toBe('desc')
    })
  })

  describe('getSortParams', () => {
    it('returns correct sort params for column', () => {
      const { result } = renderHook(() => useTableSort())

      const sortParams = result.current.getSortParams(1)

      expect(sortParams).toMatchObject({
        sortBy: {
          index: 0,
          direction: 'asc',
          defaultDirection: 'asc',
        },
        columnIndex: 1,
      })
      expect(sortParams?.onSort).toBeDefined()
    })

    it('updates sort state when onSort is called', () => {
      const { result } = renderHook(() => useTableSort())

      const sortParams = result.current.getSortParams(2)
      act(() => {
        sortParams?.onSort?.(null as never, 2, 'desc' as SortByDirection, {})
      })

      expect(result.current.activeSortIndex).toBe(2)
      expect(result.current.sortDirection).toBe('desc')
    })

    it('calls onSortChange callback when sort changes', () => {
      const onSortChange = vi.fn()
      const { result } = renderHook(() => useTableSort({ onSortChange }))

      const sortParams = result.current.getSortParams(1)
      act(() => {
        sortParams?.onSort?.(null as never, 1, 'desc' as SortByDirection, {})
      })

      expect(onSortChange).toHaveBeenCalledTimes(1)
    })

    it('does not throw when onSortChange is not provided', () => {
      const { result } = renderHook(() => useTableSort())

      const sortParams = result.current.getSortParams(1)
      expect(() => {
        act(() => {
          sortParams?.onSort?.(null as never, 1, 'desc' as SortByDirection, {})
        })
      }).not.toThrow()
    })
  })

  describe('sortData', () => {
    it('sorts strings in ascending order', () => {
      const { result } = renderHook(() => useTableSort())

      const sorted = result.current.sortData(testData, (item) => item.name)

      expect(sorted.map((i) => i.name)).toEqual(['Alice', 'Bob', 'Charlie', 'David'])
    })

    it('sorts strings in descending order', () => {
      const { result } = renderHook(() => useTableSort({ initialDirection: 'desc' }))

      const sorted = result.current.sortData(testData, (item) => item.name)

      expect(sorted.map((i) => i.name)).toEqual(['David', 'Charlie', 'Bob', 'Alice'])
    })

    it('sorts numbers in ascending order', () => {
      const { result } = renderHook(() => useTableSort())

      const sorted = result.current.sortData(testData, (item) => item.value)

      expect(sorted.map((i) => i.value)).toEqual([10, 20, 30, 40])
    })

    it('sorts numbers in descending order', () => {
      const { result } = renderHook(() => useTableSort({ initialDirection: 'desc' }))

      const sorted = result.current.sortData(testData, (item) => item.value)

      expect(sorted.map((i) => i.value)).toEqual([40, 30, 20, 10])
    })

    it('sorts dates correctly', () => {
      const { result } = renderHook(() => useTableSort())

      const sorted = result.current.sortData(testData, (item) => item.date)

      // Null dates should be sorted to the end
      expect(sorted[0].date?.toISOString()).toContain('2024-01-01')
      expect(sorted[3].date).toBeNull()
    })

    it('handles null values by pushing them to the end', () => {
      const { result } = renderHook(() => useTableSort())

      const sorted = result.current.sortData(testData, (item) => item.date)

      expect(sorted[sorted.length - 1].date).toBeNull()
    })

    it('handles undefined values by pushing them to the end', () => {
      const dataWithUndefined = [
        { id: 1, value: 'b' },
        { id: 2, value: undefined },
        { id: 3, value: 'a' },
      ]

      const { result } = renderHook(() => useTableSort())

      const sorted = result.current.sortData(dataWithUndefined, (item) => item.value)

      expect(sorted.map((i) => i.value)).toEqual(['a', 'b', undefined])
    })

    it('handles both null values equally', () => {
      const dataWithNulls = [
        { id: 1, value: null },
        { id: 2, value: null },
        { id: 3, value: 'a' },
      ]

      const { result } = renderHook(() => useTableSort())

      const sorted = result.current.sortData(dataWithNulls, (item) => item.value)

      expect(sorted[0].value).toBe('a')
      expect(sorted[1].value).toBeNull()
      expect(sorted[2].value).toBeNull()
    })

    it('does not mutate original array', () => {
      const { result } = renderHook(() => useTableSort())
      const original = [...testData]

      result.current.sortData(testData, (item) => item.name)

      expect(testData).toEqual(original)
    })
  })
})
