import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useClientPagination } from './useClientPagination'

const ITEMS = Array.from({ length: 25 }, (_, index) => `item-${index + 1}`)

describe('useClientPagination', () => {
  describe('default state', () => {
    it('starts on page 1 with perPage 20', () => {
      const { result } = renderHook(() => useClientPagination())

      expect(result.current.page).toBe(1)
      expect(result.current.perPage).toBe(20)
    })

    it('honors defaultPerPage', () => {
      const { result } = renderHook(() => useClientPagination({ defaultPerPage: 10 }))

      expect(result.current.perPage).toBe(10)
    })
  })

  describe('paginate', () => {
    it('returns the first page slice', () => {
      const { result } = renderHook(() => useClientPagination({ defaultPerPage: 10 }))

      expect(result.current.paginate(ITEMS)).toEqual(ITEMS.slice(0, 10))
    })

    it('returns the current page slice after navigating forward', () => {
      const { result } = renderHook(() => useClientPagination({ defaultPerPage: 10 }))

      act(() => {
        result.current.getFooterProps(ITEMS.length).onNext()
      })

      expect(result.current.page).toBe(2)
      expect(result.current.paginate(ITEMS)).toEqual(ITEMS.slice(10, 20))
    })

    it('returns an empty array for empty input', () => {
      const { result } = renderHook(() => useClientPagination())

      expect(result.current.paginate([])).toEqual([])
    })

    it('returns a partial last page', () => {
      const { result } = renderHook(() => useClientPagination({ defaultPerPage: 10 }))

      act(() => {
        result.current.getFooterProps(ITEMS.length).onNext()
        result.current.getFooterProps(ITEMS.length).onNext()
      })

      expect(result.current.paginate(ITEMS)).toEqual(ITEMS.slice(20, 25))
    })
  })

  describe('resetPage', () => {
    it('returns to page 1', () => {
      const { result } = renderHook(() => useClientPagination())

      act(() => {
        result.current.getFooterProps(ITEMS.length).onNext()
      })
      expect(result.current.page).toBe(2)

      act(() => {
        result.current.resetPage()
      })

      expect(result.current.page).toBe(1)
    })
  })

  describe('handlePerPageChange', () => {
    it('updates perPage and resets to page 1', () => {
      const { result } = renderHook(() => useClientPagination())

      act(() => {
        result.current.getFooterProps(ITEMS.length).onNext()
        result.current.handlePerPageChange(50)
      })

      expect(result.current.page).toBe(1)
      expect(result.current.perPage).toBe(50)
      expect(result.current.paginate(ITEMS)).toEqual(ITEMS)
    })
  })

  describe('getFooterProps', () => {
    it('includes total and hasNext for a multi-page dataset', () => {
      const { result } = renderHook(() => useClientPagination({ defaultPerPage: 10 }))

      const footer = result.current.getFooterProps(ITEMS.length)

      expect(footer).toMatchObject({
        page: 1,
        perPage: 10,
        total: ITEMS.length,
        hasNext: true,
      })
    })

    it('sets hasNext false on the last page', () => {
      const { result } = renderHook(() => useClientPagination({ defaultPerPage: 10 }))

      act(() => {
        result.current.getFooterProps(ITEMS.length).onNext()
        result.current.getFooterProps(ITEMS.length).onNext()
      })

      expect(result.current.getFooterProps(ITEMS.length).hasNext).toBe(false)
    })

    it('does not go below page 1 on prev', () => {
      const { result } = renderHook(() => useClientPagination())

      act(() => {
        result.current.getFooterProps(ITEMS.length).onPrev()
      })

      expect(result.current.page).toBe(1)
    })

    it('wires onPerPageChange to handlePerPageChange', () => {
      const { result } = renderHook(() => useClientPagination())

      act(() => {
        result.current.getFooterProps(ITEMS.length).onPerPageChange(5)
      })

      expect(result.current.perPage).toBe(5)
      expect(result.current.page).toBe(1)
    })
  })
})
