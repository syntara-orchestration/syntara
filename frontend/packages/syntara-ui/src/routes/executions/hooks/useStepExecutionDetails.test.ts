import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { createElement } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ActivityStatus } from '../../workflows/execution/types'

import { useStepExecutionDetails } from './useStepExecutionDetails'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

type MockQueryResult = {
  data: unknown
  isLoading: boolean
  isSuccess: boolean
  error: unknown
  refetch: ReturnType<typeof vi.fn>
}
type MockQueryOptions = { enabled?: boolean; select?: (data: unknown) => unknown }
type MockUseQuery = (method: string, path: string, params: unknown, options: MockQueryOptions) => MockQueryResult

const mockUseQuery = vi.fn<MockUseQuery>()
let mockQueryResult: MockQueryResult

const { mockIsShikiReady, mockPreloadShiki, mockLoadShikiService, mockService } = vi.hoisted(() => {
  const mockIsShikiReady = vi.fn<() => boolean>()
  const mockPreloadShiki = vi.fn<() => Promise<void>>()
  const mockService = { isShikiReady: mockIsShikiReady, preloadShiki: mockPreloadShiki }
  return {
    mockIsShikiReady,
    mockPreloadShiki,
    mockLoadShikiService: vi.fn<() => Promise<typeof mockService>>(),
    mockService,
  }
})

vi.mock('../../../components/details/shiki-service-loader', () => ({
  getLoadedShikiService: () => mockService,
  loadShikiService: mockLoadShikiService,
}))

vi.mock('../../../client', () => ({
  executionsClient: {
    useQuery: (method: string, path: string, params: unknown, options: MockQueryOptions) =>
      mockUseQuery(method, path, params, options),
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
  mockQueryResult = { data: undefined, isLoading: false, isSuccess: false, error: null, refetch: mockRefetch }
  mockUseQuery.mockImplementation((_method, _path, _params, options) => ({
    ...mockQueryResult,
    data:
      mockQueryResult.data === undefined || !options.select
        ? mockQueryResult.data
        : options.select(mockQueryResult.data),
  }))
  mockIsShikiReady.mockReturnValue(true)
  mockPreloadShiki.mockResolvedValue(undefined)
  mockLoadShikiService.mockResolvedValue(mockService)
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useStepExecutionDetails', () => {
  describe('return values — data mapping', () => {
    it('returns null inputData and outputData when query has no data', () => {
      mockQueryResult = { data: undefined, isLoading: false, isSuccess: false, error: null, refetch: mockRefetch }

      const { result } = renderHook(() => useStepExecutionDetails('my_activity', 'exec-1'), {
        wrapper: makeWrapper(queryClient),
      })

      expect(result.current.inputData).toBeNull()
      expect(result.current.outputData).toBeNull()
    })

    it('returns inputData and outputData from the first activity in the response', () => {
      mockQueryResult = {
        data: mockActivityResponse,
        isLoading: false,
        isSuccess: true,
        error: null,
        refetch: mockRefetch,
      }

      const { result } = renderHook(() => useStepExecutionDetails('my_activity', 'exec-1'), {
        wrapper: makeWrapper(queryClient),
      })

      expect(result.current.inputData).toEqual({ host: '10.0.0.1', port: 8080 })
      expect(result.current.outputData).toEqual({ status: 'ok', result: 42 })
    })
  })

  describe('enabled flag', () => {
    it('is false when executionId is null', () => {
      renderHook(() => useStepExecutionDetails('my_activity', null), { wrapper: makeWrapper(queryClient) })

      // The fourth argument to useQuery carries the { enabled } option
      expect(mockUseQuery).toHaveBeenCalledWith(
        'get',
        '/executions/{execution_id}/activities',
        expect.anything(),
        expect.objectContaining({ enabled: false })
      )
    })

    it('is false when stepId is empty string', () => {
      renderHook(() => useStepExecutionDetails('', 'exec-1'), { wrapper: makeWrapper(queryClient) })

      expect(mockUseQuery).toHaveBeenCalledWith(
        'get',
        '/executions/{execution_id}/activities',
        expect.anything(),
        expect.objectContaining({ enabled: false })
      )
    })

    it('is true when both stepId and executionId are provided', () => {
      renderHook(() => useStepExecutionDetails('my_activity', 'exec-1'), { wrapper: makeWrapper(queryClient) })

      expect(mockUseQuery).toHaveBeenCalledWith(
        'get',
        '/executions/{execution_id}/activities',
        expect.anything(),
        expect.objectContaining({ enabled: true })
      )
    })
  })

  describe('Shiki readiness', () => {
    it('keeps selected activity data hidden until Shiki preload settles', async () => {
      let finishPreload: (() => void) | undefined
      const preloadPromise = new Promise<void>((resolve) => {
        finishPreload = resolve
      })
      mockIsShikiReady.mockReturnValue(false)
      mockPreloadShiki.mockReturnValue(preloadPromise)
      mockQueryResult = {
        data: mockActivityResponse,
        isLoading: false,
        isSuccess: true,
        error: null,
        refetch: mockRefetch,
      }

      const { result } = renderHook(() => useNodeExecutionDetails('my_activity', 'exec-1'), {
        wrapper: makeWrapper(queryClient),
      })

      expect(result.current.isLoading).toBe(true)
      expect(result.current.inputData).toBeNull()
      expect(mockUseQuery.mock.calls[0]?.[3].select?.(mockActivityResponse)).toBeUndefined()
      await waitFor(() => expect(mockPreloadShiki).toHaveBeenCalledOnce())

      await act(async () => {
        finishPreload?.()
        await preloadPromise
      })

      await waitFor(() => expect(result.current.isLoading).toBe(false))
      expect(result.current.inputData).toEqual({ host: '10.0.0.1', port: 8080 })
      expect(result.current.outputData).toEqual({ status: 'ok', result: 42 })
      expect(mockUseQuery.mock.calls.at(-1)?.[3].select?.(mockActivityResponse)).toEqual(mockActivityResponse)
    })

    it('releases activity data if Shiki preload fails', async () => {
      mockIsShikiReady.mockReturnValue(false)
      mockPreloadShiki.mockRejectedValue(new Error('Shiki initialization failed'))
      mockQueryResult = {
        data: mockActivityResponse,
        isLoading: false,
        isSuccess: true,
        error: null,
        refetch: mockRefetch,
      }

      const { result } = renderHook(() => useNodeExecutionDetails('my_activity', 'exec-1'), {
        wrapper: makeWrapper(queryClient),
      })

      await waitFor(() => expect(result.current.isLoading).toBe(false))
      expect(result.current.inputData).toEqual({ host: '10.0.0.1', port: 8080 })
    })
  })

  describe('refetch on activityStatus change', () => {
    it('is NOT called on mount', () => {
      renderHook(() => useStepExecutionDetails('my_activity', 'exec-1', 'running'), {
        wrapper: makeWrapper(queryClient),
      })

      // The effect guards with prevStatusRef — no call on initial render
      expect(mockRefetch).not.toHaveBeenCalled()
    })

    it('is called when activityStatus changes from one value to another', () => {
      const { rerender } = renderHook(
        ({ status }: { status?: ActivityStatus }) => useStepExecutionDetails('my_activity', 'exec-1', status),
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
        ({ status }: { status?: ActivityStatus }) => useStepExecutionDetails('my_activity', 'exec-1', status),
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
})
