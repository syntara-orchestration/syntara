import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { createElement } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ActivityStatus } from '../../workflows/execution/types'

import { useStepExecutionDetails, type UseStepExecutionDetailsParams } from './useStepExecutionDetails'

function useStepExecutionDetailsWithDefaults(overrides: Partial<UseStepExecutionDetailsParams> = {}) {
  return useStepExecutionDetails({
    stepId: 'my_activity',
    executionId: 'exec-1',
    ...overrides,
  })
}

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

type MockQueryResult = { data: unknown; isLoading: boolean; error: unknown; refetch: ReturnType<typeof vi.fn> }

const mockUseQuery = vi.fn<() => MockQueryResult>()

vi.mock('../../../client', () => ({
  executionsClient: {
    useQuery: (...args: unknown[]) => mockUseQuery(...(args as [])),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const mockActivityResponse = {
  resources: [
    {
      activity_name: 'my_activity',
      input_data: { host: '10.0.0.1', port: 8080 },
      output_data: { status: 'ok', result: 42 },
    },
  ],
}

function makeWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

let queryClient: QueryClient
let mockRefetch: ReturnType<typeof vi.fn>

beforeEach(() => {
  vi.clearAllMocks()
  mockRefetch = vi.fn().mockResolvedValue(undefined)
  mockUseQuery.mockReturnValue({ data: undefined, isLoading: false, error: null, refetch: mockRefetch })
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useStepExecutionDetails', () => {
  describe('return values — data mapping', () => {
    it('returns null inputData and outputData when query has no data', () => {
      mockUseQuery.mockReturnValue({ data: undefined, isLoading: false, error: null, refetch: mockRefetch })

      const { result } = renderHook(() => useStepExecutionDetailsWithDefaults(), {
        wrapper: makeWrapper(queryClient),
      })

      expect(result.current.inputData).toBeNull()
      expect(result.current.outputData).toBeNull()
    })

    it('returns inputData and outputData from the first activity in the response', () => {
      mockUseQuery.mockReturnValue({ data: mockActivityResponse, isLoading: false, error: null, refetch: mockRefetch })

      const { result } = renderHook(() => useStepExecutionDetailsWithDefaults(), {
        wrapper: makeWrapper(queryClient),
      })

      expect(result.current.inputData).toEqual({ host: '10.0.0.1', port: 8080 })
      expect(result.current.outputData).toEqual({ status: 'ok', result: 42 })
    })
  })

  describe('enabled flag', () => {
    it('is false when executionId is null', () => {
      renderHook(() => useStepExecutionDetailsWithDefaults({ executionId: null }), {
        wrapper: makeWrapper(queryClient),
      })

      // The fourth argument to useQuery carries the { enabled } option
      expect(mockUseQuery).toHaveBeenCalledWith(
        'get',
        '/executions/{execution_id}/activities',
        expect.anything(),
        expect.objectContaining({ enabled: false })
      )
    })

    it('is false when stepId is empty string', () => {
      renderHook(() => useStepExecutionDetailsWithDefaults({ stepId: '' }), { wrapper: makeWrapper(queryClient) })

      expect(mockUseQuery).toHaveBeenCalledWith(
        'get',
        '/executions/{execution_id}/activities',
        expect.anything(),
        expect.objectContaining({ enabled: false })
      )
    })

    it('is true when both stepId and executionId are provided', () => {
      renderHook(() => useStepExecutionDetailsWithDefaults(), { wrapper: makeWrapper(queryClient) })

      expect(mockUseQuery).toHaveBeenCalledWith(
        'get',
        '/executions/{execution_id}/activities',
        expect.anything(),
        expect.objectContaining({ enabled: true })
      )
    })
  })

  describe('refetch on activityStatus change', () => {
    it('is NOT called on mount', () => {
      renderHook(() => useStepExecutionDetailsWithDefaults({ activityStatus: 'running' }), {
        wrapper: makeWrapper(queryClient),
      })

      // The effect guards with prevStatusRef — no call on initial render
      expect(mockRefetch).not.toHaveBeenCalled()
    })

    it('is called when activityStatus changes from one value to another', () => {
      const { rerender } = renderHook(
        ({ status }: { status?: ActivityStatus }) => useStepExecutionDetailsWithDefaults({ activityStatus: status }),
        {
          initialProps: { status: 'running' as ActivityStatus | undefined },
          wrapper: makeWrapper(queryClient),
        }
      )

      expect(mockRefetch).not.toHaveBeenCalled()

      rerender({ status: 'completed' })

      expect(mockRefetch).toHaveBeenCalledTimes(1)
    })

    it('is NOT called when activityStatus stays the same', () => {
      const { rerender } = renderHook(
        ({ status }: { status?: ActivityStatus }) => useStepExecutionDetailsWithDefaults({ activityStatus: status }),
        {
          initialProps: { status: 'running' as ActivityStatus | undefined },
          wrapper: makeWrapper(queryClient),
        }
      )

      rerender({ status: 'running' })
      rerender({ status: 'running' })

      expect(mockRefetch).not.toHaveBeenCalled()
    })
  })

  it('queries the selected loop iteration record', () => {
    renderHook(() => useStepExecutionDetailsWithDefaults({ activityStatus: 'completed', iteration: 2 }), {
      wrapper: makeWrapper(queryClient),
    })

    expect(mockUseQuery).toHaveBeenCalledWith(
      'get',
      '/executions/{execution_id}/activities',
      expect.objectContaining({
        params: {
          path: { execution_id: 'exec-1' },
          query: { activity_name: 'my_activity#iter-2', limit: 1 },
        },
      }),
      expect.anything()
    )
  })

  it('does not duplicate an iteration suffix already present in the step ID', () => {
    renderHook(
      () =>
        useStepExecutionDetailsWithDefaults({
          stepId: 'my_activity#iter-2',
          activityStatus: 'completed',
          iteration: 2,
        }),
      {
        wrapper: makeWrapper(queryClient),
      }
    )

    expect(mockUseQuery).toHaveBeenCalledWith(
      'get',
      '/executions/{execution_id}/activities',
      expect.objectContaining({
        params: {
          path: { execution_id: 'exec-1' },
          query: { activity_name: 'my_activity#iter-2', limit: 1 },
        },
      }),
      expect.anything()
    )
  })

  it('uses fallbackOutputData when the activities response has no matching record', () => {
    mockUseQuery.mockReturnValue({
      data: { resources: [] },
      isLoading: false,
      error: null,
      refetch: mockRefetch,
    })

    const { result } = renderHook(
      () =>
        useStepExecutionDetailsWithDefaults({
          fallbackOutputData: { hostname: 'mock-server' },
        }),
      { wrapper: makeWrapper(queryClient) }
    )

    expect(result.current.outputData).toEqual({ hostname: 'mock-server' })
  })
})
