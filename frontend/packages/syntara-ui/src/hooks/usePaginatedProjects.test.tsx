import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import type React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { accessClient } from '../routes/access/accessClient'
import type { ProjectRead } from '../routes/access/types'

import { usePaginatedProjects } from './usePaginatedProjects'

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../routes/access/accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
  },
}))

// ── Helpers ────────────────────────────────────────────────────────────────

function makeProject(id: string, name: string): ProjectRead {
  return {
    id,
    name,
    description: null,
    labels: {},
    is_default: false,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  }
}

const page1 = [makeProject('p1', 'Alpha'), makeProject('p2', 'Beta')]
const page2 = [makeProject('p3', 'Gamma'), makeProject('p4', 'Delta')]

function makeQueryData(resources: ProjectRead[], next: string | null = null, isFetching = false) {
  return {
    data: { resources, next, prev: null, total: resources.length },
    isPending: false,
    isFetching,
    refetch: vi.fn(),
  }
}

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}

// ── Tests ──────────────────────────────────────────────────────────────────

describe('usePaginatedProjects', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
    vi.mocked(accessClient.useQuery).mockReturnValue(makeQueryData(page1))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // ── Initial state ────────────────────────────────────────────────────────

  describe('initial state', () => {
    it('returns projects from query data', () => {
      const { result } = renderHook(() => usePaginatedProjects(), { wrapper })

      expect(result.current.projects).toEqual(page1)
      expect(result.current.filterValue).toBe('')
      expect(result.current.debouncedFilter).toBe('')
      expect(result.current.hasMore).toBe(false)
      expect(result.current.isInitialPage).toBe(true)
      expect(result.current.isLoadingMore).toBe(false)
    })

    it('does not filter out builtin projects so the project switcher shows them', () => {
      renderHook(() => usePaginatedProjects(), { wrapper })

      const callArgs = vi.mocked(accessClient.useQuery).mock.calls[0] as unknown[]
      const options = callArgs[2] as { params: { query: Record<string, unknown> } }
      expect(options.params.query).not.toHaveProperty('is_builtin')
    })

    it('returns empty array when query data is undefined', () => {
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: undefined,
        isPending: true,
        isFetching: false,
        refetch: vi.fn(),
      })

      const { result } = renderHook(() => usePaginatedProjects(), { wrapper })

      expect(result.current.projects).toEqual([])
    })
  })

  // ── updateFilter ─────────────────────────────────────────────────────────

  describe('updateFilter', () => {
    it('sets filterValue immediately', () => {
      const { result } = renderHook(() => usePaginatedProjects(), { wrapper })

      act(() => {
        result.current.updateFilter('alpha')
      })

      expect(result.current.filterValue).toBe('alpha')
    })

    it('updates debouncedFilter after 200ms debounce delay', () => {
      vi.useFakeTimers()
      const { result } = renderHook(() => usePaginatedProjects(), { wrapper })

      act(() => {
        result.current.updateFilter('beta')
      })
      expect(result.current.debouncedFilter).toBe('')

      act(() => {
        vi.advanceTimersByTime(199)
      })
      expect(result.current.debouncedFilter).toBe('')

      act(() => {
        vi.advanceTimersByTime(1)
      })
      expect(result.current.debouncedFilter).toBe('beta')
    })

    it('sends name[contains] query parameter for substring matching (AAP-81636)', () => {
      vi.useFakeTimers()
      renderHook(() => usePaginatedProjects(), { wrapper })

      const initialCall = vi.mocked(accessClient.useQuery).mock.calls[0] as unknown[]
      const initialQuery = (initialCall[2] as { params: { query: Record<string, unknown> } }).params.query
      expect(initialQuery).not.toHaveProperty('name[contains]')
      expect(initialQuery).not.toHaveProperty('name')

      vi.mocked(accessClient.useQuery).mockClear()

      const { result } = renderHook(() => usePaginatedProjects(), { wrapper })

      act(() => {
        result.current.updateFilter('alph')
      })
      act(() => {
        vi.advanceTimersByTime(200)
      })

      const filterCall = vi.mocked(accessClient.useQuery).mock.lastCall as unknown[]
      const filterQuery = (filterCall[2] as { params: { query: Record<string, unknown> } }).params.query
      expect(filterQuery).toHaveProperty('name[contains]', 'alph')
      expect(filterQuery).not.toHaveProperty('name')
    })

    it('sets isInitialPage to false once debouncedFilter is set', () => {
      vi.useFakeTimers()
      const { result } = renderHook(() => usePaginatedProjects(), { wrapper })

      act(() => {
        result.current.updateFilter('gamma')
      })
      act(() => {
        vi.advanceTimersByTime(200)
      })

      expect(result.current.isInitialPage).toBe(false)
    })
  })

  // ── resetPagination ───────────────────────────────────────────────────────

  describe('resetPagination', () => {
    it('clears filterValue', () => {
      const { result } = renderHook(() => usePaginatedProjects(), { wrapper })

      act(() => {
        result.current.updateFilter('alpha')
      })
      act(() => {
        result.current.resetPagination()
      })

      expect(result.current.filterValue).toBe('')
    })

    it('restores isInitialPage after reset', () => {
      vi.useFakeTimers()
      const { result } = renderHook(() => usePaginatedProjects(), { wrapper })

      act(() => {
        result.current.updateFilter('test')
      })
      act(() => {
        vi.advanceTimersByTime(200)
      })
      act(() => {
        result.current.resetPagination()
      })
      act(() => {
        vi.advanceTimersByTime(200)
      })

      expect(result.current.isInitialPage).toBe(true)
    })
  })

  describe('clearTypeaheadOnly', () => {
    it('clears filter text without collapsing merged pages', () => {
      vi.mocked(accessClient.useQuery).mockReturnValue(makeQueryData(page1, 'cursor-2'))
      const { result, rerender } = renderHook(() => usePaginatedProjects(), { wrapper })

      act(() => result.current.loadMore())
      vi.mocked(accessClient.useQuery).mockReturnValue(makeQueryData(page2))
      rerender()

      expect(result.current.projects).toHaveLength(4)

      act(() => result.current.clearTypeaheadOnly())

      expect(result.current.filterValue).toBe('')
      expect(result.current.projects).toHaveLength(4)
    })
  })

  // ── hasMore / loadMore ────────────────────────────────────────────────────

  describe('hasMore and loadMore', () => {
    it('hasMore is true when query returns a next cursor', () => {
      vi.mocked(accessClient.useQuery).mockReturnValue(makeQueryData(page1, 'cursor-2'))
      const { result } = renderHook(() => usePaginatedProjects(), { wrapper })

      expect(result.current.hasMore).toBe(true)
    })

    it('does not update cursor when no next page exists', () => {
      const { result } = renderHook(() => usePaginatedProjects(), { wrapper })

      act(() => {
        result.current.loadMore()
      })

      // Cursor remains null → still on initial page
      expect(result.current.isInitialPage).toBe(true)
    })

    it('accumulates page 2 projects after loadMore', () => {
      vi.mocked(accessClient.useQuery).mockReturnValue(makeQueryData(page1, 'cursor-2'))
      const { result, rerender } = renderHook(() => usePaginatedProjects(), { wrapper })

      act(() => {
        result.current.loadMore()
      })

      // Simulate the query returning page 2 after the cursor is set
      vi.mocked(accessClient.useQuery).mockReturnValue(makeQueryData(page2))
      rerender()

      expect(result.current.projects).toEqual([...page1, ...page2])
    })

    it('deduplicates projects that appear in both extraPages and the new page', () => {
      vi.mocked(accessClient.useQuery).mockReturnValue(makeQueryData(page1, 'cursor-2'))
      const { result, rerender } = renderHook(() => usePaginatedProjects(), { wrapper })

      act(() => {
        result.current.loadMore()
      })

      // page 2 overlaps: p1 is a duplicate
      const overlapPage = [page1[0], ...page2]
      vi.mocked(accessClient.useQuery).mockReturnValue(makeQueryData(overlapPage))
      rerender()

      const ids = result.current.projects.map((p) => p.id)
      expect(new Set(ids).size).toBe(ids.length) // no duplicates
      expect(ids).toContain('p1') // p1 appears exactly once
    })
  })

  // ── isLoadingMore ─────────────────────────────────────────────────────────

  describe('isLoadingMore', () => {
    it('is true when a cursor is set and the query is still fetching', () => {
      vi.mocked(accessClient.useQuery).mockReturnValue(makeQueryData(page1, 'cursor-2'))
      const { result, rerender } = renderHook(() => usePaginatedProjects(), { wrapper })

      act(() => {
        result.current.loadMore()
      })

      // Simulate in-flight refetch with the cursor
      vi.mocked(accessClient.useQuery).mockReturnValue(makeQueryData(page1, 'cursor-2', true))
      rerender()

      expect(result.current.isLoadingMore).toBe(true)
    })

    it('is false when no cursor is set', () => {
      const { result } = renderHook(() => usePaginatedProjects(), { wrapper })

      expect(result.current.isLoadingMore).toBe(false)
    })
  })
})
