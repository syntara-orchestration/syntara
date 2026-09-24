import { describe, expect, it, vi } from 'vitest'

import { FilterOperatorEnum, FilterTypeEnum } from '../../types/filters'

import { createFilterChangeHandler, getAuthSourceFilterDefinition, getUsernameFilterDefinition } from './userFilters'

vi.mock('../../client', () => ({
  authFetchClient: {
    GET: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

// Import after mock so vi.mocked() works
const { authFetchClient } = await import('../../client')

describe('userFilters', () => {
  describe('getUsernameFilterDefinition', () => {
    it('returns the correct filter definition', () => {
      const definition = getUsernameFilterDefinition()

      expect(definition).toEqual({
        key: 'username',
        label: 'Username',
        type: FilterTypeEnum.TEXT,
        operators: [FilterOperatorEnum.CONTAINS],
        defaultOperator: FilterOperatorEnum.CONTAINS,
        placeholder: 'Filter by username',
      })
    })

    it('returns a new object each time', () => {
      const a = getUsernameFilterDefinition()
      const b = getUsernameFilterDefinition()
      expect(a).not.toBe(b)
      expect(a).toEqual(b)
    })
  })

  describe('getAuthSourceFilterDefinition', () => {
    it('returns provider options on successful fetch', async () => {
      vi.mocked(authFetchClient.GET).mockResolvedValueOnce({
        data: {
          resources: [
            { name: 'AAP', id: '1', enabled: true },
            { name: 'Azure AD', id: '2', enabled: true },
          ],
        },
      } as never)

      const definition = getAuthSourceFilterDefinition()
      const options = await definition.asyncOptions!('')

      expect(options).toEqual([
        { value: 'Local', label: 'Local' },
        { value: 'AAP', label: 'AAP' },
        { value: 'Azure AD', label: 'Azure AD' },
      ])
    })

    it('returns only static options when fetch fails', async () => {
      vi.mocked(authFetchClient.GET).mockRejectedValueOnce(new Error('Network error'))

      const definition = getAuthSourceFilterDefinition()
      const options = await definition.asyncOptions!('')

      expect(options).toEqual([{ value: 'Local', label: 'Local' }])
    })

    it('returns only static options when providers list is empty', async () => {
      vi.mocked(authFetchClient.GET).mockResolvedValueOnce({
        data: { resources: [] },
      } as never)

      const definition = getAuthSourceFilterDefinition()
      const options = await definition.asyncOptions!('')

      expect(options).toEqual([{ value: 'Local', label: 'Local' }])
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

      handler([{ key: 'username', operator: 'contains', value: 'test' }])

      expect(resetCursor).toHaveBeenCalled()
      expect(setAllFilters).toHaveBeenCalledWith([{ key: 'username', operator: 'contains', value: 'test' }])
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

      handler([{ key: 'username', operator: 'contains', value: 'test' }])

      expect(resetCursor).not.toHaveBeenCalled()
      expect(setAllFilters).toHaveBeenCalled()
    })
  })
})
