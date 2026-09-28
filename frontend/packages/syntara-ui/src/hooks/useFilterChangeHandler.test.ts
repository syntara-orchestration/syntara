import { describe, expect, it, vi } from 'vitest'

import type { FilterConfig } from '../types/filters'

import { createFilterChangeHandler } from './useFilterChangeHandler'

describe('createFilterChangeHandler', () => {
  it('resets cursor when cursor is set and filters change', () => {
    const resetCursor = vi.fn()
    const clearAllFilters = vi.fn()
    const setAllFilters = vi.fn()

    const handler = createFilterChangeHandler({ cursor: 'page-2-cursor', resetCursor, clearAllFilters, setAllFilters })

    const newFilters: FilterConfig[] = [{ key: 'name', operator: 'contains', value: 'test' }]
    handler(newFilters)

    expect(resetCursor).toHaveBeenCalledOnce()
    expect(setAllFilters).toHaveBeenCalledWith(newFilters)
    expect(clearAllFilters).not.toHaveBeenCalled()
  })

  it('does not reset cursor when cursor is null', () => {
    const resetCursor = vi.fn()
    const clearAllFilters = vi.fn()
    const setAllFilters = vi.fn()

    const handler = createFilterChangeHandler({ cursor: null, resetCursor, clearAllFilters, setAllFilters })

    const newFilters: FilterConfig[] = [{ key: 'name', operator: 'contains', value: 'test' }]
    handler(newFilters)

    expect(resetCursor).not.toHaveBeenCalled()
    expect(setAllFilters).toHaveBeenCalledWith(newFilters)
  })

  it('calls clearAllFilters when filters array is empty', () => {
    const resetCursor = vi.fn()
    const clearAllFilters = vi.fn()
    const setAllFilters = vi.fn()

    const handler = createFilterChangeHandler({ cursor: 'page-2-cursor', resetCursor, clearAllFilters, setAllFilters })

    handler([])

    expect(resetCursor).toHaveBeenCalledOnce()
    expect(clearAllFilters).toHaveBeenCalledOnce()
    expect(setAllFilters).not.toHaveBeenCalled()
  })

  it('calls setAllFilters with filters when array is not empty', () => {
    const resetCursor = vi.fn()
    const clearAllFilters = vi.fn()
    const setAllFilters = vi.fn()

    const handler = createFilterChangeHandler({ cursor: null, resetCursor, clearAllFilters, setAllFilters })

    const newFilters: FilterConfig[] = [
      { key: 'name', operator: 'contains', value: 'test' },
      { key: 'status', operator: 'eq', value: 'active' },
    ]
    handler(newFilters)

    expect(setAllFilters).toHaveBeenCalledWith(newFilters)
    expect(clearAllFilters).not.toHaveBeenCalled()
  })

  it('applies transformation function when provided', () => {
    const resetCursor = vi.fn()
    const clearAllFilters = vi.fn()
    const setAllFilters = vi.fn()
    const transformFilters = vi.fn((filters: FilterConfig[]) =>
      filters.map((filter) => {
        if (filter.key === 'is_enabled' && typeof filter.value === 'string') {
          return { ...filter, value: filter.value === 'true' }
        }
        return filter
      })
    )

    const handler = createFilterChangeHandler({
      cursor: null,
      resetCursor,
      clearAllFilters,
      setAllFilters,
      transformFilters,
    })

    const newFilters: FilterConfig[] = [{ key: 'is_enabled', operator: 'eq', value: 'true' }]
    handler(newFilters)

    expect(transformFilters).toHaveBeenCalledWith(newFilters)
    expect(setAllFilters).toHaveBeenCalledWith([{ key: 'is_enabled', operator: 'eq', value: true }])
  })

  it('does not apply transformation when not provided', () => {
    const resetCursor = vi.fn()
    const clearAllFilters = vi.fn()
    const setAllFilters = vi.fn()

    const handler = createFilterChangeHandler({ cursor: null, resetCursor, clearAllFilters, setAllFilters })

    const newFilters: FilterConfig[] = [{ key: 'is_enabled', operator: 'eq', value: 'true' }]
    handler(newFilters)

    expect(setAllFilters).toHaveBeenCalledWith(newFilters)
  })

  it('transformation function preserves filters that do not match condition', () => {
    const resetCursor = vi.fn()
    const clearAllFilters = vi.fn()
    const setAllFilters = vi.fn()
    const transformFilters = (filters: FilterConfig[]) =>
      filters.map((filter) => {
        if (filter.key === 'is_enabled' && typeof filter.value === 'string') {
          return { ...filter, value: filter.value === 'true' }
        }
        return filter
      })

    const handler = createFilterChangeHandler({
      cursor: null,
      resetCursor,
      clearAllFilters,
      setAllFilters,
      transformFilters,
    })

    const newFilters: FilterConfig[] = [
      { key: 'name', operator: 'contains', value: 'test' },
      { key: 'is_enabled', operator: 'eq', value: 'false' },
    ]
    handler(newFilters)

    expect(setAllFilters).toHaveBeenCalledWith([
      { key: 'name', operator: 'contains', value: 'test' },
      { key: 'is_enabled', operator: 'eq', value: false },
    ])
  })

  it('resets cursor before clearing filters', () => {
    const resetCursor = vi.fn()
    const clearAllFilters = vi.fn()
    const setAllFilters = vi.fn()

    const handler = createFilterChangeHandler({ cursor: 'cursor', resetCursor, clearAllFilters, setAllFilters })

    handler([])

    expect(resetCursor).toHaveBeenCalled()
    expect(clearAllFilters).toHaveBeenCalled()
    // Verify resetCursor was called before clearAllFilters
    expect(resetCursor.mock.invocationCallOrder[0]).toBeLessThan(clearAllFilters.mock.invocationCallOrder[0])
  })

  it('resets cursor before setting filters', () => {
    const resetCursor = vi.fn()
    const clearAllFilters = vi.fn()
    const setAllFilters = vi.fn()

    const handler = createFilterChangeHandler({ cursor: 'cursor', resetCursor, clearAllFilters, setAllFilters })

    const newFilters: FilterConfig[] = [{ key: 'name', operator: 'contains', value: 'test' }]
    handler(newFilters)

    expect(resetCursor).toHaveBeenCalled()
    expect(setAllFilters).toHaveBeenCalled()
    // Verify resetCursor was called before setAllFilters
    expect(resetCursor.mock.invocationCallOrder[0]).toBeLessThan(setAllFilters.mock.invocationCallOrder[0])
  })
})
