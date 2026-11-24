import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DEFAULT_MAX_WAIT_SECONDS, fetchMaxWaitDuration, useMaxWaitDuration } from './useMaxWaitDuration'

const mockGet = vi.fn()

vi.mock('../../../client', () => ({
  settingsFetchClient: {
    GET: () => mockGet() as Promise<unknown>,
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

const mockUseQuery = vi.fn()

vi.mock('@tanstack/react-query', () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args) as { data: unknown; isLoading: boolean; isFetching: boolean },
}))

describe('useMaxWaitDuration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: true, isFetching: true })
  })

  it('returns default max when loading', () => {
    const { result } = renderHook(() => useMaxWaitDuration())

    expect(result.current.maxSeconds).toBe(DEFAULT_MAX_WAIT_SECONDS)
    expect(result.current.isLoading).toBe(true)
  })

  it('returns numeric effective_value from query data', () => {
    mockUseQuery.mockReturnValue({ data: { effective_value: 7200 }, isLoading: false, isFetching: false })

    const { result } = renderHook(() => useMaxWaitDuration())

    expect(result.current.maxSeconds).toBe(7200)
    expect(result.current.isLoading).toBe(false)
  })

  it('returns default when effective_value is not a number', () => {
    mockUseQuery.mockReturnValue({ data: { effective_value: 'not a number' }, isLoading: false, isFetching: false })

    const { result } = renderHook(() => useMaxWaitDuration())

    expect(result.current.maxSeconds).toBe(DEFAULT_MAX_WAIT_SECONDS)
  })

  it('returns default when data is null', () => {
    mockUseQuery.mockReturnValue({ data: null, isLoading: false, isFetching: false })

    const { result } = renderHook(() => useMaxWaitDuration())

    expect(result.current.maxSeconds).toBe(DEFAULT_MAX_WAIT_SECONDS)
  })

  it('reports loading when isFetching is true even if isLoading is false', () => {
    mockUseQuery.mockReturnValue({ data: { effective_value: 3600 }, isLoading: false, isFetching: true })

    const { result } = renderHook(() => useMaxWaitDuration())

    expect(result.current.isLoading).toBe(true)
  })

  it('returns default when effective_value is NaN', () => {
    mockUseQuery.mockReturnValue({ data: { effective_value: Number.NaN }, isLoading: false, isFetching: false })

    const { result } = renderHook(() => useMaxWaitDuration())

    expect(result.current.maxSeconds).toBe(DEFAULT_MAX_WAIT_SECONDS)
  })

  it('returns default when effective_value is Infinity', () => {
    mockUseQuery.mockReturnValue({ data: { effective_value: Infinity }, isLoading: false, isFetching: false })

    const { result } = renderHook(() => useMaxWaitDuration())

    expect(result.current.maxSeconds).toBe(DEFAULT_MAX_WAIT_SECONDS)
  })

  it('returns default when effective_value is zero or negative', () => {
    mockUseQuery.mockReturnValue({ data: { effective_value: 0 }, isLoading: false, isFetching: false })

    const { result } = renderHook(() => useMaxWaitDuration())

    expect(result.current.maxSeconds).toBe(DEFAULT_MAX_WAIT_SECONDS)
  })

  it('exports DEFAULT_MAX_WAIT_SECONDS as 30 days', () => {
    expect(DEFAULT_MAX_WAIT_SECONDS).toBe(2_592_000)
  })

  it('passes correct queryKey and staleTime to useQuery', () => {
    renderHook(() => useMaxWaitDuration())

    const queryConfig = mockUseQuery.mock.calls[0][0] as { queryKey: string[]; staleTime: number; gcTime: number }
    expect(queryConfig.queryKey).toEqual(['setting', 'workflow_engine.max_wait_duration_seconds'])
    expect(queryConfig.staleTime).toBe(0)
    expect(queryConfig.gcTime).toBe(0)
  })

  it('queryFn calls settings API and returns data', async () => {
    mockGet.mockResolvedValue({ data: { effective_value: 9999 } })
    mockUseQuery.mockImplementation((config: { queryFn: () => Promise<unknown> }) => {
      return { data: undefined, isLoading: true, isFetching: true, queryFn: config.queryFn }
    })

    const { result } = renderHook(() => useMaxWaitDuration())
    const queryFn = (mockUseQuery.mock.calls[0][0] as { queryFn: () => Promise<unknown> }).queryFn
    const data = await queryFn()

    expect(data).toEqual({ effective_value: 9999 })
    expect(result.current.maxSeconds).toBe(DEFAULT_MAX_WAIT_SECONDS)
  })

  it('queryFn returns null when API returns no data', async () => {
    mockGet.mockResolvedValue({ data: undefined })
    mockUseQuery.mockImplementation((config: { queryFn: () => Promise<unknown> }) => {
      return { data: undefined, isLoading: false, isFetching: false, queryFn: config.queryFn }
    })

    renderHook(() => useMaxWaitDuration())
    const queryFn = (mockUseQuery.mock.calls[0][0] as { queryFn: () => Promise<unknown> }).queryFn
    const data = await queryFn()

    expect(data).toBeNull()
  })

  it('returns default when effective_value is negative', () => {
    mockUseQuery.mockReturnValue({ data: { effective_value: -5 }, isLoading: false, isFetching: false })

    const { result } = renderHook(() => useMaxWaitDuration())

    expect(result.current.maxSeconds).toBe(DEFAULT_MAX_WAIT_SECONDS)
  })
})

describe('fetchMaxWaitDuration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns numeric effective_value from API', async () => {
    mockGet.mockResolvedValue({ data: { effective_value: 7200 } })

    const result = await fetchMaxWaitDuration()

    expect(result).toBe(7200)
  })

  it('returns default when effective_value is not a number', async () => {
    mockGet.mockResolvedValue({ data: { effective_value: 'not a number' } })

    const result = await fetchMaxWaitDuration()

    expect(result).toBe(DEFAULT_MAX_WAIT_SECONDS)
  })

  it('returns default when data is null', async () => {
    mockGet.mockResolvedValue({ data: null })

    const result = await fetchMaxWaitDuration()

    expect(result).toBe(DEFAULT_MAX_WAIT_SECONDS)
  })

  it('returns default when effective_value is NaN', async () => {
    mockGet.mockResolvedValue({ data: { effective_value: Number.NaN } })

    const result = await fetchMaxWaitDuration()

    expect(result).toBe(DEFAULT_MAX_WAIT_SECONDS)
  })

  it('returns default when effective_value is Infinity', async () => {
    mockGet.mockResolvedValue({ data: { effective_value: Infinity } })

    const result = await fetchMaxWaitDuration()

    expect(result).toBe(DEFAULT_MAX_WAIT_SECONDS)
  })

  it('returns default on API error', async () => {
    mockGet.mockRejectedValue(new Error('Network error'))

    const result = await fetchMaxWaitDuration()

    expect(result).toBe(DEFAULT_MAX_WAIT_SECONDS)
  })

  it('returns default when effective_value is zero', async () => {
    mockGet.mockResolvedValue({ data: { effective_value: 0 } })

    const result = await fetchMaxWaitDuration()

    expect(result).toBe(DEFAULT_MAX_WAIT_SECONDS)
  })

  it('returns default when effective_value is negative', async () => {
    mockGet.mockResolvedValue({ data: { effective_value: -100 } })

    const result = await fetchMaxWaitDuration()

    expect(result).toBe(DEFAULT_MAX_WAIT_SECONDS)
  })
})
