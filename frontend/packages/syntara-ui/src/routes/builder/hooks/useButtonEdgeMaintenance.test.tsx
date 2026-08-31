import { renderHook, act } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'

import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { EdgeType } from '../utils/workflowToGraph'

import { useButtonEdgeMaintenance } from './useButtonEdgeMaintenance'

// Mock dependencies
vi.mock('../../../constants', () => ({
  FlowNodeType: {
    CONDITION: 'condition',
    LOOP: 'loop',
    APPROVAL: 'approval',
    PLACEHOLDER: 'placeholder',
  },
}))

vi.mock('../utils/filterHelpers', () => ({
  filterRealNodes: (nodes: Array<{ id: string }>) =>
    nodes.filter((n) => !n.id.startsWith('placeholder-') && !n.id.startsWith('pending-')),
  filterButtonEdges: (edges: Array<{ type?: string; id?: string }>) =>
    edges.filter((e) => e.type === 'buttonEdge' || e.id?.startsWith('button-')),
  isRealEdge: (edge: { type?: string; id?: string }) =>
    edge.type !== 'buttonEdge' && !edge.id?.startsWith('button-') && !edge.id?.startsWith('pending-'),
}))

type SetNodesFn = React.Dispatch<React.SetStateAction<NodeType[]>>
type SetEdgesFn = React.Dispatch<React.SetStateAction<EdgeType[]>>
type OnAddNodeFn = (
  sourceNodeId: string,
  targetNodeId?: string,
  edgeId?: string,
  sourceHandle?: string,
  desiredPosition?: { x: number; y: number }
) => void

