import { act, renderHook } from '@testing-library/react'
import type React from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { FlowNodeType } from '../../../constants'

import { useExecutionStepClick } from './useExecutionStepClick'

// Mock useExecutionApprovals
const mockHandleApprovalClick = vi.fn()
const mockClearApprovals = vi.fn()
const mockNavigateToIndex = vi.fn()
const mockSetApprovalsAndIndex = vi.fn()
const mockFetchApprovals = vi.fn()

vi.mock('./useExecutionApprovals', () => ({
  isWaitingApprovalNode: (node: { type?: string; data: Record<string, unknown> }) => {
    if (node.type !== FlowNodeType.APPROVAL) return false
    const executionState = node.data.__executionState as { status?: string } | undefined
    return executionState?.status === 'waiting'
  },
  useExecutionApprovals: () => ({
    approvals: [],
    currentIndex: 0,
    currentApproval: null,
    isLoading: false,
    handleNodeClick: mockHandleApprovalClick,
    navigateToIndex: mockNavigateToIndex,
    clearApprovals: mockClearApprovals,
    setApprovalsAndIndex: mockSetApprovalsAndIndex,
    fetchApprovals: mockFetchApprovals,
  }),
}))

const fakeEvent = {} as React.MouseEvent

function makeNode(
  id: string,
  status: string,
  overrides?: { type?: string; name?: string }
): { id: string; type?: string; data: Record<string, unknown> } {
  return {
    id,
    type: overrides?.type,
    data: {
      name: overrides?.name ?? id,
      __executionState: { status },
    },
  }
}

describe('useExecutionStepClick', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns null selectedStepId initially', () => {
    const { result } = renderHook(() => useExecutionStepClick('exec-1'))
    expect(result.current.selectedStepId).toBeNull()
    expect(result.current.selectedStepName).toBeNull()
  })

  it('delegates approval step clicks to useExecutionApprovals', () => {
    const { result } = renderHook(() => useExecutionStepClick('exec-1'))
    const approvalNode = makeNode('approval-1', 'waiting', { type: FlowNodeType.APPROVAL })

    act(() => {
      result.current.handleNodeClick(fakeEvent, approvalNode)
    })

    expect(mockHandleApprovalClick).toHaveBeenCalledWith(fakeEvent, approvalNode)
    // Should NOT set selectedStepId for approval steps
    expect(result.current.selectedStepId).toBeNull()
  })

  it('selects a completed step on click', () => {
    const { result } = renderHook(() => useExecutionStepClick('exec-1'))
    const node = makeNode('step-1', 'completed', { name: 'Run Script' })

    act(() => {
      result.current.handleNodeClick(fakeEvent, node)
    })

    expect(result.current.selectedStepId).toBe('step-1')
    expect(result.current.selectedStepName).toBe('Run Script')
  })

  it('selects a failed step on click', () => {
    const { result } = renderHook(() => useExecutionStepClick('exec-1'))
    const node = makeNode('step-2', 'failed', { name: 'Deploy' })

    act(() => {
      result.current.handleNodeClick(fakeEvent, node)
    })

    expect(result.current.selectedStepId).toBe('step-2')
    expect(result.current.selectedStepName).toBe('Deploy')
  })

  it('keeps selection when clicking the same step again', () => {
    const { result } = renderHook(() => useExecutionStepClick('exec-1'))
    const node = makeNode('step-1', 'completed', { name: 'Run Script' })

    act(() => {
      result.current.handleNodeClick(fakeEvent, node)
    })
    expect(result.current.selectedStepId).toBe('step-1')

    act(() => {
      result.current.handleNodeClick(fakeEvent, node)
    })
    expect(result.current.selectedStepId).toBe('step-1')
    expect(result.current.selectedStepName).toBe('Run Script')
  })

  it('switches selection when clicking a different step', () => {
    const { result } = renderHook(() => useExecutionStepClick('exec-1'))
    const node1 = makeNode('step-1', 'completed', { name: 'First' })
    const node2 = makeNode('step-2', 'completed', { name: 'Second' })

    act(() => {
      result.current.handleNodeClick(fakeEvent, node1)
    })
    expect(result.current.selectedStepId).toBe('step-1')

    act(() => {
      result.current.handleNodeClick(fakeEvent, node2)
    })
    expect(result.current.selectedStepId).toBe('step-2')
    expect(result.current.selectedStepName).toBe('Second')
  })

  it('ignores clicks on pending/running steps', () => {
    const { result } = renderHook(() => useExecutionStepClick('exec-1'))

    act(() => {
      result.current.handleNodeClick(fakeEvent, makeNode('step-1', 'pending'))
    })
    expect(result.current.selectedStepId).toBeNull()

    act(() => {
      result.current.handleNodeClick(fakeEvent, makeNode('step-2', 'running'))
    })
    expect(result.current.selectedStepId).toBeNull()
  })

  it('uses step id as name when data.name is not a string', () => {
    const { result } = renderHook(() => useExecutionStepClick('exec-1'))
    const node = {
      id: 'step-no-name',
      data: { __executionState: { status: 'completed' } },
    }

    act(() => {
      result.current.handleNodeClick(fakeEvent, node)
    })

    expect(result.current.selectedStepId).toBe('step-no-name')
    expect(result.current.selectedStepName).toBe('step-no-name')
  })

  it('deselectStep clears selectedStepId and selectedStepName', () => {
    const { result } = renderHook(() => useExecutionStepClick('exec-1'))
    const node = makeNode('step-1', 'completed', { name: 'Run Script' })

    act(() => {
      result.current.handleNodeClick(fakeEvent, node)
    })
    expect(result.current.selectedStepId).toBe('step-1')

    act(() => {
      result.current.deselectStep()
    })
    expect(result.current.selectedStepId).toBeNull()
    expect(result.current.selectedStepName).toBeNull()
  })

  it('exposes clearApprovals from useExecutionApprovals', () => {
    const { result } = renderHook(() => useExecutionStepClick('exec-1'))

    act(() => {
      result.current.clearApprovals()
    })

    expect(mockClearApprovals).toHaveBeenCalledOnce()
  })
})
