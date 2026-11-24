import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { accessFetchClient } from './accessClient'
import { useAllProjects, useSelectableProjects } from './useAllProjects'

vi.mock('./accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  accessFetchClient: {
    GET: vi.fn(),
    use: vi.fn(),
  },
}))

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
)

describe('useAllProjects', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
  })

  it('returns projects on successful fetch', async () => {
    const mockProjects = [
      { id: 'p1', name: 'A', description: null, labels: {}, is_default: false, created_at: null, updated_at: null },
    ]

    vi.mocked(accessFetchClient.GET).mockResolvedValue({
      data: { resources: mockProjects },
      error: null,
    } as never)

    const { result } = renderHook(() => useAllProjects(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.projects).toEqual(mockProjects)
    expect(result.current.error).toBeNull()
  })

  it('paginates through multiple pages', async () => {
    const page1 = [
      { id: 'p1', name: 'A', description: null, labels: {}, is_default: false, created_at: null, updated_at: null },
    ]
    const page2 = [
      { id: 'p2', name: 'B', description: null, labels: {}, is_default: false, created_at: null, updated_at: null },
    ]

    vi.mocked(accessFetchClient.GET)
      .mockResolvedValueOnce({ data: { resources: page1, next: 'cursor-1' }, error: null } as never)
      .mockResolvedValueOnce({ data: { resources: page2 }, error: null } as never)

    const { result } = renderHook(() => useAllProjects(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.projects).toEqual([...page1, ...page2])
    expect(accessFetchClient.GET).toHaveBeenCalledTimes(2)
  })

  it('returns error when fetch fails', async () => {
    vi.mocked(accessFetchClient.GET).mockResolvedValue({
      data: undefined,
      error: { detail: 'Forbidden' },
    } as never)

    const { result } = renderHook(() => useAllProjects(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.error).toBeTruthy()
  })

  it('is loading initially', () => {
    vi.mocked(accessFetchClient.GET).mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(() => useAllProjects(), { wrapper })

    expect(result.current.isLoading).toBe(true)
    expect(result.current.projects).toEqual([])
  })

  it('does not fetch or report loading when disabled', () => {
    const { result } = renderHook(() => useSelectableProjects({ enabled: false }), { wrapper })

    expect(accessFetchClient.GET).not.toHaveBeenCalled()
    expect(result.current.isLoading).toBe(false)
    expect(result.current.projects).toEqual([])
  })

  it('passes correct query parameters without is_builtin filter', async () => {
    vi.mocked(accessFetchClient.GET).mockResolvedValue({
      data: { resources: [] },
      error: null,
    } as never)

    renderHook(() => useAllProjects(), { wrapper })

    await waitFor(() => {
      expect(accessFetchClient.GET).toHaveBeenCalledWith('/projects', {
        params: { query: { sort: 'name', limit: 100, cursor: undefined } },
      })
    })
  })

  it('does not fetch when enabled is false', () => {
    const { result } = renderHook(() => useAllProjects({ enabled: false }), { wrapper })

    expect(accessFetchClient.GET).not.toHaveBeenCalled()
    expect(result.current.isLoading).toBe(false)
    expect(result.current.projects).toEqual([])
  })
})

describe('useSelectableProjects', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
  })

  it('passes is_builtin: false to exclude the built-in project', async () => {
    vi.mocked(accessFetchClient.GET).mockResolvedValue({
      data: { resources: [] },
      error: null,
    } as never)

    renderHook(() => useSelectableProjects(), { wrapper })

    await waitFor(() => {
      expect(accessFetchClient.GET).toHaveBeenCalledWith('/projects', {
        params: { query: { sort: 'name', limit: 100, cursor: undefined, is_builtin: false } },
      })
    })
  })

  it('returns projects from the response', async () => {
    const mockProjects = [
      { id: 'p1', name: 'Alpha', description: null, labels: {}, is_default: false, created_at: null, updated_at: null },
      { id: 'p2', name: 'Beta', description: null, labels: {}, is_default: false, created_at: null, updated_at: null },
    ]

    vi.mocked(accessFetchClient.GET).mockResolvedValue({
      data: { resources: mockProjects },
      error: null,
    } as never)

    const { result } = renderHook(() => useSelectableProjects(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.projects).toEqual(mockProjects)
    expect(result.current.error).toBeNull()
  })

  it('is loading initially', () => {
    vi.mocked(accessFetchClient.GET).mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(() => useSelectableProjects(), { wrapper })

    expect(result.current.isLoading).toBe(true)
    expect(result.current.projects).toEqual([])
  })

  it('returns error when fetch fails', async () => {
    vi.mocked(accessFetchClient.GET).mockResolvedValue({
      data: undefined,
      error: { detail: 'Forbidden' },
    } as never)

    const { result } = renderHook(() => useSelectableProjects(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.error).toBeTruthy()
  })
})
