import { act, renderHook } from '@testing-library/react'
import type React from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { FlowNodeType } from '../../../constants'

import { useExecutionNodeClick } from './useExecutionNodeClick'

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

describe('useExecutionNodeClick', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns null selectedNodeId initially', () => {
    const { result } = renderHook(() => useExecutionNodeClick('exec-1'))
    expect(result.current.selectedNodeId).toBeNull()
    expect(result.current.selectedNodeName).toBeNull()
  })

  it('delegates approval node clicks to useExecutionApprovals', () => {
    const { result } = renderHook(() => useExecutionNodeClick('exec-1'))
    const approvalNode = makeNode('approval-1', 'waiting', { type: FlowNodeType.APPROVAL })

    act(() => {
      result.current.handleNodeClick(fakeEvent, approvalNode)
    })

    expect(mockHandleApprovalClick).toHaveBeenCalledWith(fakeEvent, approvalNode)
    // Should NOT set selectedNodeId for approval nodes
    expect(result.current.selectedNodeId).toBeNull()
  })

  it('selects a completed node on click', () => {
    const { result } = renderHook(() => useExecutionNodeClick('exec-1'))
    const node = makeNode('step-1', 'completed', { name: 'Run Script' })

    act(() => {
      result.current.handleNodeClick(fakeEvent, node)
    })

    expect(result.current.selectedNodeId).toBe('step-1')
    expect(result.current.selectedNodeName).toBe('Run Script')
  })

  it('selects a failed node on click', () => {
    const { result } = renderHook(() => useExecutionNodeClick('exec-1'))
    const node = makeNode('step-2', 'failed', { name: 'Deploy' })

    act(() => {
      result.current.handleNodeClick(fakeEvent, node)
    })

    expect(result.current.selectedNodeId).toBe('step-2')
    expect(result.current.selectedNodeName).toBe('Deploy')
  })

  it('keeps selection when clicking the same node again', () => {
    const { result } = renderHook(() => useExecutionNodeClick('exec-1'))
    const node = makeNode('step-1', 'completed', { name: 'Run Script' })

    act(() => {
      result.current.handleNodeClick(fakeEvent, node)
    })
    expect(result.current.selectedNodeId).toBe('step-1')

    act(() => {
      result.current.handleNodeClick(fakeEvent, node)
    })
    expect(result.current.selectedNodeId).toBe('step-1')
    expect(result.current.selectedNodeName).toBe('Run Script')
  })

  it('switches selection when clicking a different node', () => {
    const { result } = renderHook(() => useExecutionNodeClick('exec-1'))
    const node1 = makeNode('step-1', 'completed', { name: 'First' })
    const node2 = makeNode('step-2', 'completed', { name: 'Second' })

    act(() => {
      result.current.handleNodeClick(fakeEvent, node1)
    })
    expect(result.current.selectedNodeId).toBe('step-1')

    act(() => {
      result.current.handleNodeClick(fakeEvent, node2)
    })
    expect(result.current.selectedNodeId).toBe('step-2')
    expect(result.current.selectedNodeName).toBe('Second')
  })

  it('ignores clicks on pending/running nodes', () => {
    const { result } = renderHook(() => useExecutionNodeClick('exec-1'))

    act(() => {
      result.current.handleNodeClick(fakeEvent, makeNode('step-1', 'pending'))
    })
    expect(result.current.selectedNodeId).toBeNull()

    act(() => {
      result.current.handleNodeClick(fakeEvent, makeNode('step-2', 'running'))
    })
    expect(result.current.selectedNodeId).toBeNull()
  })

  it('uses node id as name when data.name is not a string', () => {
    const { result } = renderHook(() => useExecutionNodeClick('exec-1'))
    const node = {
      id: 'step-no-name',
      data: { __executionState: { status: 'completed' } },
    }

    act(() => {
      result.current.handleNodeClick(fakeEvent, node)
    })

    expect(result.current.selectedNodeId).toBe('step-no-name')
    expect(result.current.selectedNodeName).toBe('step-no-name')
  })

  it('deselectNode clears selectedNodeId and selectedNodeName', () => {
    const { result } = renderHook(() => useExecutionNodeClick('exec-1'))
    const node = makeNode('step-1', 'completed', { name: 'Run Script' })

    act(() => {
      result.current.handleNodeClick(fakeEvent, node)
    })
    expect(result.current.selectedNodeId).toBe('step-1')

    act(() => {
      result.current.deselectNode()
    })
    expect(result.current.selectedNodeId).toBeNull()
    expect(result.current.selectedNodeName).toBeNull()
  })

  it('exposes clearApprovals from useExecutionApprovals', () => {
    const { result } = renderHook(() => useExecutionNodeClick('exec-1'))

    act(() => {
      result.current.clearApprovals()
    })

    expect(mockClearApprovals).toHaveBeenCalledOnce()
  })

  it('selectNode sets both selected id and display name', () => {
    const { result } = renderHook(() => useExecutionNodeClick('exec-1'))

    act(() => {
      result.current.selectNode('activity-42', 'Deploy service')
    })

    expect(result.current.selectedNodeId).toBe('activity-42')
    expect(result.current.selectedNodeName).toBe('Deploy service')
  })

  it('uses definitionId as the selected activity id when present', () => {
    const { result } = renderHook(() => useExecutionNodeClick('exec-1'))
    const node = {
      id: 'react-flow-node-1',
      data: {
        name: 'Run Script',
        definitionId: 'run_script',
        __executionState: { status: 'completed' },
      },
    }

    act(() => {
      result.current.handleNodeClick(fakeEvent, node)
    })

    expect(result.current.selectedNodeId).toBe('run_script')
    expect(result.current.selectedNodeName).toBe('Run Script')
  })

  it('ignores clicks when __executionState is not an object', () => {
    const { result } = renderHook(() => useExecutionNodeClick('exec-1'))
    const node = {
      id: 'step-1',
      data: {
        name: 'Broken state',
        __executionState: 'completed',
      },
    }

    act(() => {
      result.current.handleNodeClick(fakeEvent, node)
    })

    expect(result.current.selectedNodeId).toBeNull()
  })
})
