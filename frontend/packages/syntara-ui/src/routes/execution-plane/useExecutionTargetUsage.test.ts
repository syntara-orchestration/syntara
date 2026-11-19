import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { executionPlaneClient } from '../../client'

import { useExecutionTargetUsage } from './useExecutionTargetUsage'

vi.mock('../../client', () => ({
  executionPlaneClient: {
    useQuery: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

type MockQueryReturn = Pick<UseQueryResult, 'data' | 'error' | 'isLoading'>

function mockQuery(overrides: Partial<MockQueryReturn> = {}) {
  vi.mocked(executionPlaneClient.useQuery).mockReturnValue({
    data: undefined,
    error: null,
    isLoading: false,
    ...overrides,
  } as ReturnType<typeof executionPlaneClient.useQuery>)
}

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

describe('useExecutionTargetUsage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockQuery()
  })

  it('disables the query when targetId is null', () => {
    renderHook(() => useExecutionTargetUsage(null), { wrapper: createWrapper() })

    expect(executionPlaneClient.useQuery).toHaveBeenCalledWith(
      'get',
      '/api/execution_plane/v1/execution_targets/{target_id}/usage',
      expect.anything(),
      expect.objectContaining({ enabled: false })
    )
  })

  it('enables the query and passes the target id when provided', () => {
    renderHook(() => useExecutionTargetUsage('et-001'), { wrapper: createWrapper() })

    expect(executionPlaneClient.useQuery).toHaveBeenCalledWith(
      'get',
      '/api/execution_plane/v1/execution_targets/{target_id}/usage',
      expect.objectContaining({
        params: { path: { target_id: 'et-001' } },
      }),
      expect.objectContaining({ enabled: true })
    )
  })

  it('returns the active workload count from query data', () => {
    mockQuery({ data: { target_id: 'et-001', active_workload_count: 7 } })

    const { result } = renderHook(() => useExecutionTargetUsage('et-001'), { wrapper: createWrapper() })

    expect(result.current.activeWorkloadCount).toBe(7)
    expect(result.current.usageFetchError).toBe(false)
  })

  it('defaults activeWorkloadCount to 0 when data is undefined', () => {
    mockQuery({ data: undefined })

    const { result } = renderHook(() => useExecutionTargetUsage('et-001'), { wrapper: createWrapper() })

    expect(result.current.activeWorkloadCount).toBe(0)
  })

  it('sets usageFetchError when the query has an error', () => {
    mockQuery({ error: new Error('Server error') })

    const { result } = renderHook(() => useExecutionTargetUsage('et-001'), { wrapper: createWrapper() })

    expect(result.current.usageFetchError).toBe(true)
    expect(result.current.activeWorkloadCount).toBe(0)
  })

  it('reports isLoadingUsage when the query is loading and a target id is present', () => {
    mockQuery({ isLoading: true })

    const { result } = renderHook(() => useExecutionTargetUsage('et-001'), { wrapper: createWrapper() })

    expect(result.current.isLoadingUsage).toBe(true)
  })

  it('does not report isLoadingUsage when targetId is null even if the query shows loading', () => {
    mockQuery({ isLoading: true })

    const { result } = renderHook(() => useExecutionTargetUsage(null), { wrapper: createWrapper() })

    expect(result.current.isLoadingUsage).toBe(false)
  })

  it('updates query params and enabled when targetId transitions across rerenders', () => {
    mockQuery({ data: { target_id: 'et-001', active_workload_count: 7 } })

    type HookProps = { targetId: string | null }
    const initialProps: HookProps = { targetId: 'et-001' }
    const { result, rerender } = renderHook(({ targetId }: HookProps) => useExecutionTargetUsage(targetId), {
      wrapper: createWrapper(),
      initialProps,
    })

    expect(result.current.activeWorkloadCount).toBe(7)
    expect(executionPlaneClient.useQuery).toHaveBeenLastCalledWith(
      'get',
      '/api/execution_plane/v1/execution_targets/{target_id}/usage',
      expect.objectContaining({ params: { path: { target_id: 'et-001' } } }),
      expect.objectContaining({ enabled: true })
    )

    mockQuery({ data: undefined, isLoading: true })
    rerender({ targetId: null })

    expect(result.current.activeWorkloadCount).toBe(0)
    expect(result.current.isLoadingUsage).toBe(false)
    expect(executionPlaneClient.useQuery).toHaveBeenLastCalledWith(
      'get',
      '/api/execution_plane/v1/execution_targets/{target_id}/usage',
      expect.objectContaining({ params: { path: { target_id: '' } } }),
      expect.objectContaining({ enabled: false })
    )

    mockQuery({ data: { target_id: 'et-002', active_workload_count: 2 } })
    rerender({ targetId: 'et-002' })

    expect(result.current.activeWorkloadCount).toBe(2)
    expect(executionPlaneClient.useQuery).toHaveBeenLastCalledWith(
      'get',
      '/api/execution_plane/v1/execution_targets/{target_id}/usage',
      expect.objectContaining({ params: { path: { target_id: 'et-002' } } }),
      expect.objectContaining({ enabled: true })
    )
  })
})
