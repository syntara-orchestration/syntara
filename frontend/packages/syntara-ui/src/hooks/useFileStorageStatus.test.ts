import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { filesClient } from '../client'

import { useFileStorageStatus } from './useFileStorageStatus'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../client', () => ({
  filesClient: {
    useQuery: vi.fn(),
  },
  filesFetchClient: {
    use: vi.fn(),
  },
}))

const mockUseQuery = vi.mocked(filesClient.useQuery)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type MockQueryResult = {
  data: unknown
  isLoading: boolean
  isError: boolean
}

function settled(status: string): MockQueryResult {
  return { data: { status }, isLoading: false, isError: false }
}

const FIVE_MINUTES_MS = 5 * 60 * 1000

const loadingResult: MockQueryResult = { data: undefined, isLoading: true, isError: false }
const errorResult: MockQueryResult = { data: undefined, isLoading: false, isError: true }

function mockResult(result: MockQueryResult) {
  mockUseQuery.mockReturnValue(result)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useFileStorageStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns isConfigured true and status "ok" when storage is ok', () => {
    mockResult(settled('ok'))

    const { result } = renderHook(() => useFileStorageStatus())

    expect(result.current.isConfigured).toBe(true)
    expect(result.current.status).toBe('ok')
    expect(result.current.isError).toBe(false)
  })

  it('queries the file storage status endpoint', () => {
    mockResult(settled('ok'))

    renderHook(() => useFileStorageStatus())

    expect(mockUseQuery).toHaveBeenCalledWith('get', '/files/storage_status', {}, expect.objectContaining({ retry: 1 }))
  })

  it('polls on an interval so the gate recovers without a reload', () => {
    // staleTime alone only marks data stale — it never schedules a refetch,
    // so without refetchInterval a long-lived page keeps its first answer.
    mockResult(settled('ok'))

    renderHook(() => useFileStorageStatus())

    expect(mockUseQuery).toHaveBeenCalledWith(
      'get',
      '/files/storage_status',
      {},
      expect.objectContaining({ refetchInterval: FIVE_MINUTES_MS })
    )
  })

  it('re-enables uploads once storage recovers from degraded to ok', () => {
    mockResult(settled('degraded'))

    const { result, rerender } = renderHook(() => useFileStorageStatus())

    expect(result.current.isConfigured).toBe(false)

    mockResult(settled('ok'))
    rerender()

    expect(result.current.isConfigured).toBe(true)
    expect(result.current.status).toBe('ok')
  })

  it('disables uploads when storage breaks while the page is open', () => {
    mockResult(settled('ok'))

    const { result, rerender } = renderHook(() => useFileStorageStatus())

    expect(result.current.isConfigured).toBe(true)

    mockResult(settled('degraded'))
    rerender()

    expect(result.current.isConfigured).toBe(false)
    expect(result.current.status).toBe('degraded')
  })

  it.each(['degraded', 'error', 'unconfigured'] as const)(
    'returns isConfigured false and status "%s" when storage is "%s"',
    (status) => {
      mockResult(settled(status))

      const { result } = renderHook(() => useFileStorageStatus())

      expect(result.current.isConfigured).toBe(false)
      expect(result.current.status).toBe(status)
    }
  )

  it('defaults to isConfigured true and isLoading true while in flight', () => {
    mockResult(loadingResult)

    const { result } = renderHook(() => useFileStorageStatus())

    expect(result.current.isConfigured).toBe(true)
    expect(result.current.isLoading).toBe(true)
    expect(result.current.status).toBeUndefined()
  })

  it('defaults to isConfigured true when the query fails', () => {
    mockResult(errorResult)

    const { result } = renderHook(() => useFileStorageStatus())

    expect(result.current.isConfigured).toBe(true)
    expect(result.current.isError).toBe(true)
    expect(result.current.status).toBeUndefined()
  })
})
