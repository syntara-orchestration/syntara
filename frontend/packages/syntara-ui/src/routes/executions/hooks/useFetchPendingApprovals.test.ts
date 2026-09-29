import type { Approval } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { approvalsClient } from '../../../client'

import { useFetchPendingApprovals } from './useFetchPendingApprovals'

vi.mock('../../../client', () => ({
  approvalsClient: {
    useQuery: vi.fn(),
  },
}))

const mockApprovals: Approval[] = [
  {
    id: 'approval-1',
    project_id: 'test-project-1',
    name: 'Approval 1',
    status: 'pending',
    approval_node_id: 'node-1',
    execution_id: 'exec-1',
    created_at: '2024-01-01T00:00:00Z',
    next_step_approved: { id: 'step-1', name: 'Next Step 1', type: 'step' },
    workflow_context: { workflow_id: 'wf-1', workflow_name: 'Workflow 1', inputs: {} },
  },
  {
    id: 'approval-2',
    project_id: 'test-project-1',
    name: 'Approval 2',
    status: 'pending',
    approval_node_id: 'node-2',
    execution_id: 'exec-1',
    created_at: '2024-01-01T00:01:00Z',
    next_step_approved: { id: 'step-2', name: 'Next Step 2', type: 'step' },
    workflow_context: { workflow_id: 'wf-1', workflow_name: 'Workflow 1', inputs: {} },
  },
  {
    id: 'approval-3',
    project_id: 'test-project-1',
    name: 'Approval 3',
    status: 'pending',
    approval_node_id: 'node-3',
    execution_id: 'exec-1',
    created_at: '2024-01-01T00:02:00Z',
    next_step_approved: { id: 'step-3', name: 'Next Step 3', type: 'step' },
    workflow_context: { workflow_id: 'wf-1', workflow_name: 'Workflow 1', inputs: {} },
  },
]

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

describe('useFetchPendingApprovals', () => {
  let mockRefetch: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.clearAllMocks()
    mockRefetch = vi.fn()

    vi.mocked(approvalsClient.useQuery).mockReturnValue({
      refetch: mockRefetch,
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
    })
  })

  it('initializes with not loading', () => {
    const { result } = renderHook(() => useFetchPendingApprovals('exec-1'), {
      wrapper: createWrapper(),
    })

    expect(result.current.isLoading).toBe(false)
  })

  it('fetches approvals and returns them', async () => {
    mockRefetch.mockResolvedValue({
      data: { resources: mockApprovals },
    })

    const { result } = renderHook(() => useFetchPendingApprovals('exec-1'), {
      wrapper: createWrapper(),
    })

    let fetchedApprovals: Approval[] = []
    await act(async () => {
      fetchedApprovals = await result.current.fetchApprovals()
    })

    expect(fetchedApprovals).toEqual(mockApprovals)
    expect(mockRefetch).toHaveBeenCalledTimes(1)
  })

  it('handles fetch errors gracefully', async () => {
    mockRefetch.mockRejectedValue(new Error('Network error'))

    const { result } = renderHook(() => useFetchPendingApprovals('exec-1'), {
      wrapper: createWrapper(),
    })

    await act(async () => {
      await expect(result.current.fetchApprovals()).rejects.toThrow('Network error')
    })
  })

  it('handles empty response', async () => {
    mockRefetch.mockResolvedValue({
      data: { resources: [] },
    })

    const { result } = renderHook(() => useFetchPendingApprovals('exec-1'), {
      wrapper: createWrapper(),
    })

    let fetchedApprovals: Approval[] = []
    await act(async () => {
      fetchedApprovals = await result.current.fetchApprovals()
    })

    expect(fetchedApprovals).toEqual([])
  })

  it('handles undefined data in response', async () => {
    mockRefetch.mockResolvedValue({
      data: undefined,
    })

    const { result } = renderHook(() => useFetchPendingApprovals('exec-1'), {
      wrapper: createWrapper(),
    })

    let fetchedApprovals: Approval[] = []
    await act(async () => {
      fetchedApprovals = await result.current.fetchApprovals()
    })

    expect(fetchedApprovals).toEqual([])
  })

  it('returns approvals that can be used for finding index by node ID', async () => {
    mockRefetch.mockResolvedValue({
      data: { resources: mockApprovals },
    })

    const { result } = renderHook(() => useFetchPendingApprovals('exec-1'), {
      wrapper: createWrapper(),
    })

    let approvals: Approval[] = []
    await act(async () => {
      approvals = await result.current.fetchApprovals()
    })

    expect(approvals.findIndex((a) => a.approval_node_id === 'node-1')).toBe(0)
    expect(approvals.findIndex((a) => a.approval_node_id === 'node-2')).toBe(1)
    expect(approvals.findIndex((a) => a.approval_node_id === 'node-3')).toBe(2)
    expect(approvals.findIndex((a) => a.approval_node_id === 'non-existent')).toBe(-1)
  })

  it('provides a clear function to reset loading state', () => {
    const { result } = renderHook(() => useFetchPendingApprovals('exec-1'), {
      wrapper: createWrapper(),
    })

    expect(result.current.clear).toBeTypeOf('function')

    act(() => {
      result.current.clear()
    })

    expect(result.current.isLoading).toBe(false)
  })

  it('queries with correct execution_id parameter', () => {
    renderHook(() => useFetchPendingApprovals('exec-123'), {
      wrapper: createWrapper(),
    })

    expect(approvalsClient.useQuery).toHaveBeenCalledWith('get', '/approvals', {
      params: {
        query: {
          execution_id: 'exec-123',
          status: 'pending',
        },
      },
      enabled: false,
    })
  })

  it('uses enabled: false to prevent automatic fetching', () => {
    renderHook(() => useFetchPendingApprovals('exec-1'), {
      wrapper: createWrapper(),
    })

    expect(approvalsClient.useQuery).toHaveBeenCalledWith(
      expect.anything(),
      expect.anything(),
      expect.objectContaining({
        enabled: false,
      })
    )
  })

  it('returns empty array without fetching when executionId is empty', async () => {
    const { result } = renderHook(() => useFetchPendingApprovals(''), {
      wrapper: createWrapper(),
    })

    let fetchedApprovals: unknown
    await act(async () => {
      fetchedApprovals = await result.current.fetchApprovals()
    })

    expect(fetchedApprovals).toEqual([])
    expect(mockRefetch).not.toHaveBeenCalled()
    expect(result.current.isLoading).toBe(false)
  })
})
