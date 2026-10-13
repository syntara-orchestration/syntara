import { renderHook } from '@testing-library/react'

import { useRetryFromFailurePreview } from './useRetryFromFailurePreview'

type MockQueryResult = {
  data?: unknown
  isPending: boolean
  isError: boolean
}

const mockUseQuery = vi.fn<(method: unknown, path: unknown, params: unknown, options: unknown) => MockQueryResult>()

vi.mock('../../../client', () => ({
  executionsClient: {
    useQuery: (method: unknown, path: unknown, params: unknown, options: unknown): MockQueryResult =>
      mockUseQuery(method, path, params, options),
  },
  authMiddleware: { onRequest: vi.fn() },
}))

function mockQueryResult(overrides: Record<string, unknown> = {}) {
  mockUseQuery.mockReturnValue({ data: undefined, isPending: false, isError: false, ...overrides })
}

describe('useRetryFromFailurePreview', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockQueryResult()
  })

  it('requests the preview for the given execution', () => {
    renderHook(() => useRetryFromFailurePreview({ executionId: 'exec-abc', enabled: true }))

    expect(mockUseQuery).toHaveBeenCalledWith(
      'get',
      '/executions/{execution_id}/retry-from-failure-preview',
      { params: { path: { execution_id: 'exec-abc' } } },
      expect.objectContaining({ enabled: true })
    )
  })

  it('does not fetch while the dialog is closed', () => {
    renderHook(() => useRetryFromFailurePreview({ executionId: 'exec-abc', enabled: false }))

    expect(mockUseQuery).toHaveBeenCalledWith(
      'get',
      '/executions/{execution_id}/retry-from-failure-preview',
      expect.anything(),
      expect.objectContaining({ enabled: false })
    )
  })

  it('exposes the preview payload', () => {
    const preview = { eligible: true, eligible_point_ids: ['a'], total_step_count: 2 }
    mockQueryResult({ data: preview })

    const { result } = renderHook(() => useRetryFromFailurePreview({ executionId: 'exec-abc', enabled: true }))

    expect(result.current.preview).toEqual(preview)
  })

  it('reports loading while the dialog is open', () => {
    mockQueryResult({ isPending: true })

    const { result } = renderHook(() => useRetryFromFailurePreview({ executionId: 'exec-abc', enabled: true }))

    expect(result.current.isLoading).toBe(true)
  })

  it('does not report loading while the dialog is closed', () => {
    mockQueryResult({ isPending: true })

    const { result } = renderHook(() => useRetryFromFailurePreview({ executionId: 'exec-abc', enabled: false }))

    expect(result.current.isLoading).toBe(false)
  })

  it('exposes an ineligible preview as data, not as an error', () => {
    mockQueryResult({ data: { eligible: false, reason: 'Nothing failed.' }, isPending: false, isError: false })

    const { result } = renderHook(() => useRetryFromFailurePreview({ executionId: 'exec-abc', enabled: true }))

    expect(result.current.preview).toEqual({ eligible: false, reason: 'Nothing failed.' })
    expect(result.current.isError).toBe(false)
  })

  it('surfaces a transport failure as an error', () => {
    mockQueryResult({ isError: true })

    const { result } = renderHook(() => useRetryFromFailurePreview({ executionId: 'exec-abc', enabled: true }))

    expect(result.current.isError).toBe(true)
  })
})
