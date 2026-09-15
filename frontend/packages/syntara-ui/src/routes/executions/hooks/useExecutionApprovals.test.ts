import type { Approval } from '@syntara/contracts'
import { renderHook, act, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { FlowNodeType } from '../../../constants'
import { ACTIVITY_STATUS } from '../../builder/utils/executionState/executionHelpers'

import type { ExecutionNode } from './useExecutionApprovals'
import { isWaitingApprovalNode, useExecutionApprovals } from './useExecutionApprovals'

// Mock dependencies
vi.mock('./useFetchPendingApprovals', () => ({
  useFetchPendingApprovals: vi.fn(),
}))

vi.mock('../../../providers/alerts', () => ({
  useAlerts: vi.fn(() => ({
    showInfo: vi.fn(),
    showError: vi.fn(),
  })),
}))

const mockApproval: Approval = {
  id: 'approval-1',
  project_id: 'test-project-1',
  approval_node_id: 'node-1',
  name: 'Test Approval',
  status: 'pending',
  execution_id: 'exec-1',
  created_at: '2026-01-01T00:00:00Z',
  next_step_approved: { id: 'step-a', name: 'Approved Step', type: 'task' },
  workflow_context: {
    workflow_id: 'wfv-1',
    workflow_name: 'Test Workflow',
    inputs: {},
  },
}

describe('isWaitingApprovalNode', () => {
  it('returns true for approval node with waiting status', () => {
    const node: ExecutionNode = {
      id: 'node-1',
      type: FlowNodeType.APPROVAL,
      data: {
        __executionState: { status: ACTIVITY_STATUS.WAITING },
      },
    }

    expect(isWaitingApprovalNode(node)).toBe(true)
  })

  it('returns false for non-approval node', () => {
    const node: ExecutionNode = {
      id: 'node-1',
      type: FlowNodeType.TASK,
      data: {
        __executionState: { status: ACTIVITY_STATUS.WAITING },
      },
    }

    expect(isWaitingApprovalNode(node)).toBe(false)
  })

  it('returns false for approval node without waiting status', () => {
    const node: ExecutionNode = {
      id: 'node-1',
      type: FlowNodeType.APPROVAL,
      data: {
        __executionState: { status: ACTIVITY_STATUS.COMPLETED },
      },
    }

    expect(isWaitingApprovalNode(node)).toBe(false)
  })

  it('returns false when execution state is missing', () => {
    const node: ExecutionNode = {
      id: 'node-1',
      type: FlowNodeType.APPROVAL,
      data: {},
    }

    expect(isWaitingApprovalNode(node)).toBe(false)
  })
})

describe('useExecutionApprovals', () => {
  beforeEach(async () => {
    const { useFetchPendingApprovals } = await import('./useFetchPendingApprovals')
    vi.mocked(useFetchPendingApprovals).mockReturnValue({
      isLoading: false,
      fetchApprovals: vi.fn(),
      clear: vi.fn(),
    })
  })

  it('initializes with empty approvals', async () => {
    const { result } = renderHook(() => useExecutionApprovals('exec-1'))

    await waitFor(() => {
      expect(result.current.approvals).toEqual([])
      expect(result.current.currentIndex).toBe(0)
      expect(result.current.currentApproval).toBeNull()
    })
  })

  it('setApprovalsAndIndex updates state', () => {
    const { result } = renderHook(() => useExecutionApprovals('exec-1'))

    act(() => {
      result.current.setApprovalsAndIndex([mockApproval], 0)
    })

    expect(result.current.approvals).toEqual([mockApproval])
    expect(result.current.currentApproval).toEqual(mockApproval)
  })

  it('setApprovalsAndIndex clamps out-of-bounds index', () => {
    const { result } = renderHook(() => useExecutionApprovals('exec-1'))

    act(() => {
      result.current.setApprovalsAndIndex([mockApproval], 10)
    })

    expect(result.current.approvals).toEqual([mockApproval])
    // Index 10 is beyond array length 1, clamped to last valid index (0)
    expect(result.current.currentIndex).toBe(0)
    expect(result.current.currentApproval).toEqual(mockApproval)
  })

  it('navigateToIndex clamps to valid range', () => {
    const { result } = renderHook(() => useExecutionApprovals('exec-1'))

    act(() => {
      result.current.setApprovalsAndIndex([mockApproval], 0)
    })

    act(() => {
      result.current.navigateToIndex(5) // Beyond range
    })

    expect(result.current.currentIndex).toBe(0) // Clamped to last index
  })

  it('clearApprovals resets state', () => {
    const { result } = renderHook(() => useExecutionApprovals('exec-1'))

    act(() => {
      result.current.setApprovalsAndIndex([mockApproval], 0)
    })

    act(() => {
      result.current.clearApprovals()
    })

    expect(result.current.approvals).toEqual([])
    expect(result.current.currentIndex).toBe(0)
    expect(result.current.currentApproval).toBeNull()
  })

  it('resets state when executionId changes', () => {
    const { result, rerender } = renderHook(({ id }) => useExecutionApprovals(id), {
      initialProps: { id: 'exec-1' },
    })

    act(() => {
      result.current.setApprovalsAndIndex([mockApproval], 0)
    })

    rerender({ id: 'exec-2' })

    expect(result.current.approvals).toEqual([])
    expect(result.current.currentIndex).toBe(0)
  })

  it('handleNodeClick ignores non-waiting approval nodes', () => {
    const { result } = renderHook(() => useExecutionApprovals('exec-1'))

    const node: ExecutionNode = {
      id: 'node-1',
      type: FlowNodeType.TASK,
      data: {},
    }

    act(() => {
      result.current.handleNodeClick({} as React.MouseEvent, node)
    })

    // Node is not a waiting approval node, so no action should occur
    expect(result.current.approvals).toEqual([])
  })

  it('currentApproval is computed from approvals and currentIndex', () => {
    const { result } = renderHook(() => useExecutionApprovals('exec-1'))

    act(() => {
      result.current.setApprovalsAndIndex([mockApproval], 0)
    })

    expect(result.current.currentApproval).toBe(mockApproval)

    act(() => {
      result.current.navigateToIndex(5) // Out of bounds - clamps to last index
    })

    // Should clamp to last valid index (0 in this case)
    expect(result.current.currentApproval).toBe(mockApproval)
    expect(result.current.currentIndex).toBe(0)
  })

  it('navigateToIndex with negative index clamps to 0', () => {
    const { result } = renderHook(() => useExecutionApprovals('exec-1'))

    act(() => {
      result.current.setApprovalsAndIndex([mockApproval], 0)
    })

    act(() => {
      result.current.navigateToIndex(-1)
    })

    expect(result.current.currentIndex).toBe(0)
  })

  it('shows error notification when approval fetch fails on node click', async () => {
    const mockShowError = vi.fn()
    const mockFetchApprovals = vi.fn().mockRejectedValue(new Error('Network error'))

    const { useAlerts } = await import('../../../providers/alerts')
    vi.mocked(useAlerts).mockReturnValue({
      showInfo: vi.fn(),
      showError: mockShowError,
      showAlert: vi.fn(),
      showSuccess: vi.fn(),
      showWarning: vi.fn(),
      dismissAlert: vi.fn(),
      clearAllAlerts: vi.fn(),
    })

    const { useFetchPendingApprovals } = await import('./useFetchPendingApprovals')
    vi.mocked(useFetchPendingApprovals).mockReturnValue({
      isLoading: false,
      fetchApprovals: mockFetchApprovals,
      clear: vi.fn(),
    })

    const { result } = renderHook(() => useExecutionApprovals('exec-1'))

    const node: ExecutionNode = {
      id: 'node-1',
      type: FlowNodeType.APPROVAL,
      data: {
        __executionState: { status: ACTIVITY_STATUS.WAITING },
      },
    }

    act(() => {
      result.current.handleNodeClick({} as React.MouseEvent, node)
    })

    await waitFor(() => {
      expect(mockShowError).toHaveBeenCalledWith({
        title: 'Failed to load approval',
        description: 'Network error',
      })
    })
  })

  it('handleNodeClick sets approvals and index on successful fetch', async () => {
    const mockFetchApprovals = vi.fn().mockResolvedValue([mockApproval])

    const { useFetchPendingApprovals } = await import('./useFetchPendingApprovals')
    vi.mocked(useFetchPendingApprovals).mockReturnValue({
      isLoading: false,
      fetchApprovals: mockFetchApprovals,
      clear: vi.fn(),
    })

    const { result } = renderHook(() => useExecutionApprovals('exec-1'))

    const node: ExecutionNode = {
      id: 'node-1',
      type: FlowNodeType.APPROVAL,
      data: {
        __executionState: { status: ACTIVITY_STATUS.WAITING },
      },
    }

    act(() => {
      result.current.handleNodeClick({} as React.MouseEvent, node)
    })

    await waitFor(() => {
      expect(result.current.approvals).toEqual([mockApproval])
      expect(result.current.currentIndex).toBe(0)
      expect(result.current.currentApproval).toEqual(mockApproval)
    })
  })

  it('handleNodeClick matches a loop-iteration approval_node_id to the canvas node', async () => {
    const loopApproval = { ...mockApproval, approval_node_id: 'node-1_iter_0' }
    const mockFetchApprovals = vi.fn().mockResolvedValue([loopApproval])

    const { useFetchPendingApprovals } = await import('./useFetchPendingApprovals')
    vi.mocked(useFetchPendingApprovals).mockReturnValue({
      isLoading: false,
      fetchApprovals: mockFetchApprovals,
      clear: vi.fn(),
    })

    const { result } = renderHook(() => useExecutionApprovals('exec-1'))

    const node: ExecutionNode = {
      id: 'node-1',
      type: FlowNodeType.APPROVAL,
      data: {
        __executionState: { status: ACTIVITY_STATUS.WAITING },
      },
    }

    act(() => {
      result.current.handleNodeClick({} as React.MouseEvent, node)
    })

    await waitFor(() => {
      expect(result.current.currentApproval).toEqual(loopApproval)
    })
  })

  it('handleNodeClick shows info when approval is no longer pending', async () => {
    const mockShowInfo = vi.fn()
    const mockFetchApprovals = vi.fn().mockResolvedValue([mockApproval])

    const { useAlerts } = await import('../../../providers/alerts')
    vi.mocked(useAlerts).mockReturnValue({
      showInfo: mockShowInfo,
      showError: vi.fn(),
      showAlert: vi.fn(),
      showSuccess: vi.fn(),
      showWarning: vi.fn(),
      dismissAlert: vi.fn(),
      clearAllAlerts: vi.fn(),
    })

    const { useFetchPendingApprovals } = await import('./useFetchPendingApprovals')
    vi.mocked(useFetchPendingApprovals).mockReturnValue({
      isLoading: false,
      fetchApprovals: mockFetchApprovals,
      clear: vi.fn(),
    })

    const { result } = renderHook(() => useExecutionApprovals('exec-1'))

    // Click a node whose ID does NOT match any approval_node_id in the response
    const node: ExecutionNode = {
      id: 'node-not-in-response',
      type: FlowNodeType.APPROVAL,
      data: {
        __executionState: { status: ACTIVITY_STATUS.WAITING },
      },
    }

    act(() => {
      result.current.handleNodeClick({} as React.MouseEvent, node)
    })

    await waitFor(() => {
      expect(mockShowInfo).toHaveBeenCalledWith({
        title: 'Approval no longer pending',
        description: 'This approval has been resolved or is no longer available.',
      })
    })
  })

  it('resets error dedup after a successful fetch', async () => {
    const mockShowError = vi.fn()
    let callCount = 0
    const mockFetchApprovals = vi.fn().mockImplementation(() => {
      callCount++
      if (callCount <= 1) return Promise.reject(new Error('Network error'))
      return Promise.resolve([mockApproval])
    })

    const { useAlerts } = await import('../../../providers/alerts')
    vi.mocked(useAlerts).mockReturnValue({
      showInfo: vi.fn(),
      showError: mockShowError,
      showAlert: vi.fn(),
      showSuccess: vi.fn(),
      showWarning: vi.fn(),
      dismissAlert: vi.fn(),
      clearAllAlerts: vi.fn(),
    })

    const { useFetchPendingApprovals } = await import('./useFetchPendingApprovals')
    vi.mocked(useFetchPendingApprovals).mockReturnValue({
      isLoading: false,
      fetchApprovals: mockFetchApprovals,
      clear: vi.fn(),
    })

    const { result } = renderHook(() => useExecutionApprovals('exec-1'))

    const node: ExecutionNode = {
      id: 'node-1',
      type: FlowNodeType.APPROVAL,
      data: {
        __executionState: { status: ACTIVITY_STATUS.WAITING },
      },
    }

    // First click fails
    act(() => {
      result.current.handleNodeClick({} as React.MouseEvent, node)
    })

    await waitFor(() => {
      expect(mockShowError).toHaveBeenCalledTimes(1)
    })

    // Second click succeeds (resets dedup key)
    act(() => {
      result.current.handleNodeClick({} as React.MouseEvent, node)
    })

    await waitFor(() => {
      expect(result.current.approvals).toEqual([mockApproval])
    })

    // Third click fails again — should show toast since dedup was reset
    mockFetchApprovals.mockRejectedValue(new Error('Network error'))
    act(() => {
      result.current.handleNodeClick({} as React.MouseEvent, node)
    })

    await waitFor(() => {
      expect(mockShowError).toHaveBeenCalledTimes(2)
    })
  })

  it('suppresses error toast when executionId changes before failed fetch settles', async () => {
    let rejectFetch: (error: Error) => void = () => {}
    const mockShowError = vi.fn()
    const mockFetchApprovals = vi.fn().mockImplementation(
      () =>
        new Promise<Approval[]>((_resolve, reject) => {
          rejectFetch = reject
        })
    )

    const { useAlerts } = await import('../../../providers/alerts')
    vi.mocked(useAlerts).mockReturnValue({
      showInfo: vi.fn(),
      showError: mockShowError,
      showAlert: vi.fn(),
      showSuccess: vi.fn(),
      showWarning: vi.fn(),
      dismissAlert: vi.fn(),
      clearAllAlerts: vi.fn(),
    })

    const { useFetchPendingApprovals } = await import('./useFetchPendingApprovals')
    vi.mocked(useFetchPendingApprovals).mockReturnValue({
      isLoading: false,
      fetchApprovals: mockFetchApprovals,
      clear: vi.fn(),
    })

    const { result, rerender } = renderHook(({ id }) => useExecutionApprovals(id), {
      initialProps: { id: 'exec-1' },
    })

    const node: ExecutionNode = {
      id: 'node-1',
      type: FlowNodeType.APPROVAL,
      data: {
        __executionState: { status: ACTIVITY_STATUS.WAITING },
      },
    }

    // Start the fetch
    act(() => {
      result.current.handleNodeClick({} as React.MouseEvent, node)
    })

    // Change executionId before the fetch settles
    rerender({ id: 'exec-2' })

    // Now reject the fetch — the guard should suppress the toast
    await act(async () => {
      rejectFetch(new Error('Network error'))
      await Promise.resolve()
    })

    expect(mockShowError).not.toHaveBeenCalled()
  })

  it('suppresses error toast when a different node is clicked before failed fetch settles', async () => {
    const rejectFns: Array<(error: Error) => void> = []
    const mockShowError = vi.fn()
    const mockFetchApprovals = vi.fn().mockImplementation(
      () =>
        new Promise<Approval[]>((_resolve, reject) => {
          rejectFns.push(reject)
        })
    )

    const { useAlerts } = await import('../../../providers/alerts')
    vi.mocked(useAlerts).mockReturnValue({
      showInfo: vi.fn(),
      showError: mockShowError,
      showAlert: vi.fn(),
      showSuccess: vi.fn(),
      showWarning: vi.fn(),
      dismissAlert: vi.fn(),
      clearAllAlerts: vi.fn(),
    })

    const { useFetchPendingApprovals } = await import('./useFetchPendingApprovals')
    vi.mocked(useFetchPendingApprovals).mockReturnValue({
      isLoading: false,
      fetchApprovals: mockFetchApprovals,
      clear: vi.fn(),
    })

    const { result } = renderHook(() => useExecutionApprovals('exec-1'))

    const node1: ExecutionNode = {
      id: 'node-1',
      type: FlowNodeType.APPROVAL,
      data: {
        __executionState: { status: ACTIVITY_STATUS.WAITING },
      },
    }

    const node2: ExecutionNode = {
      id: 'node-2',
      type: FlowNodeType.APPROVAL,
      data: {
        __executionState: { status: ACTIVITY_STATUS.WAITING },
      },
    }

    // Start a fetch for node-1
    act(() => {
      result.current.handleNodeClick({} as React.MouseEvent, node1)
    })

    // Click a different node before the first fetch settles
    // This updates latestNodeIdRef to 'node-2'
    act(() => {
      result.current.handleNodeClick({} as React.MouseEvent, node2)
    })

    // Reject the FIRST fetch — guard sees latestNodeIdRef is 'node-2', not 'node-1'
    await act(async () => {
      rejectFns[0](new Error('Network error'))
      await Promise.resolve()
    })

    expect(mockShowError).not.toHaveBeenCalled()
  })

  it('resets error dedup when executionId changes', async () => {
    const mockShowError = vi.fn()
    const mockFetchApprovals = vi.fn().mockRejectedValue(new Error('Network error'))

    const { useAlerts } = await import('../../../providers/alerts')
    vi.mocked(useAlerts).mockReturnValue({
      showInfo: vi.fn(),
      showError: mockShowError,
      showAlert: vi.fn(),
      showSuccess: vi.fn(),
      showWarning: vi.fn(),
      dismissAlert: vi.fn(),
      clearAllAlerts: vi.fn(),
    })

    const { useFetchPendingApprovals } = await import('./useFetchPendingApprovals')
    vi.mocked(useFetchPendingApprovals).mockReturnValue({
      isLoading: false,
      fetchApprovals: mockFetchApprovals,
      clear: vi.fn(),
    })

    const { result, rerender } = renderHook(({ id }) => useExecutionApprovals(id), {
      initialProps: { id: 'exec-1' },
    })

    const node: ExecutionNode = {
      id: 'node-1',
      type: FlowNodeType.APPROVAL,
      data: {
        __executionState: { status: ACTIVITY_STATUS.WAITING },
      },
    }

    // Fail on exec-1
    act(() => {
      result.current.handleNodeClick({} as React.MouseEvent, node)
    })

    await waitFor(() => {
      expect(mockShowError).toHaveBeenCalledTimes(1)
    })

    // Switch to exec-2 — should reset the dedup ref
    rerender({ id: 'exec-2' })

    // Same error on exec-2 should NOT be suppressed
    act(() => {
      result.current.handleNodeClick({} as React.MouseEvent, node)
    })

    await waitFor(() => {
      expect(mockShowError).toHaveBeenCalledTimes(2)
    })
  })

  it('deduplicates identical error toasts on repeated failed clicks', async () => {
    const mockShowError = vi.fn()
    const mockFetchApprovals = vi.fn().mockRejectedValue(new Error('Network error'))

    const { useAlerts } = await import('../../../providers/alerts')
    vi.mocked(useAlerts).mockReturnValue({
      showInfo: vi.fn(),
      showError: mockShowError,
      showAlert: vi.fn(),
      showSuccess: vi.fn(),
      showWarning: vi.fn(),
      dismissAlert: vi.fn(),
      clearAllAlerts: vi.fn(),
    })

    const { useFetchPendingApprovals } = await import('./useFetchPendingApprovals')
    vi.mocked(useFetchPendingApprovals).mockReturnValue({
      isLoading: false,
      fetchApprovals: mockFetchApprovals,
      clear: vi.fn(),
    })

    const { result } = renderHook(() => useExecutionApprovals('exec-1'))

    const node: ExecutionNode = {
      id: 'node-1',
      type: FlowNodeType.APPROVAL,
      data: {
        __executionState: { status: ACTIVITY_STATUS.WAITING },
      },
    }

    // Click twice with the same error
    act(() => {
      result.current.handleNodeClick({} as React.MouseEvent, node)
    })

    await waitFor(() => {
      expect(mockShowError).toHaveBeenCalledTimes(1)
    })

    act(() => {
      result.current.handleNodeClick({} as React.MouseEvent, node)
    })

    await waitFor(() => {
      // Should still be 1 -- dedup prevents the duplicate toast
      expect(mockShowError).toHaveBeenCalledTimes(1)
    })
  })
})
