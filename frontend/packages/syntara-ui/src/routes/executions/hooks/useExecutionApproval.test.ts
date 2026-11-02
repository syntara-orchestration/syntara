import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { FlowNodeType } from '../../../constants'

import { isWaitingApprovalNode, useExecutionApproval } from './useExecutionApproval'

const mockFetchForStep = vi.fn()
const mockClear = vi.fn()

vi.mock('./useFetchApprovalForStep', () => ({
  useFetchApprovalForStep: () => ({
    fetchForStep: mockFetchForStep,
    clear: mockClear,
    approval: null,
    isLoading: false,
  }),
}))

const mockApproval = {
  id: 'approval-1',
  approval_node_id: 'node-abc',
  status: 'pending',
  name: 'Test Approval',
  execution_id: 'exec-1',
}

function makeMouseEvent(): React.MouseEvent {
  return {} as React.MouseEvent
}

function makeNode(overrides: Partial<{ id: string; type: string; data: Record<string, unknown> }> = {}) {
  return {
    id: 'node-abc',
    type: FlowNodeType.APPROVAL,
    data: { __executionState: { status: 'waiting' } },
    ...overrides,
  }
}

describe('isWaitingApprovalNode', () => {
  it('returns true for an approval node in waiting status', () => {
    expect(isWaitingApprovalNode(makeNode())).toBe(true)
  })

  it('returns false for a non-approval node', () => {
    expect(isWaitingApprovalNode(makeNode({ type: FlowNodeType.TASK }))).toBe(false)
  })

  it('returns false for an approval node not in waiting status', () => {
    expect(isWaitingApprovalNode(makeNode({ data: { __executionState: { status: 'completed' } } }))).toBe(false)
  })

  it('returns false when execution state is missing', () => {
    expect(isWaitingApprovalNode(makeNode({ data: {} }))).toBe(false)
  })
})

describe('useExecutionApproval', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockFetchForStep.mockResolvedValue(mockApproval)
  })

  it('returns null pendingApproval initially', () => {
    const { result } = renderHook(() => useExecutionApproval('exec-1'))

    expect(result.current.pendingApproval).toBeNull()
    expect(result.current.handleNodeClick).toBeDefined()
  })

  it('ignores clicks on non-approval nodes', () => {
    const { result } = renderHook(() => useExecutionApproval('exec-1'))

    result.current.handleNodeClick(makeMouseEvent(), makeNode({ type: FlowNodeType.TASK }))

    expect(mockFetchForStep).not.toHaveBeenCalled()
    expect(result.current.pendingApproval).toBeNull()
  })

  it('ignores clicks on approval nodes not in waiting status', () => {
    const { result } = renderHook(() => useExecutionApproval('exec-1'))

    result.current.handleNodeClick(makeMouseEvent(), makeNode({ data: { __executionState: { status: 'completed' } } }))

    expect(mockFetchForStep).not.toHaveBeenCalled()
    expect(result.current.pendingApproval).toBeNull()
  })

  it('fetches and sets pendingApproval on valid approval node click', async () => {
    const { result } = renderHook(() => useExecutionApproval('exec-1'))

    result.current.handleNodeClick(makeMouseEvent(), makeNode())

    await waitFor(() => {
      expect(mockFetchForStep).toHaveBeenCalledWith('node-abc')
      expect(result.current.pendingApproval).toEqual(mockApproval)
    })
  })

  it('does not set pendingApproval when fetch returns null', async () => {
    mockFetchForStep.mockResolvedValue(null)

    const { result } = renderHook(() => useExecutionApproval('exec-1'))

    result.current.handleNodeClick(makeMouseEvent(), makeNode())

    await waitFor(() => {
      expect(mockFetchForStep).toHaveBeenCalled()
    })

    expect(result.current.pendingApproval).toBeNull()
  })

  it('clears approval state when executionId changes', () => {
    const { rerender } = renderHook(({ execId }) => useExecutionApproval(execId), {
      initialProps: { execId: 'exec-1' },
    })

    rerender({ execId: 'exec-2' })

    expect(mockClear).toHaveBeenCalled()
  })

  it('clears pending approval when clearPendingApproval is called', async () => {
    const { result } = renderHook(() => useExecutionApproval('exec-1'))

    // Set a pending approval
    result.current.handleNodeClick(makeMouseEvent(), makeNode())

    await waitFor(() => {
      expect(result.current.pendingApproval).toEqual(mockApproval)
    })

    // Clear it
    act(() => {
      result.current.clearPendingApproval()
    })

    expect(result.current.pendingApproval).toBeNull()
    expect(mockClear).toHaveBeenCalled()
  })

  it('handles fetch rejection without throwing', async () => {
    mockFetchForStep.mockRejectedValue(new Error('Network error'))

    const { result } = renderHook(() => useExecutionApproval('exec-1'))

    result.current.handleNodeClick(makeMouseEvent(), makeNode())

    await waitFor(() => {
      expect(mockFetchForStep).toHaveBeenCalled()
    })

    expect(result.current.pendingApproval).toBeNull()
  })

  it('ignores clicks on approval nodes with no execution state', () => {
    const { result } = renderHook(() => useExecutionApproval('exec-1'))

    result.current.handleNodeClick(makeMouseEvent(), makeNode({ data: {} }))

    expect(mockFetchForStep).not.toHaveBeenCalled()
  })

  it('discards stale fetch when a different node is clicked before fetch resolves', async () => {
    const approvalB = { ...mockApproval, id: 'approval-2', approval_node_id: 'node-xyz' }
    let resolveFirst: (value: typeof mockApproval) => void
    mockFetchForStep
      .mockReturnValueOnce(
        new Promise<typeof mockApproval>((resolve) => {
          resolveFirst = resolve
        })
      )
      .mockResolvedValueOnce(approvalB)

    const { result } = renderHook(() => useExecutionApproval('exec-1'))

    // Click first node — fetch starts but hasn't resolved
    result.current.handleNodeClick(makeMouseEvent(), makeNode({ id: 'node-abc' }))

    // Quickly click a different node — second fetch resolves immediately
    result.current.handleNodeClick(makeMouseEvent(), makeNode({ id: 'node-xyz' }))

    await waitFor(() => {
      expect(result.current.pendingApproval).toEqual(approvalB)
    })

    // Now first fetch resolves with stale data
    resolveFirst!(mockApproval)

    // pendingApproval should stay as approvalB (from node-xyz), not revert to mockApproval
    await waitFor(() => {
      expect(mockFetchForStep).toHaveBeenCalledTimes(2)
    })
    expect(result.current.pendingApproval).toEqual(approvalB)
  })

  it('discards stale fetch result when executionId changes before fetch resolves', async () => {
    let resolveFetch: (value: typeof mockApproval) => void
    mockFetchForStep.mockReturnValue(
      new Promise<typeof mockApproval>((resolve) => {
        resolveFetch = resolve
      })
    )

    const { result, rerender } = renderHook(({ execId }) => useExecutionApproval(execId), {
      initialProps: { execId: 'exec-1' },
    })

    // Click approval node — fetch starts but hasn't resolved
    result.current.handleNodeClick(makeMouseEvent(), makeNode())
    expect(mockFetchForStep).toHaveBeenCalledWith('node-abc')

    // User navigates to a different execution before fetch resolves
    rerender({ execId: 'exec-2' })

    // Now the original fetch resolves with stale data
    resolveFetch!(mockApproval)

    await waitFor(() => {
      expect(mockFetchForStep).toHaveBeenCalled()
    })

    // pendingApproval should remain null — the result was for exec-1, not exec-2
    expect(result.current.pendingApproval).toBeNull()
  })
})
