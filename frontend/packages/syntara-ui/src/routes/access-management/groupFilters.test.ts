import { describe, expect, it, vi } from 'vitest'

import { FilterOperatorEnum, FilterTypeEnum } from '../../types/filters'

import { createFilterChangeHandler, getGroupNameFilterDefinition } from './groupFilters'

describe('groupFilters', () => {
  describe('getGroupNameFilterDefinition', () => {
    it('returns the correct filter definition', () => {
      const definition = getGroupNameFilterDefinition()

      expect(definition).toEqual({
        key: 'name',
        label: 'Name',
        type: FilterTypeEnum.TEXT,
        operators: [FilterOperatorEnum.CONTAINS],
        defaultOperator: FilterOperatorEnum.CONTAINS,
        placeholder: 'Filter by name',
      })
    })

    it('returns a new object each time', () => {
      const a = getGroupNameFilterDefinition()
      const b = getGroupNameFilterDefinition()
      expect(a).not.toBe(b)
      expect(a).toEqual(b)
    })
  })

  describe('createFilterChangeHandler (re-export)', () => {
    it('is exported and callable', () => {
      expect(typeof createFilterChangeHandler).toBe('function')
    })

    it('resets cursor and applies filters', () => {
      const resetCursor = vi.fn()
      const clearAllFilters = vi.fn()
      const setAllFilters = vi.fn()

      const handler = createFilterChangeHandler({ cursor: 'some-cursor', resetCursor, clearAllFilters, setAllFilters })

      handler([{ key: 'name', operator: 'contains', value: 'test' }])

      expect(resetCursor).toHaveBeenCalled()
      expect(setAllFilters).toHaveBeenCalledWith([{ key: 'name', operator: 'contains', value: 'test' }])
    })

    it('calls clearAllFilters when filters are empty', () => {
      const resetCursor = vi.fn()
      const clearAllFilters = vi.fn()
      const setAllFilters = vi.fn()

      const handler = createFilterChangeHandler({ cursor: null, resetCursor, clearAllFilters, setAllFilters })

      handler([])

      expect(clearAllFilters).toHaveBeenCalled()
      expect(setAllFilters).not.toHaveBeenCalled()
    })

    it('does not reset cursor when cursor is null', () => {
      const resetCursor = vi.fn()
      const clearAllFilters = vi.fn()
      const setAllFilters = vi.fn()

      const handler = createFilterChangeHandler({ cursor: null, resetCursor, clearAllFilters, setAllFilters })

      handler([{ key: 'name', operator: 'contains', value: 'test' }])

      expect(resetCursor).not.toHaveBeenCalled()
      expect(setAllFilters).toHaveBeenCalled()
    })
  })
})
