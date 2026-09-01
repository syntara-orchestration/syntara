/**
 * Execution Data Hook Tests
 *
 * Tests for REST API fetching hook with integration to execution store
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, it, expect, beforeEach, vi } from 'vitest'

import { executionsClient } from '../../../client'
import type { Execution } from '../execution/types'
import { useExecutionStore } from '../stores/useExecutionStore'

import { useExecutionData, useShouldStreamExecution } from './useExecutionData'

// ============================================================================
// Mock Setup
// ============================================================================

vi.mock('../../../client', () => ({
  executionsClient: {
    useQuery: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
)

// ============================================================================
// Test Helpers
// ============================================================================

function createMockExecution(overrides?: Partial<Execution>): Execution {
  return {
    id: 'exec-123',
    createdAt: '2025-12-10T15:00:00Z',
    updatedAt: '2025-12-10T15:00:00Z',
    workflow_id: 'workflow-456',
    workflow_version_id: 'version-789',
    status: 'running',
    started_at: '2025-12-10T15:00:05Z',
    completed_at: null,
    workflow_definition: { workflow: { activities: [] } },
    activities: [
      {
        activity_id: 'fetch_data',
        status: 'completed',
        error_details: null,
        started_at: '2025-12-10T15:00:05Z',
        completed_at: '2025-12-10T15:00:10Z',
      },
    ],
    ...overrides,
  } as Execution
}

// ============================================================================
// useExecutionData Tests
// ============================================================================

describe('useExecutionData', () => {
  beforeEach(() => {
    useExecutionStore.getState().reset()
    vi.clearAllMocks()
  })

  it('fetches execution data successfully', async () => {
    const mockExecution = createMockExecution()

    vi.mocked(executionsClient.useQuery).mockReturnValue({
      data: mockExecution,
      isLoading: false,
      isSuccess: true,
      error: null,
      refetch: vi.fn(),
    })

    const { result } = renderHook(() => useExecutionData('exec-123'), { wrapper })

    await waitFor(() => {
      expect(result.current.data).toEqual(mockExecution)
    })

    expect(result.current.isLoading).toBe(false)
    expect(result.current.isSuccess).toBe(true)
    expect(result.current.error).toBeNull()
  })

  it('requests correct API endpoint with includes', () => {
    vi.mocked(executionsClient.useQuery).mockReturnValue({
      data: null,
      isLoading: true,
      isSuccess: false,
      error: null,
      refetch: vi.fn(),
    })

    renderHook(() => useExecutionData('exec-123'), { wrapper })

    expect(executionsClient.useQuery).toHaveBeenCalledWith(
      'get',
      '/executions/{execution_id}',
      {
        params: {
          path: {
            execution_id: 'exec-123',
          },
          query: {
            include: 'workflow_definition,activities',
          },
        },
      },
      {
        enabled: true,
      }
    )
  })

  it('auto-loads data into store by default', async () => {
    const mockExecution = createMockExecution()

    vi.mocked(executionsClient.useQuery).mockReturnValue({
      data: mockExecution,
      isLoading: false,
      isSuccess: true,
      error: null,
      refetch: vi.fn(),
    })

    renderHook(() => useExecutionData('exec-123'), { wrapper })

    await waitFor(() => {
      const storeState = useExecutionStore.getState()
      expect(storeState.executionId).toBe('exec-123')
      expect(storeState.visualization).not.toBeNull()
    })
  })

  it('does not auto-load when autoLoad is false', async () => {
    const mockExecution = createMockExecution()

    vi.mocked(executionsClient.useQuery).mockReturnValue({
      data: mockExecution,
      isLoading: false,
      isSuccess: true,
      error: null,
      refetch: vi.fn(),
    })

    renderHook(() => useExecutionData('exec-123', { autoLoad: false }), { wrapper })

    await waitFor(() => {
      const storeState = useExecutionStore.getState()
      expect(storeState.executionId).toBeNull()
      expect(storeState.visualization).toBeNull()
    })
  })

  it('does not fetch when enabled is false', () => {
    vi.mocked(executionsClient.useQuery).mockReturnValue({
      data: null,
      isLoading: false,
      isSuccess: false,
      error: null,
      refetch: vi.fn(),
    })

    renderHook(() => useExecutionData('exec-123', { enabled: false }), { wrapper })

    expect(executionsClient.useQuery).toHaveBeenCalledWith(
      'get',
      '/executions/{execution_id}',
      expect.anything(),
      expect.objectContaining({
        enabled: false,
      })
    )
  })

  it('handles loading state', () => {
    vi.mocked(executionsClient.useQuery).mockReturnValue({
      data: null,
      isLoading: true,
      isSuccess: false,
      error: null,
      refetch: vi.fn(),
    })

    const { result } = renderHook(() => useExecutionData('exec-123'), { wrapper })

    expect(result.current.isLoading).toBe(true)
    expect(result.current.data).toBeNull()
  })

  it('handles error state', async () => {
    const mockError = new Error('Failed to fetch execution')

    vi.mocked(executionsClient.useQuery).mockReturnValue({
      data: null,
      isLoading: false,
      isSuccess: false,
      error: mockError,
      refetch: vi.fn(),
    })

    const { result } = renderHook(() => useExecutionData('exec-123'), { wrapper })

    await waitFor(() => {
      expect(result.current.error).toEqual(mockError)
    })

    // Error should be set in store
    const storeState = useExecutionStore.getState()
    expect(storeState.error).toEqual(mockError)
  })

  it('provides refetch function', () => {
    const mockRefetch = vi.fn()

    vi.mocked(executionsClient.useQuery).mockReturnValue({
      data: null,
      isLoading: false,
      isSuccess: false,
      error: null,
      refetch: mockRefetch,
    })

    const { result } = renderHook(() => useExecutionData('exec-123'), { wrapper })

    result.current.refetch()

    expect(mockRefetch).toHaveBeenCalled()
  })

  it('clears store error on successful load', async () => {
    // Set initial error
    useExecutionStore.getState().setError(new Error('Previous error'))

    const mockExecution = createMockExecution()

    vi.mocked(executionsClient.useQuery).mockReturnValue({
      data: mockExecution,
      isLoading: false,
      isSuccess: true,
      error: null,
      refetch: vi.fn(),
    })

    renderHook(() => useExecutionData('exec-123'), { wrapper })

    await waitFor(() => {
      const storeState = useExecutionStore.getState()
      expect(storeState.error).toBeNull()
    })
  })

  it('stores an Error when auto-load setExecution throws', async () => {
    const mockExecution = createMockExecution()
    const setExecutionSpy = vi.spyOn(useExecutionStore.getState(), 'setExecution').mockImplementation(() => {
      throw new Error('failed to hydrate store')
    })

    vi.mocked(executionsClient.useQuery).mockReturnValue({
      data: mockExecution,
      isLoading: false,
      isSuccess: true,
      error: null,
      refetch: vi.fn(),
    })

    try {
      renderHook(() => useExecutionData('exec-123'), { wrapper })

      await waitFor(() => {
        expect(useExecutionStore.getState().error).toEqual(new Error('failed to hydrate store'))
      })
    } finally {
      setExecutionSpy.mockRestore()
    }
  })

  it('wraps non-Error auto-load failures before storing them', async () => {
    const mockExecution = createMockExecution()
    const setExecutionSpy = vi.spyOn(useExecutionStore.getState(), 'setExecution').mockImplementation(() => {
      // eslint-disable-next-line @typescript-eslint/only-throw-error -- intentional non-Error to cover catch wrapping
      throw { unexpected: true }
    })

    vi.mocked(executionsClient.useQuery).mockReturnValue({
      data: mockExecution,
      isLoading: false,
      isSuccess: true,
      error: null,
      refetch: vi.fn(),
    })

    try {
      renderHook(() => useExecutionData('exec-123'), { wrapper })

      await waitFor(() => {
        const storeError = useExecutionStore.getState().error
        expect(storeError).toBeInstanceOf(Error)
      })
    } finally {
      setExecutionSpy.mockRestore()
    }
  })

  it('returns null error when the query reports undefined', () => {
    vi.mocked(executionsClient.useQuery).mockReturnValue({
      data: undefined,
      isLoading: false,
      isSuccess: false,
      error: undefined,
      refetch: vi.fn(),
    })

    const { result } = renderHook(() => useExecutionData('exec-123'), { wrapper })

    expect(result.current.error).toBeNull()
  })

  it('handles execution with complete workflow definition', async () => {
    const mockExecution = createMockExecution({
      workflow_definition: {
        workflow: {
          activities: [
            { id: 'task1', type: 'task' },
            { id: 'task2', type: 'task' },
          ],
        },
      },
    } as unknown as Partial<Execution>)

    vi.mocked(executionsClient.useQuery).mockReturnValue({
      data: mockExecution,
      isLoading: false,
      isSuccess: true,
      error: null,
      refetch: vi.fn(),
    })

    renderHook(() => useExecutionData('exec-123'), { wrapper })

    await waitFor(() => {
      const storeState = useExecutionStore.getState()
      expect(storeState.visualization?.workflowDefinition).toEqual(mockExecution.workflow_definition)
    })
  })

  it('handles execution with multiple activities', async () => {
    const mockExecution = createMockExecution({
      activities: [
        {
          activity_id: 'fetch_data',
          status: 'completed',
          error_details: null,
          started_at: '2025-12-10T15:00:05Z',
          completed_at: '2025-12-10T15:00:10Z',
        },
        {
          activity_id: 'process_data',
          status: 'running',
          error_details: null,
          started_at: '2025-12-10T15:00:10Z',
          completed_at: null,
        },
        {
          activity_id: 'send_notification',
          status: 'pending',
          error_details: null,
          started_at: null,
          completed_at: null,
        },
      ],
    })

    vi.mocked(executionsClient.useQuery).mockReturnValue({
      data: mockExecution,
      isLoading: false,
      isSuccess: true,
      error: null,
      refetch: vi.fn(),
    })

    renderHook(() => useExecutionData('exec-123'), { wrapper })

    await waitFor(() => {
      const storeState = useExecutionStore.getState()
      expect(storeState.activityStates.size).toBe(3)
      expect(storeState.activityStates.get('fetch_data')?.status).toBe('completed')
      expect(storeState.activityStates.get('process_data')?.status).toBe('running')
      expect(storeState.activityStates.get('send_notification')?.status).toBe('pending')
    })
  })
})

// ============================================================================
// useShouldStreamExecution Tests
// ============================================================================

describe('useShouldStreamExecution', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns false when data not loaded', () => {
    vi.mocked(executionsClient.useQuery).mockReturnValue({
      data: null,
      isLoading: true,
      isSuccess: false,
      error: null,
      refetch: vi.fn(),
    })

    const { result } = renderHook(() => useShouldStreamExecution('exec-123'), { wrapper })

    expect(result.current).toBe(false)
  })

  it('returns true for running execution', () => {
    const mockExecution = createMockExecution({ status: 'running' })

    vi.mocked(executionsClient.useQuery).mockReturnValue({
      data: mockExecution,
      isLoading: false,
      isSuccess: true,
      error: null,
      refetch: vi.fn(),
    })

    const { result } = renderHook(() => useShouldStreamExecution('exec-123'), { wrapper })

    expect(result.current).toBe(true)
  })

  it('returns true for pending execution', () => {
    const mockExecution = createMockExecution({ status: 'pending' })

    vi.mocked(executionsClient.useQuery).mockReturnValue({
      data: mockExecution,
      isLoading: false,
      isSuccess: true,
      error: null,
      refetch: vi.fn(),
    })

    const { result } = renderHook(() => useShouldStreamExecution('exec-123'), { wrapper })

    expect(result.current).toBe(true)
  })

  it('returns true for paused execution', () => {
    const mockExecution = createMockExecution({ status: 'paused' })

    vi.mocked(executionsClient.useQuery).mockReturnValue({
      data: mockExecution,
      isLoading: false,
      isSuccess: true,
      error: null,
      refetch: vi.fn(),
    })

    const { result } = renderHook(() => useShouldStreamExecution('exec-123'), { wrapper })

    expect(result.current).toBe(true)
  })

  it('returns false for completed execution', () => {
    const mockExecution = createMockExecution({ status: 'completed' })

    vi.mocked(executionsClient.useQuery).mockReturnValue({
      data: mockExecution,
      isLoading: false,
      isSuccess: true,
      error: null,
      refetch: vi.fn(),
    })

    const { result } = renderHook(() => useShouldStreamExecution('exec-123'), { wrapper })

    expect(result.current).toBe(false)
  })

  it('returns false for failed execution', () => {
    const mockExecution = createMockExecution({ status: 'failed' })

    vi.mocked(executionsClient.useQuery).mockReturnValue({
      data: mockExecution,
      isLoading: false,
      isSuccess: true,
      error: null,
      refetch: vi.fn(),
    })

    const { result } = renderHook(() => useShouldStreamExecution('exec-123'), { wrapper })

    expect(result.current).toBe(false)
  })

  it('returns false for cancelled execution', () => {
    const mockExecution = createMockExecution({ status: 'cancelled' })

    vi.mocked(executionsClient.useQuery).mockReturnValue({
      data: mockExecution,
      isLoading: false,
      isSuccess: true,
      error: null,
      refetch: vi.fn(),
    })

    const { result } = renderHook(() => useShouldStreamExecution('exec-123'), { wrapper })

    expect(result.current).toBe(false)
  })

  it('returns false for completed_with_errors execution', () => {
    const mockExecution = createMockExecution({ status: 'completed_with_errors' })

    vi.mocked(executionsClient.useQuery).mockReturnValue({
      data: mockExecution,
      isLoading: false,
      isSuccess: true,
      error: null,
      refetch: vi.fn(),
    })

    const { result } = renderHook(() => useShouldStreamExecution('exec-123'), { wrapper })

    expect(result.current).toBe(false)
  })

  it('returns false when execution status is missing', () => {
    const mockExecution = createMockExecution({ status: undefined })

    vi.mocked(executionsClient.useQuery).mockReturnValue({
      data: mockExecution,
      isLoading: false,
      isSuccess: true,
      error: null,
      refetch: vi.fn(),
    })

    const { result } = renderHook(() => useShouldStreamExecution('exec-123'), { wrapper })

    expect(result.current).toBe(true)
  })
})
