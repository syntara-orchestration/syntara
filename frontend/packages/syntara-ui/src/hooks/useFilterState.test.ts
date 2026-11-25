import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

import type { FilterConfig } from '../types/filters'

import { useFilterState } from './useFilterState'

// Mock the URL search params hook
const mockSetSearchParams = vi.fn()
let mockSearchParams = new URLSearchParams()

vi.mock('./routing/useSearchParams', () => ({
  useSearchParams: () => [mockSearchParams, mockSetSearchParams],
}))

describe('useFilterState', () => {
  beforeEach(() => {
    // Reset mocks before each test
    mockSearchParams = new URLSearchParams()
    mockSetSearchParams.mockClear()
  })

  describe('filters', () => {
    it('should return empty array when no filters in URL', () => {
      const { result } = renderHook(() => useFilterState())

      expect(result.current.filters).toEqual([])
    })

    it('should parse filters from URL', () => {
      mockSearchParams = new URLSearchParams('name[contains]=deploy&is_enabled=true')

      const { result } = renderHook(() => useFilterState())

      expect(result.current.filters).toEqual([
        { key: 'name', operator: 'contains', value: 'deploy' },
        { key: 'is_enabled', operator: 'eq', value: 'true' },
      ])
    })

    it('should parse multiple filters with in operator from URL', () => {
      mockSearchParams = new URLSearchParams('status[in]=running,failed,pending')

      const { result } = renderHook(() => useFilterState())

      expect(result.current.filters).toEqual([
        { key: 'status', operator: 'in', value: ['running', 'failed', 'pending'] },
      ])
    })

    it('should use default filters when URL has no filters', () => {
      const defaultFilters: FilterConfig[] = [{ key: 'is_enabled', value: true }]

      const { result } = renderHook(() => useFilterState(defaultFilters))

      expect(result.current.filters).toEqual(defaultFilters)
    })

    it('should prefer URL filters over default filters', () => {
      mockSearchParams = new URLSearchParams('name[contains]=deploy')
      const defaultFilters: FilterConfig[] = [{ key: 'is_enabled', value: true }]

      const { result } = renderHook(() => useFilterState(defaultFilters))

      expect(result.current.filters).toEqual([{ key: 'name', operator: 'contains', value: 'deploy' }])
    })

    it('should handle date filters from URL', () => {
      mockSearchParams = new URLSearchParams('created_at[gte]=2024-01-01T00:00:00.000Z')

      const { result } = renderHook(() => useFilterState())

      expect(result.current.filters).toEqual([
        { key: 'created_at', operator: 'gte', value: '2024-01-01T00:00:00.000Z' },
      ])
    })

    it('should skip invalid operators from URL', () => {
      mockSearchParams = new URLSearchParams('name[invalid]=test&status[in]=running')

      const { result } = renderHook(() => useFilterState())

      // Should only include valid operator
      expect(result.current.filters).toEqual([{ key: 'status', operator: 'in', value: ['running'] }])
    })
  })

  describe('setFilter', () => {
    it('should add a new filter to URL', () => {
      const { result } = renderHook(() => useFilterState())

      act(() => {
        result.current.setFilter({ key: 'name', operator: 'contains', value: 'deploy' })
      })

      expect(mockSetSearchParams).toHaveBeenCalledWith(expect.any(URLSearchParams))
      const calledParams = mockSetSearchParams.mock.calls[0][0] as URLSearchParams
      expect(calledParams.get('name[contains]')).toBe('deploy')
    })

    it('should replace existing filter with same key', () => {
      mockSearchParams = new URLSearchParams('name[contains]=old')

      const { result } = renderHook(() => useFilterState())

      act(() => {
        result.current.setFilter({ key: 'name', operator: 'contains', value: 'new' })
      })

      expect(mockSetSearchParams).toHaveBeenCalledWith(expect.any(URLSearchParams))
      const calledParams = mockSetSearchParams.mock.calls[0][0] as URLSearchParams
      expect(calledParams.get('name[contains]')).toBe('new')
      // Should only have one name filter
      expect(Array.from(calledParams.keys()).filter((k) => k.startsWith('name'))).toHaveLength(1)
    })

    it('should add filter to existing filters', () => {
      mockSearchParams = new URLSearchParams('name[contains]=deploy')

      const { result } = renderHook(() => useFilterState())

      act(() => {
        result.current.setFilter({ key: 'is_enabled', value: true })
      })

      expect(mockSetSearchParams).toHaveBeenCalledWith(expect.any(URLSearchParams))
      const calledParams = mockSetSearchParams.mock.calls[0][0] as URLSearchParams
      expect(calledParams.get('name[contains]')).toBe('deploy')
      expect(calledParams.get('is_enabled')).toBe('true')
    })

    it('should handle filter with in operator (array value)', () => {
      const { result } = renderHook(() => useFilterState())

      act(() => {
        result.current.setFilter({ key: 'status', operator: 'in', value: ['running', 'failed'] })
      })

      expect(mockSetSearchParams).toHaveBeenCalledWith(expect.any(URLSearchParams))
      const calledParams = mockSetSearchParams.mock.calls[0][0] as URLSearchParams
      expect(calledParams.get('status[in]')).toBe('running,failed')
    })

    it('should handle filter with date value', () => {
      const { result } = renderHook(() => useFilterState())
      const date = new Date('2024-01-01T00:00:00.000Z')

      act(() => {
        result.current.setFilter({ key: 'created_at', operator: 'gte', value: date })
      })

      expect(mockSetSearchParams).toHaveBeenCalledWith(expect.any(URLSearchParams))
      const calledParams = mockSetSearchParams.mock.calls[0][0] as URLSearchParams
      expect(calledParams.get('created_at[gte]')).toBe('2024-01-01T00:00:00.000Z')
    })

    it('should handle boolean filter', () => {
      const { result } = renderHook(() => useFilterState())

      act(() => {
        result.current.setFilter({ key: 'is_enabled', value: true })
      })

      expect(mockSetSearchParams).toHaveBeenCalledWith(expect.any(URLSearchParams))
      const calledParams = mockSetSearchParams.mock.calls[0][0] as URLSearchParams
      expect(calledParams.get('is_enabled')).toBe('true')
    })
  })

  describe('removeFilter', () => {
    it('should remove a filter by key', () => {
      mockSearchParams = new URLSearchParams('name[contains]=deploy&is_enabled=true')

      const { result } = renderHook(() => useFilterState())

      act(() => {
        result.current.removeFilter('name')
      })

      expect(mockSetSearchParams).toHaveBeenCalledWith(expect.any(URLSearchParams))
      const calledParams = mockSetSearchParams.mock.calls[0][0] as URLSearchParams
      expect(calledParams.has('name[contains]')).toBe(false)
      expect(calledParams.get('is_enabled')).toBe('true')
    })

    it('should clear all params when removing last filter', () => {
      mockSearchParams = new URLSearchParams('name[contains]=deploy')

      const { result } = renderHook(() => useFilterState())

      act(() => {
        result.current.removeFilter('name')
      })

      expect(mockSetSearchParams).toHaveBeenCalledWith(expect.any(URLSearchParams))
      const calledParams = mockSetSearchParams.mock.calls[0][0] as URLSearchParams
      expect(calledParams.toString()).toBe('')
    })

    it('should handle removing non-existent filter', () => {
      mockSearchParams = new URLSearchParams('name[contains]=deploy')

      const { result } = renderHook(() => useFilterState())

      act(() => {
        result.current.removeFilter('status')
      })

      expect(mockSetSearchParams).toHaveBeenCalledWith(expect.any(URLSearchParams))
      const calledParams = mockSetSearchParams.mock.calls[0][0] as URLSearchParams
      expect(calledParams.get('name[contains]')).toBe('deploy')
    })

    it('should handle removing from empty filters', () => {
      const { result } = renderHook(() => useFilterState())

      act(() => {
        result.current.removeFilter('name')
      })

      expect(mockSetSearchParams).toHaveBeenCalledWith(expect.any(URLSearchParams))
      const calledParams = mockSetSearchParams.mock.calls[0][0] as URLSearchParams
      expect(calledParams.toString()).toBe('')
    })
  })

  describe('clearAllFilters', () => {
    it('should clear all filters from URL', () => {
      mockSearchParams = new URLSearchParams('name[contains]=deploy&is_enabled=true&status[in]=running,failed')

      const { result } = renderHook(() => useFilterState())

      act(() => {
        result.current.clearAllFilters()
      })

      expect(mockSetSearchParams).toHaveBeenCalledWith(expect.any(URLSearchParams))
      const calledParams = mockSetSearchParams.mock.calls[0][0] as URLSearchParams
      expect(calledParams.toString()).toBe('')
    })

    it('should handle clearing when no filters exist', () => {
      const { result } = renderHook(() => useFilterState())

      act(() => {
        result.current.clearAllFilters()
      })

      expect(mockSetSearchParams).toHaveBeenCalledWith(expect.any(URLSearchParams))
      const calledParams = mockSetSearchParams.mock.calls[0][0] as URLSearchParams
      expect(calledParams.toString()).toBe('')
    })
  })

  describe('URL state persistence', () => {
    it('should support browser back/forward navigation', () => {
      // Initial state
      mockSearchParams = new URLSearchParams('name[contains]=deploy')
      const { result, rerender } = renderHook(() => useFilterState())

      expect(result.current.filters).toEqual([{ key: 'name', operator: 'contains', value: 'deploy' }])

      // Simulate adding a filter (forward navigation)
      act(() => {
        result.current.setFilter({ key: 'is_enabled', value: true })
      })

      // Simulate browser back button - URL changes back
      mockSearchParams = new URLSearchParams('name[contains]=deploy')
      rerender()

      expect(result.current.filters).toEqual([{ key: 'name', operator: 'contains', value: 'deploy' }])
    })

    it('should create shareable URL with all filters', () => {
      const { result, rerender } = renderHook(() => useFilterState())

      // Add first filter
      act(() => {
        result.current.setFilter({ key: 'name', operator: 'contains', value: 'deploy' })
      })
      // Simulate URL update
      mockSearchParams = new URLSearchParams('name[contains]=deploy')
      rerender()

      // Add second filter
      act(() => {
        result.current.setFilter({ key: 'is_enabled', value: true })
      })
      // Simulate URL update
      mockSearchParams = new URLSearchParams('name[contains]=deploy&is_enabled=true')
      rerender()

      // Add third filter
      act(() => {
        result.current.setFilter({ key: 'status', operator: 'in', value: ['running', 'failed'] })
      })

      // The URL params should contain all filters
      const lastCall = mockSetSearchParams.mock.calls[mockSetSearchParams.mock.calls.length - 1]
      const calledParams = lastCall[0] as URLSearchParams
      expect(calledParams.get('name[contains]')).toBe('deploy')
      expect(calledParams.get('is_enabled')).toBe('true')
      expect(calledParams.get('status[in]')).toBe('running,failed')
    })
  })

  describe('setAllFilters', () => {
    it('should replace all filters at once', () => {
      mockSearchParams = new URLSearchParams('name[contains]=old&status[in]=running')

      const { result } = renderHook(() => useFilterState())

      act(() => {
        result.current.setAllFilters([
          { key: 'is_enabled', value: true },
          { key: 'name', operator: 'contains', value: 'new' },
        ])
      })

      expect(mockSetSearchParams).toHaveBeenCalledWith(expect.any(URLSearchParams))
      const calledParams = mockSetSearchParams.mock.calls[0][0] as URLSearchParams
      // Old filters should be gone
      expect(calledParams.has('status[in]')).toBe(false)
      // New filters should be present
      expect(calledParams.get('is_enabled')).toBe('true')
      expect(calledParams.get('name[contains]')).toBe('new')
    })

    it('should clear all filters when given empty array', () => {
      mockSearchParams = new URLSearchParams('name[contains]=deploy&is_enabled=true')

      const { result } = renderHook(() => useFilterState())

      act(() => {
        result.current.setAllFilters([])
      })

      expect(mockSetSearchParams).toHaveBeenCalledWith(expect.any(URLSearchParams))
      const calledParams = mockSetSearchParams.mock.calls[0][0] as URLSearchParams
      expect(calledParams.toString()).toBe('')
    })

    it('should preserve filter order from input array', () => {
      const { result } = renderHook(() => useFilterState())

      const filters: FilterConfig[] = [
        { key: 'name', operator: 'contains', value: 'deploy' },
        { key: 'is_enabled', value: true },
        { key: 'status', operator: 'in', value: ['running', 'failed'] },
      ]

      act(() => {
        result.current.setAllFilters(filters)
      })

      expect(mockSetSearchParams).toHaveBeenCalledWith(expect.any(URLSearchParams))
      const calledParams = mockSetSearchParams.mock.calls[0][0] as URLSearchParams
      expect(calledParams.get('name[contains]')).toBe('deploy')
      expect(calledParams.get('is_enabled')).toBe('true')
      expect(calledParams.get('status[in]')).toBe('running,failed')
    })

    it('should handle setting filters when none exist', () => {
      const { result } = renderHook(() => useFilterState())

      act(() => {
        result.current.setAllFilters([{ key: 'name', operator: 'contains', value: 'test' }])
      })

      expect(mockSetSearchParams).toHaveBeenCalledWith(expect.any(URLSearchParams))
      const calledParams = mockSetSearchParams.mock.calls[0][0] as URLSearchParams
      expect(calledParams.get('name[contains]')).toBe('test')
    })

    it('should handle multiple filters with same key but different operators', () => {
      const { result } = renderHook(() => useFilterState())

      const filters: FilterConfig[] = [
        { key: 'created_at', operator: 'gte', value: new Date('2024-01-01') },
        { key: 'created_at', operator: 'lte', value: new Date('2024-12-31') },
      ]

      act(() => {
        result.current.setAllFilters(filters)
      })

      expect(mockSetSearchParams).toHaveBeenCalledWith(expect.any(URLSearchParams))
      const calledParams = mockSetSearchParams.mock.calls[0][0] as URLSearchParams
      expect(calledParams.get('created_at[gte]')).toBe('2024-01-01T00:00:00.000Z')
      expect(calledParams.get('created_at[lte]')).toBe('2024-12-31T00:00:00.000Z')
    })

    it('should make atomic update in single call', () => {
      mockSearchParams = new URLSearchParams('old_key=old_value')

      const { result } = renderHook(() => useFilterState())

      act(() => {
        result.current.setAllFilters([
          { key: 'key1', value: 'value1' },
          { key: 'key2', value: 'value2' },
          { key: 'key3', value: 'value3' },
        ])
      })

      // Should only call setSearchParams once, not multiple times
      expect(mockSetSearchParams).toHaveBeenCalledTimes(1)
      const calledParams = mockSetSearchParams.mock.calls[0][0] as URLSearchParams
      expect(calledParams.get('key1')).toBe('value1')
      expect(calledParams.get('key2')).toBe('value2')
      expect(calledParams.get('key3')).toBe('value3')
      expect(calledParams.has('old_key')).toBe(false)
    })

    it('should handle filters with boolean values', () => {
      const { result } = renderHook(() => useFilterState())

      act(() => {
        result.current.setAllFilters([
          { key: 'is_enabled', value: true },
          { key: 'is_archived', value: false },
        ])
      })

      expect(mockSetSearchParams).toHaveBeenCalledWith(expect.any(URLSearchParams))
      const calledParams = mockSetSearchParams.mock.calls[0][0] as URLSearchParams
      expect(calledParams.get('is_enabled')).toBe('true')
      expect(calledParams.get('is_archived')).toBe('false')
    })

    it('should remove old filter and add new filter', () => {
      mockSearchParams = new URLSearchParams('name[contains]=old')

      const { result } = renderHook(() => useFilterState())

      act(() => {
        result.current.setAllFilters([{ key: 'is_enabled', value: true }])
      })

      expect(mockSetSearchParams).toHaveBeenCalledWith(expect.any(URLSearchParams))
      const calledParams = mockSetSearchParams.mock.calls[0][0] as URLSearchParams
      // Old filter should be removed
      expect(calledParams.has('name[contains]')).toBe(false)
      // New filter should be added
      expect(calledParams.get('is_enabled')).toBe('true')
    })
  })

  describe('edge cases', () => {
    it('should handle empty string filter value', () => {
      const { result } = renderHook(() => useFilterState())

      act(() => {
        result.current.setFilter({ key: 'name', operator: 'contains', value: '' })
      })

      // Empty values are skipped by buildFilterParams
      const calledParams = mockSetSearchParams.mock.calls[0][0] as URLSearchParams
      expect(calledParams.toString()).toBe('')
    })

    it('should handle whitespace-only filter value', () => {
      const { result } = renderHook(() => useFilterState())

      act(() => {
        result.current.setFilter({ key: 'name', operator: 'contains', value: '   ' })
      })

      // Whitespace-only values are skipped by buildFilterParams
      const calledParams = mockSetSearchParams.mock.calls[0][0] as URLSearchParams
      expect(calledParams.toString()).toBe('')
    })

    it('should handle empty array filter value', () => {
      const { result } = renderHook(() => useFilterState())

      act(() => {
        result.current.setFilter({ key: 'status', operator: 'in', value: [] })
      })

      // Empty arrays are skipped by buildFilterParams
      const calledParams = mockSetSearchParams.mock.calls[0][0] as URLSearchParams
      expect(calledParams.toString()).toBe('')
    })

    it('should handle multiple rapid filter changes', () => {
      const { result } = renderHook(() => useFilterState())

      act(() => {
        result.current.setFilter({ key: 'name', operator: 'contains', value: 'a' })
        result.current.setFilter({ key: 'name', operator: 'contains', value: 'ab' })
        result.current.setFilter({ key: 'name', operator: 'contains', value: 'abc' })
      })

      // Should have been called 3 times
      expect(mockSetSearchParams).toHaveBeenCalledTimes(3)
      // Last call should have the final value
      const lastCall = mockSetSearchParams.mock.calls[2]
      const calledParams = lastCall[0] as URLSearchParams
      expect(calledParams.get('name[contains]')).toBe('abc')
    })
  })
})