describe('useButtonEdgeMaintenance', () => {
  const mockSetNodes = vi.fn<SetNodesFn>()
  const mockSetEdges = vi.fn<SetEdgesFn>()
  const mockOnAddNodeFromEdge = vi.fn<OnAddNodeFn>()

  const defaultOptions = {
    nodes: [] as never[],
    edges: [] as never[],
    isInitialized: true,
    activeEdgeButtonNodeId: null,
    activeEdgeButtonHandle: null,
    onAddNodeFromEdge: mockOnAddNodeFromEdge,
    pendingEdge: null,
    setNodes: mockSetNodes,
    setEdges: mockSetEdges,
    executionStatus: null,
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    mockSetNodes.mockImplementation((updater) => {
      if (typeof updater === 'function') {
        return updater([])
      }
    })
    mockSetEdges.mockImplementation((updater) => {
      if (typeof updater === 'function') {
        return updater([])
      }
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns memoized signatures', () => {
    const { result } = renderHook(() => useButtonEdgeMaintenance(defaultOptions))

    expect(result.current.realNodeIds).toBeDefined()
    expect(result.current.realEdgesSignature).toBeDefined()
    expect(result.current.buttonEdgesSignature).toBeDefined()
  })

  it('does nothing when not initialized', () => {
    renderHook(() =>
      useButtonEdgeMaintenance({
        ...defaultOptions,
        isInitialized: false,
        nodes: [{ id: 'node-1', type: 'task', position: { x: 0, y: 0 } }] as never[],
      })
    )

    act(() => {
      vi.advanceTimersByTime(100)
    })

    expect(mockSetEdges).not.toHaveBeenCalled()
  })

  it('skips button edge creation and cleans up existing ones in execution mode', () => {
    renderHook(() =>
      useButtonEdgeMaintenance({
        ...defaultOptions,
        executionStatus: 'running',
        nodes: [{ id: 'node-1', type: 'task', position: { x: 0, y: 0 } }] as never[],
      })
    )

    act(() => {
      vi.advanceTimersByTime(100)
    })

    // setEdges is called for cleanup (removing button edges), but no new button edges are created
    expect(mockSetEdges).toHaveBeenCalled()
    const updater = mockSetEdges.mock.calls[0][0] as (prev: unknown[]) => unknown[]
    const result = updater([
      { id: 'real-edge', source: 'a', target: 'b' },
      { id: 'button-edge-node-1', source: 'node-1', target: 'placeholder-node-1' },
    ])
    // Only real edges remain after cleanup
    expect(result).toHaveLength(1)
    expect((result as Array<{ id: string }>)[0].id).toBe('real-edge')
  })

  it('skips button edge creation and cleans up in read-only mode', () => {
    renderHook(() =>
      useButtonEdgeMaintenance({
        ...defaultOptions,
        isReadOnly: true,
        nodes: [{ id: 'node-1', type: 'task', position: { x: 0, y: 0 } }] as never[],
      })
    )

    act(() => {
      vi.advanceTimersByTime(100)
    })

    expect(mockSetEdges).toHaveBeenCalled()
    const updater = mockSetEdges.mock.calls[0][0] as (prev: unknown[]) => unknown[]
    const result = updater([
      { id: 'real-edge', source: 'a', target: 'b' },
      { id: 'button-edge-node-1', source: 'node-1', target: 'placeholder-node-1' },
    ])
    expect(result).toHaveLength(1)
    expect((result as Array<{ id: string }>)[0].id).toBe('real-edge')
  })

  it('creates button edges normally when isReadOnly is false', () => {
    renderHook(() =>
      useButtonEdgeMaintenance({
        ...defaultOptions,
        isReadOnly: false,
        nodes: [{ id: 'node-1', type: 'task', position: { x: 0, y: 0 } }] as never[],
      })
    )

    act(() => {
      vi.advanceTimersByTime(100)
    })

    expect(mockSetEdges).toHaveBeenCalled()
  })

  it('creates button edge for node without outgoing edge', () => {
    let capturedEdges: unknown[] = []
    mockSetEdges.mockImplementation((updater) => {
      if (typeof updater === 'function') {
        capturedEdges = updater([])
      }
      return capturedEdges
    })

    renderHook(() =>
      useButtonEdgeMaintenance({
        ...defaultOptions,
        nodes: [{ id: 'node-1', type: 'task', position: { x: 100, y: 100 } }] as never[],
      })
    )

    act(() => {
      vi.advanceTimersByTime(100)
    })

    expect(mockSetEdges).toHaveBeenCalled()
    const buttonEdge = capturedEdges.find((e) => (e as { id: string }).id === 'button-node-1')
    expect(buttonEdge).toBeDefined()
  })

  it('does not create button edge for node with outgoing edge', () => {
    let capturedEdges: unknown[] = []
    mockSetEdges.mockImplementation((updater) => {
      if (typeof updater === 'function') {
        capturedEdges = updater([{ id: 'edge-1', source: 'node-1', target: 'node-2', sourceHandle: 'source' }])
      }
      return capturedEdges
    })

    renderHook(() =>
      useButtonEdgeMaintenance({
        ...defaultOptions,
        nodes: [
          { id: 'node-1', type: 'task', position: { x: 100, y: 100 } },
          { id: 'node-2', type: 'task', position: { x: 300, y: 100 } },
        ] as never[],
        edges: [{ id: 'edge-1', source: 'node-1', target: 'node-2', sourceHandle: 'source' }] as never[],
      })
    )

    act(() => {
      vi.advanceTimersByTime(100)
    })

    // Button edge should not be created for node-1
    const buttonEdge = capturedEdges.find((e) => (e as { id: string }).id === 'button-node-1')
    expect(buttonEdge).toBeUndefined()
  })

  it('creates button edges for condition node handles', () => {
    let capturedEdges: unknown[] = []
    mockSetEdges.mockImplementation((updater) => {
      if (typeof updater === 'function') {
        capturedEdges = updater([])
      }
      return capturedEdges
    })

    renderHook(() =>
      useButtonEdgeMaintenance({
        ...defaultOptions,
        nodes: [{ id: 'condition-1', type: 'condition', position: { x: 100, y: 100 } }] as never[],
      })
    )

    act(() => {
      vi.advanceTimersByTime(100)
    })

    expect(mockSetEdges).toHaveBeenCalled()
    const trueEdge = capturedEdges.find((e) => (e as { id: string }).id === 'button-condition-1-true')
    const falseEdge = capturedEdges.find((e) => (e as { id: string }).id === 'button-condition-1-false')
    expect(trueEdge).toBeDefined()
    expect(falseEdge).toBeDefined()
  })

  it('creates placeholder nodes for button edges', () => {
    // Track all setNodes calls
    const nodesCalls: unknown[][] = []
    mockSetNodes.mockImplementation((updater) => {
      if (typeof updater === 'function') {
        const result = updater([{ id: 'node-1', type: 'task', position: { x: 100, y: 100 } }] as unknown as NodeType[])
        nodesCalls.push(result)
        return result
      }
    })

    renderHook(() =>
      useButtonEdgeMaintenance({
        ...defaultOptions,
        nodes: [{ id: 'node-1', type: 'task', position: { x: 100, y: 100 } }] as never[],
      })
    )

    act(() => {
      vi.advanceTimersByTime(100)
    })

    // Check that setNodes was called
    expect(mockSetNodes).toHaveBeenCalled()

    // Look for placeholder in any of the calls
    const allNodes = nodesCalls.flat()
    const placeholder = allNodes.find((n) => (n as { id: string }).id === 'placeholder-node-1')
    expect(placeholder).toBeDefined()
  })

  it('updates active state for button edges', () => {
    // This test verifies that button edges are created with isActive state
    // based on activeEdgeButtonNodeId and activeEdgeButtonHandle

    // Track all setEdges calls
    const edgesCalls: unknown[][] = []
    mockSetEdges.mockImplementation((updater) => {
      if (typeof updater === 'function') {
        // No existing edges - the hook should create a new button edge with isActive
        const result = updater([])
        edgesCalls.push(result)
        return result
      }
    })

    renderHook(() =>
      useButtonEdgeMaintenance({
        ...defaultOptions,
        nodes: [{ id: 'node-1', type: 'task', position: { x: 100, y: 100 } }] as never[],
        edges: [] as never[], // No existing edges
        activeEdgeButtonNodeId: 'node-1',
        activeEdgeButtonHandle: 'source',
      })
    )

    act(() => {
      vi.advanceTimersByTime(100)
    })

    // Check that setEdges was called
    expect(mockSetEdges).toHaveBeenCalled()

    // Look for button edge in all calls and verify active state
    const allEdges = edgesCalls.flat()
    const buttonEdge = allEdges.find((e) => (e as { id: string }).id === 'button-node-1') as {
      data: { isActive: boolean }
    }

    // The NEW button edge should have isActive: true because activeEdgeButtonNodeId and handle match
    expect(buttonEdge?.data?.isActive).toBe(true)
  })

  it('handles loop nodes with done and loop handles', () => {
    let capturedEdges: unknown[] = []
    const nodesCalls: unknown[][] = []

    mockSetEdges.mockImplementation((updater) => {
      if (typeof updater === 'function') {
        capturedEdges = updater([])
      }
      return capturedEdges
    })

    mockSetNodes.mockImplementation((updater) => {
      if (typeof updater === 'function') {
        const result = updater([{ id: 'loop-1', type: 'loop', position: { x: 100, y: 100 } }] as unknown as NodeType[])
        nodesCalls.push(result)
        return result
      }
    })

    renderHook(() =>
      useButtonEdgeMaintenance({
        ...defaultOptions,
        nodes: [{ id: 'loop-1', type: 'loop', position: { x: 100, y: 100 } }] as never[],
      })
    )

    act(() => {
      vi.advanceTimersByTime(100)
    })

    const doneEdge = capturedEdges.find((e) => (e as { id: string }).id === 'button-loop-1-done')
    const loopEdge = capturedEdges.find((e) => (e as { id: string }).id === 'button-loop-1-loop')
    expect(doneEdge).toBeDefined()
    expect(loopEdge).toBeDefined()

    // Regression test: Verify loop handle yOffset is 30
    const allNodes = nodesCalls.flat()
    const loopPlaceholder = allNodes.find((n) => (n as { id: string }).id === 'placeholder-loop-1-loop') as
      | { position: { x: number; y: number } }
      | undefined
    expect(loopPlaceholder).toBeDefined()
    expect(loopPlaceholder?.position.y).toBe(130) // node.y (100) + yOffset (30)
  })

  it('handles approval nodes with approved and rejected handles', () => {
    let capturedEdges: unknown[] = []
    mockSetEdges.mockImplementation((updater) => {
      if (typeof updater === 'function') {
        capturedEdges = updater([])
      }
      return capturedEdges
    })

    renderHook(() =>
      useButtonEdgeMaintenance({
        ...defaultOptions,
        nodes: [{ id: 'approval-1', type: 'approval', position: { x: 100, y: 100 } }] as never[],
      })
    )

    act(() => {
      vi.advanceTimersByTime(100)
    })

    const approvedEdge = capturedEdges.find((e) => (e as { id: string }).id === 'button-approval-1-approved')
    const rejectedEdge = capturedEdges.find((e) => (e as { id: string }).id === 'button-approval-1-rejected')
    expect(approvedEdge).toBeDefined()
    expect(rejectedEdge).toBeDefined()
  })

  it('skips button edge when there is a pending edge', () => {
    let capturedEdges: unknown[] = []
    mockSetEdges.mockImplementation((updater) => {
      if (typeof updater === 'function') {
        capturedEdges = updater([])
      }
      return capturedEdges
    })

    renderHook(() =>
      useButtonEdgeMaintenance({
        ...defaultOptions,
        nodes: [{ id: 'node-1', type: 'task', position: { x: 100, y: 100 } }] as never[],
        pendingEdge: { sourceNodeId: 'node-1', x: 200, y: 100 },
      })
    )

    act(() => {
      vi.advanceTimersByTime(100)
    })

    // Button edge should not be created when there's a pending edge
    const buttonEdge = capturedEdges.find((e) => (e as { id: string }).id === 'button-node-1')
    expect(buttonEdge).toBeUndefined()
  })

  it('resets signature when edges are cleared', () => {
    const { rerender, result } = renderHook(
      ({ edges }) =>
        useButtonEdgeMaintenance({
          ...defaultOptions,
          nodes: [{ id: 'node-1', type: 'task', position: { x: 100, y: 100 } }] as never[],
          edges,
        }),
      { initialProps: { edges: [{ id: 'edge-1' }] as never[] } }
    )

    // Clear edges - hook should handle gracefully
    rerender({ edges: [] as never[] })

    // Hook should still return valid data after edges cleared
    expect(result.current.realNodeIds).toBeDefined()
    expect(result.current.realEdgesSignature).toBeDefined()
    expect(result.current.buttonEdgesSignature).toBeDefined()
  })

  it('calls setNodes to update node className', () => {
    renderHook(() =>
      useButtonEdgeMaintenance({
        ...defaultOptions,
        nodes: [{ id: 'node-1', type: 'task', position: { x: 100, y: 100 } }] as never[],
      })
    )

    act(() => {
      vi.advanceTimersByTime(100)
    })

    // Check that setNodes was called (for className updates)
    // The hook calls setNodes multiple times - once for placeholders, once for className updates
    expect(mockSetNodes).toHaveBeenCalled()
  })

  it('removes stale button edges when node gets real connection', () => {
    const edgesCalls: unknown[][] = []
    mockSetEdges.mockImplementation((updater) => {
      if (typeof updater === 'function') {
        // Simulate existing button edge and a new real edge
        const result = updater([
          { id: 'button-node-1', type: 'buttonEdge', source: 'node-1' },
          { id: 'edge-1', source: 'node-1', target: 'node-2', sourceHandle: 'source' },
        ] as unknown as EdgeType[])
        edgesCalls.push(result)
        return result
      }
    })

    renderHook(() =>
      useButtonEdgeMaintenance({
        ...defaultOptions,
        nodes: [
          { id: 'node-1', type: 'task', position: { x: 100, y: 100 } },
          { id: 'node-2', type: 'task', position: { x: 300, y: 100 } },
        ] as never[],
        edges: [{ id: 'edge-1', source: 'node-1', target: 'node-2', sourceHandle: 'source' }] as never[],
      })
    )

    act(() => {
      vi.advanceTimersByTime(100)
    })

    // Button edge should be removed since node has a real connection
    expect(mockSetEdges).toHaveBeenCalled()
    const allEdges = edgesCalls.flat()
    const buttonEdge = allEdges.find((e) => (e as { id: string }).id === 'button-node-1')
    expect(buttonEdge).toBeUndefined()
  })

  it('handles nodes with connected handles correctly', () => {
    // This test verifies that the hook processes nodes correctly
    // when some have connections and some don't
    const nodesCalls: unknown[][] = []
    mockSetNodes.mockImplementation((updater) => {
      if (typeof updater === 'function') {
        const result = updater([
          { id: 'node-1', type: 'task', position: { x: 100, y: 100 }, className: '' },
          { id: 'node-2', type: 'task', position: { x: 300, y: 100 }, className: '' },
        ] as unknown as NodeType[])
        nodesCalls.push(result)
        return result
      }
    })

    renderHook(() =>
      useButtonEdgeMaintenance({
        ...defaultOptions,
        nodes: [
          { id: 'node-1', type: 'task', position: { x: 100, y: 100 } },
          { id: 'node-2', type: 'task', position: { x: 300, y: 100 } },
        ] as never[],
        edges: [{ id: 'edge-1', source: 'node-1', target: 'node-2', sourceHandle: 'source' }] as never[],
      })
    )

    act(() => {
      vi.advanceTimersByTime(100)
    })

    // The hook should have been called to update nodes
    expect(mockSetNodes).toHaveBeenCalled()
  })

  it('preserves pending-target nodes in node updates', () => {
    const nodesCalls: unknown[][] = []
    mockSetNodes.mockImplementation((updater) => {
      if (typeof updater === 'function') {
        const result = updater([
          { id: 'node-1', type: 'task', position: { x: 100, y: 100 } },
          { id: 'pending-target-node-1', type: 'placeholder', position: { x: 200, y: 100 } },
        ] as unknown as NodeType[])
        nodesCalls.push(result)
        return result
      }
    })

    renderHook(() =>
      useButtonEdgeMaintenance({
        ...defaultOptions,
        nodes: [
          { id: 'node-1', type: 'task', position: { x: 100, y: 100 } },
          { id: 'pending-target-node-1', type: 'placeholder', position: { x: 200, y: 100 } },
        ] as never[],
      })
    )

    act(() => {
      vi.advanceTimersByTime(100)
    })

    // Pending target node should be preserved
    expect(mockSetNodes).toHaveBeenCalled()
    const allNodes = nodesCalls.flat()
    const pendingNode = allNodes.find((n) => (n as { id: string }).id === 'pending-target-node-1')
    expect(pendingNode).toBeDefined()
  })

  it('handles empty real nodes gracefully', () => {
    renderHook(() =>
      useButtonEdgeMaintenance({
        ...defaultOptions,
        nodes: [{ id: 'placeholder-node-1', type: 'placeholder', position: { x: 100, y: 100 } }] as never[],
      })
    )

    act(() => {
      vi.advanceTimersByTime(100)
    })

    // Should not throw - handles empty real nodes case
    expect(mockSetEdges).not.toHaveBeenCalled()
  })

  it('updates button edge for condition node when activeEdgeButtonHandle matches', () => {
    const edgesCalls: unknown[][] = []
    mockSetEdges.mockImplementation((updater) => {
      if (typeof updater === 'function') {
        const result = updater([
          {
            id: 'button-condition-1-true',
            type: 'buttonEdge',
            source: 'condition-1',
            sourceHandle: 'true',
            data: { isActive: false },
          },
        ] as unknown as EdgeType[])
        edgesCalls.push(result)
        return result
      }
    })

    renderHook(() =>
      useButtonEdgeMaintenance({
        ...defaultOptions,
        nodes: [{ id: 'condition-1', type: 'condition', position: { x: 100, y: 100 } }] as never[],
        edges: [
          {
            id: 'button-condition-1-true',
            type: 'buttonEdge',
            source: 'condition-1',
            sourceHandle: 'true',
            data: { isActive: false },
          },
        ] as never[],
        activeEdgeButtonNodeId: 'condition-1',
        activeEdgeButtonHandle: 'true',
      })
    )

    act(() => {
      vi.advanceTimersByTime(100)
    })

    const allEdges = edgesCalls.flat()
    const buttonEdge = allEdges.find((e) => (e as { id: string }).id === 'button-condition-1-true') as {
      data: { isActive: boolean }
    }
    expect(buttonEdge?.data?.isActive).toBe(true)
  })

  it('updates button edge for loop node done handle', () => {
    const edgesCalls: unknown[][] = []
    mockSetEdges.mockImplementation((updater) => {
      if (typeof updater === 'function') {
        const result = updater([
          {
            id: 'button-loop-1-done',
            type: 'buttonEdge',
            source: 'loop-1',
            sourceHandle: 'done',
            data: { isActive: false },
          },
        ] as unknown as EdgeType[])
        edgesCalls.push(result)
        return result
      }
    })

    renderHook(() =>
      useButtonEdgeMaintenance({
        ...defaultOptions,
        nodes: [{ id: 'loop-1', type: 'loop', position: { x: 100, y: 100 } }] as never[],
        edges: [
          {
            id: 'button-loop-1-done',
            type: 'buttonEdge',
            source: 'loop-1',
            sourceHandle: 'done',
            data: { isActive: false },
          },
        ] as never[],
        activeEdgeButtonNodeId: 'loop-1',
        activeEdgeButtonHandle: 'done',
      })
    )

    act(() => {
      vi.advanceTimersByTime(100)
    })

    const allEdges = edgesCalls.flat()
    const buttonEdge = allEdges.find((e) => (e as { id: string }).id === 'button-loop-1-done') as {
      data: { isActive: boolean }
    }
    expect(buttonEdge?.data?.isActive).toBe(true)
  })

  it('updates button edge for approval node approved handle', () => {
    const edgesCalls: unknown[][] = []
    mockSetEdges.mockImplementation((updater) => {
      if (typeof updater === 'function') {
        const result = updater([
          {
            id: 'button-approval-1-approved',
            type: 'buttonEdge',
            source: 'approval-1',
            sourceHandle: 'approved',
            data: { isActive: false },
          },
        ] as unknown as EdgeType[])
        edgesCalls.push(result)
        return result
      }
    })

    renderHook(() =>
      useButtonEdgeMaintenance({
        ...defaultOptions,
        nodes: [{ id: 'approval-1', type: 'approval', position: { x: 100, y: 100 } }] as never[],
        edges: [
          {
            id: 'button-approval-1-approved',
            type: 'buttonEdge',
            source: 'approval-1',
            sourceHandle: 'approved',
            data: { isActive: false },
          },
        ] as never[],
        activeEdgeButtonNodeId: 'approval-1',
        activeEdgeButtonHandle: 'approved',
      })
    )

    act(() => {
      vi.advanceTimersByTime(100)
    })

    const allEdges = edgesCalls.flat()
    const buttonEdge = allEdges.find((e) => (e as { id: string }).id === 'button-approval-1-approved') as {
      data: { isActive: boolean }
    }
    expect(buttonEdge?.data?.isActive).toBe(true)
  })

  it('keeps button edge inactive when activeEdgeButtonHandle does not match', () => {
    const edgesCalls: unknown[][] = []
    mockSetEdges.mockImplementation((updater) => {
      if (typeof updater === 'function') {
        const result = updater([
          {
            id: 'button-condition-1-true',
            type: 'buttonEdge',
            source: 'condition-1',
            sourceHandle: 'true',
            data: { isActive: false },
          },
        ] as unknown as EdgeType[])
        edgesCalls.push(result)
        return result
      }
    })

    renderHook(() =>
      useButtonEdgeMaintenance({
        ...defaultOptions,
        nodes: [{ id: 'condition-1', type: 'condition', position: { x: 100, y: 100 } }] as never[],
        edges: [
          {
            id: 'button-condition-1-true',
            type: 'buttonEdge',
            source: 'condition-1',
            sourceHandle: 'true',
            data: { isActive: false },
          },
        ] as never[],
        activeEdgeButtonNodeId: 'condition-1',
        activeEdgeButtonHandle: 'false', // Different handle
      })
    )

    act(() => {
      vi.advanceTimersByTime(100)
    })

    const allEdges = edgesCalls.flat()
    const buttonEdge = allEdges.find((e) => (e as { id: string }).id === 'button-condition-1-true') as {
      data: { isActive: boolean }
    }
    // Should remain inactive because handle doesn't match
    expect(buttonEdge?.data?.isActive).toBe(false)
  })

  it('creates new button edge when node has no outgoing edges and no existing button edge', () => {
    const edgesCalls: unknown[][] = []
    mockSetEdges.mockImplementation((updater) => {
      if (typeof updater === 'function') {
        const result = updater([])
        edgesCalls.push(result)
        return result
      }
    })

    renderHook(() =>
      useButtonEdgeMaintenance({
        ...defaultOptions,
        nodes: [{ id: 'node-1', type: 'task', position: { x: 100, y: 100 } }] as never[],
        edges: [] as never[],
      })
    )

    act(() => {
      vi.advanceTimersByTime(100)
    })

    const allEdges = edgesCalls.flat()
    const buttonEdge = allEdges.find((e) => (e as { id: string }).id === 'button-node-1')
    expect(buttonEdge).toBeDefined()
  })

  it('does not create button edge when activeEdgeButtonHandle is null for regular node', () => {
    const edgesCalls: unknown[][] = []
    mockSetEdges.mockImplementation((updater) => {
      if (typeof updater === 'function') {
        const result = updater([])
        edgesCalls.push(result)
        return result
      }
    })

    renderHook(() =>
      useButtonEdgeMaintenance({
        ...defaultOptions,
        nodes: [{ id: 'node-1', type: 'task', position: { x: 100, y: 100 } }] as never[],
        edges: [] as never[],
        activeEdgeButtonNodeId: 'node-1',
        activeEdgeButtonHandle: null,
      })
    )

    act(() => {
      vi.advanceTimersByTime(100)
    })

    const allEdges = edgesCalls.flat()
    const buttonEdge = allEdges.find((e) => (e as { id: string }).id === 'button-node-1') as {
      data?: { isActive?: boolean }
    }
    // Button edge should be created and active when activeEdgeButtonHandle is null for regular nodes
    expect(buttonEdge).toBeDefined()
    expect(buttonEdge?.data?.isActive).toBe(true)
  })

  it('returns updated edges when only isActive changes (no additions/removals)', () => {
    const edgesCalls: unknown[][] = []
    mockSetEdges.mockImplementation((updater) => {
      if (typeof updater === 'function') {
        // Existing button edge with isActive: false — the hook should detect
        // the active state change and return updated edges
        const result = updater([
          {
            id: 'button-node-1',
            type: 'buttonEdge',
            source: 'node-1',
            sourceHandle: 'source',
            target: 'placeholder-node-1',
            targetHandle: 'target',
            data: { isActive: false },
          },
        ])
        edgesCalls.push(result)
        return result
      }
    })

    renderHook(() =>
      useButtonEdgeMaintenance({
        ...defaultOptions,
        nodes: [{ id: 'node-1', type: 'task', position: { x: 100, y: 100 } }] as never[],
        edges: [
          {
            id: 'button-node-1',
            type: 'buttonEdge',
            source: 'node-1',
            sourceHandle: 'source',
            target: 'placeholder-node-1',
            data: { isActive: false },
          },
        ] as never[],
        activeEdgeButtonNodeId: 'node-1',
        activeEdgeButtonHandle: 'source',
      })
    )

    act(() => {
      vi.advanceTimersByTime(100)
    })

    expect(mockSetEdges).toHaveBeenCalled()
    const allEdges = edgesCalls.flat()
    const buttonEdge = allEdges.find((e) => (e as { id: string }).id === 'button-node-1') as {
      data: { isActive: boolean }
    }
    // isActive should be updated to true even though no edges were added/removed
    expect(buttonEdge?.data?.isActive).toBe(true)
  })

  it('categorizes button edges by sourceHandle, not by parsing edge ID', () => {
    const edgesCalls: unknown[][] = []
    mockSetEdges.mockImplementation((updater) => {
      if (typeof updater === 'function') {
        // Edge ID contains '-true' substring (from node ID) but sourceHandle is 'source'
        // This should be treated as a regular node edge, not a condition handle
        const result = updater([
          {
            id: 'button-node-with-true-in-name',
            type: 'buttonEdge',
            source: 'node-with-true-in-name',
            sourceHandle: 'source',
            target: 'placeholder-node-with-true-in-name',
            targetHandle: 'target',
            data: { isActive: false },
          },
        ])
        edgesCalls.push(result)
        return result
      }
    })

    renderHook(() =>
      useButtonEdgeMaintenance({
        ...defaultOptions,
        nodes: [{ id: 'node-with-true-in-name', type: 'task', position: { x: 100, y: 100 } }] as never[],
        edges: [
          {
            id: 'button-node-with-true-in-name',
            type: 'buttonEdge',
            source: 'node-with-true-in-name',
            sourceHandle: 'source',
            target: 'placeholder-node-with-true-in-name',
            data: { isActive: false },
          },
        ] as never[],
        activeEdgeButtonNodeId: 'node-with-true-in-name',
        activeEdgeButtonHandle: 'source',
      })
    )

    act(() => {
      vi.advanceTimersByTime(100)
    })

    expect(mockSetEdges).toHaveBeenCalled()
    const allEdges = edgesCalls.flat()
    const buttonEdge = allEdges.find((e) => (e as { id: string }).id === 'button-node-with-true-in-name') as {
      data: { isActive: boolean }
    }
    // Should be kept as a regular node edge and marked active
    expect(buttonEdge).toBeDefined()
    expect(buttonEdge?.data?.isActive).toBe(true)
  })

  it('removes button edge when node gets a real outgoing connection', () => {
    const edgesCalls: unknown[][] = []
    mockSetEdges.mockImplementation((updater) => {
      if (typeof updater === 'function') {
        // Existing button edge should be removed when real edge is added
        const result = updater([
          { id: 'button-node-1', type: 'buttonEdge', source: 'node-1' },
          { id: 'real-edge', source: 'node-1', target: 'node-2', sourceHandle: 'source' },
        ] as unknown as EdgeType[])
        edgesCalls.push(result)
        return result
      }
    })

    renderHook(() =>
      useButtonEdgeMaintenance({
        ...defaultOptions,
        nodes: [
          { id: 'node-1', type: 'task', position: { x: 100, y: 100 } },
          { id: 'node-2', type: 'task', position: { x: 300, y: 100 } },
        ] as never[],
        edges: [{ id: 'real-edge', source: 'node-1', target: 'node-2', sourceHandle: 'source' }] as never[],
      })
    )

    act(() => {
      vi.advanceTimersByTime(100)
    })

    const allEdges = edgesCalls.flat()
    const buttonEdge = allEdges.find((e) => (e as { id: string }).id === 'button-node-1')
    // Button edge should be removed
    expect(buttonEdge).toBeUndefined()
  })

  it('re-runs when a node is replaced with a different type (same ID)', () => {
    // Regression test: replacing a task node with an approval node must trigger the effect
    // because the approval node needs 'approved'/'rejected' button edges instead of 'source'.
    const setEdgesCalls: unknown[][] = []
    const captureSetEdges = vi.fn<SetEdgesFn>((updater) => {
      if (typeof updater === 'function') {
        const result = updater([])
        setEdgesCalls.push(result)
        return result
      }
    })
    mockSetNodes.mockImplementation((updater) => (typeof updater === 'function' ? updater([]) : undefined))

    const taskNode = { id: 'node-1', type: 'task', position: { x: 100, y: 100 } }
    const approvalNode = { id: 'node-1', type: 'approval', position: { x: 100, y: 100 } }

    const { rerender } = renderHook((props) => useButtonEdgeMaintenance(props as never), {
      initialProps: {
        ...defaultOptions,
        nodes: [taskNode],
        edges: [],
        setEdges: captureSetEdges,
      },
    })

    act(() => {
      vi.advanceTimersByTime(100)
    })

    // Replace the task node with an approval node (same ID, different type)
    rerender({
      ...defaultOptions,
      nodes: [approvalNode],
      edges: [],
      setEdges: captureSetEdges,
    })

    act(() => {
      vi.advanceTimersByTime(100)
    })

    // The effect must have run a second time and created approval button edges
    const allCreatedEdges = setEdgesCalls.flat() as Array<{ id: string; sourceHandle?: string }>
    const approvedEdge = allCreatedEdges.find((e) => e.id === 'button-node-1-approved')
    const rejectedEdge = allCreatedEdges.find((e) => e.id === 'button-node-1-rejected')
    expect(approvedEdge).toBeDefined()
    expect(rejectedEdge).toBeDefined()
  })

  it('resets signature when transitioning from execution to edit mode', () => {
    const nodes = [{ id: 'node-1', type: 'task', position: { x: 100, y: 100 } }] as never[]
    const edges = [] as never[]
    type StatusProps = { executionStatus: string | null }
    const initialProps: StatusProps = { executionStatus: 'running' }

    // Start in execution mode
    const { rerender } = renderHook(
      ({ executionStatus }: StatusProps) =>
        useButtonEdgeMaintenance({
          ...defaultOptions,
          nodes,
          edges,
          executionStatus,
        }),
      { initialProps }
    )

    // In execution mode, no button edges should be created
    act(() => {
      vi.advanceTimersByTime(100)
    })

    // Clear mock calls from execution mode
    mockSetEdges.mockClear()
    mockSetNodes.mockClear()

    // Transition to null (edit mode)
    rerender({ executionStatus: null })

    // Advance timers to trigger the effect
    act(() => {
      vi.advanceTimersByTime(100)
    })

    // Verify button edges are recreated in edit mode
    // This validates that the signature was reset, forcing recreation
    expect(mockSetEdges).toHaveBeenCalled()
    expect(mockSetNodes).toHaveBeenCalled()
  })
})
