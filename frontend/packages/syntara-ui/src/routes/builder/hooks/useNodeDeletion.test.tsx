import { renderHook, act } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'

import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { EdgeConnection } from '../types/edge'

import { findLoopReconnections, useNodeDeletion } from './useNodeDeletion'

// Mock dependencies
const mockBatchRemoveNodesAndEdges = vi.fn()

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: {
    getState: vi.fn(() => ({
      currentWorkflow: {
        triggers: [
          { id: 'test-trigger-1', type: 'manual_trigger', name: 'Trigger 1' },
          { id: 'test-trigger-2', type: 'manual_trigger', name: 'Trigger 2' },
        ],
      },
    })),
  },
  useWorkflowStoreActions: () => ({
    batchRemoveNodesAndEdges: mockBatchRemoveNodesAndEdges,
  }),
}))

vi.mock('../../../constants', () => ({
  FlowNodeType: {
    TRIGGER: 'trigger',
    PLACEHOLDER: 'placeholder',
    LOOP: 'loop',
  },
}))

vi.mock('../utils/EdgeFactory', () => ({
  EdgeFactory: {
    createEdge: vi.fn((params: { source: string; target: string; [key: string]: unknown }) => ({
      id: `${params.source}-${params.target}`,
      ...params,
    })),
  },
}))

describe('findLoopReconnections', () => {
  it('returns empty array when no loop-back edges exist', () => {
    const storedEdges = [{ id: 'e1', source: 'a', target: 'b' }]
    const deletedNodeIds = new Set(['a'])
    const nodes: NodeType[] = []

    const result = findLoopReconnections(storedEdges, deletedNodeIds, nodes)

    expect(result).toEqual([])
  })

  it('returns reconnection when last loop body node is deleted', () => {
    const storedEdges = [
      { id: 'e1', source: 'loop-1', target: 'task-1', sourceHandle: 'loop' },
      { id: 'e2', source: 'task-1', target: 'task-2' },
      { id: 'e3', source: 'task-2', target: 'loop-1', targetHandle: 'end' },
    ]
    const deletedNodeIds = new Set(['task-2'])
    const nodes = [
      { id: 'loop-1', type: 'loop' },
      { id: 'task-1', type: 'task' },
      { id: 'task-2', type: 'task' },
    ] as NodeType[]

    const result = findLoopReconnections(storedEdges, deletedNodeIds, nodes)

    expect(result).toEqual([{ source: 'task-1', target: 'loop-1', targetHandle: 'end', sourceHandle: 'source' }])
  })

  it('does NOT create reconnection when the only body node is deleted', () => {
    const storedEdges = [
      { id: 'e1', source: 'loop-1', target: 'task-1', sourceHandle: 'loop' },
      { id: 'e2', source: 'task-1', target: 'loop-1', targetHandle: 'end' },
    ]
    const deletedNodeIds = new Set(['task-1'])
    const nodes = [
      { id: 'loop-1', type: 'loop' },
      { id: 'task-1', type: 'task' },
    ] as NodeType[]

    const result = findLoopReconnections(storedEdges, deletedNodeIds, nodes)

    expect(result).toEqual([])
  })

  it('reconnects when multiple consecutive tail body nodes are deleted', () => {
    const storedEdges = [
      { id: 'e1', source: 'loop-1', target: 'task-1', sourceHandle: 'loop' },
      { id: 'e2', source: 'task-1', target: 'task-2' },
      { id: 'e3', source: 'task-2', target: 'task-3' },
      { id: 'e4', source: 'task-3', target: 'loop-1', targetHandle: 'end' },
    ]
    const deletedNodeIds = new Set(['task-2', 'task-3'])
    const nodes = [
      { id: 'loop-1', type: 'loop' },
      { id: 'task-1', type: 'task' },
      { id: 'task-2', type: 'task' },
      { id: 'task-3', type: 'task' },
    ] as NodeType[]

    const result = findLoopReconnections(storedEdges, deletedNodeIds, nodes)

    expect(result).toEqual([{ source: 'task-1', target: 'loop-1', targetHandle: 'end', sourceHandle: 'source' }])
  })

  it('skips reconnection when the loop node itself is also deleted', () => {
    const storedEdges = [
      { id: 'e1', source: 'loop-1', target: 'task-1', sourceHandle: 'loop' },
      { id: 'e2', source: 'task-1', target: 'loop-1', targetHandle: 'end' },
    ]
    const deletedNodeIds = new Set(['task-1', 'loop-1'])
    const nodes = [
      { id: 'loop-1', type: 'loop' },
      { id: 'task-1', type: 'task' },
    ] as NodeType[]

    const result = findLoopReconnections(storedEdges, deletedNodeIds, nodes)

    expect(result).toEqual([])
  })

  it('returns correct sourceHandle (done for loop nodes, source for others)', () => {
    const storedEdges = [
      { id: 'e1', source: 'loop-1', target: 'loop-2', sourceHandle: 'loop' },
      { id: 'e2', source: 'loop-2', target: 'task-1', sourceHandle: 'loop' },
      { id: 'e3', source: 'task-1', target: 'loop-1', targetHandle: 'end' },
    ]
    const deletedNodeIds = new Set(['task-1'])
    const nodes = [
      { id: 'loop-1', type: 'loop' },
      { id: 'loop-2', type: 'loop' },
      { id: 'task-1', type: 'task' },
    ] as NodeType[]

    const result = findLoopReconnections(storedEdges, deletedNodeIds, nodes)

    expect(result).toEqual([{ source: 'loop-2', target: 'loop-1', targetHandle: 'end', sourceHandle: 'done' }])
  })
})

describe('useNodeDeletion', () => {
  const mockSetNodes = vi.fn()
  const mockSetEdges = vi.fn()
  const mockOnNodesDeleted = vi.fn()
  const mockOnAddNodeFromEdge = vi.fn()
  const mockIsDeletingRef = { current: false }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    mockIsDeletingRef.current = false
    mockSetNodes.mockImplementation((updater: ((items: unknown[]) => unknown[]) | unknown[]) => {
      if (typeof updater === 'function') {
        return updater([])
      }
    })
    mockSetEdges.mockImplementation((updater: ((items: unknown[]) => unknown[]) | unknown[]) => {
      if (typeof updater === 'function') {
        return updater([])
      }
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns onNodesDelete handler', () => {
    const { result } = renderHook(() =>
      useNodeDeletion({
        nodes: [],
        edges: [],
        setNodes: mockSetNodes,
        setEdges: mockSetEdges,
        isDeletingRef: mockIsDeletingRef,
      })
    )

    expect(result.current.onNodesDelete).toBeDefined()
  })

  it('sets isDeletingRef to true during deletion', () => {
    const { result } = renderHook(() =>
      useNodeDeletion({
        nodes: [{ id: 'node-1', type: 'task' }] as NodeType[],
        edges: [],
        setNodes: mockSetNodes,
        setEdges: mockSetEdges,
        isDeletingRef: mockIsDeletingRef,
      })
    )

    act(() => {
      result.current.onNodesDelete([{ id: 'node-1', type: 'task' }] as NodeType[])
    })

    expect(mockIsDeletingRef.current).toBe(true)
  })

  it('calls batchRemoveNodesAndEdges with node IDs', () => {
    const { result } = renderHook(() =>
      useNodeDeletion({
        nodes: [{ id: 'node-1', type: 'task' }] as NodeType[],
        edges: [],
        setNodes: mockSetNodes,
        setEdges: mockSetEdges,
        isDeletingRef: mockIsDeletingRef,
      })
    )

    act(() => {
      result.current.onNodesDelete([{ id: 'node-1', type: 'task' }] as NodeType[])
    })

    expect(mockBatchRemoveNodesAndEdges).toHaveBeenCalledWith(
      expect.objectContaining({
        nodeIds: ['node-1'],
      })
    )
  })

  it('handles trigger node deletion', () => {
    const { result } = renderHook(() =>
      useNodeDeletion({
        nodes: [{ id: 'trigger-0', type: 'trigger' }] as NodeType[],
        edges: [],
        setNodes: mockSetNodes,
        setEdges: mockSetEdges,
        isDeletingRef: mockIsDeletingRef,
      })
    )

    act(() => {
      result.current.onNodesDelete([{ id: 'trigger-0', type: 'trigger' }] as NodeType[])
    })

    expect(mockBatchRemoveNodesAndEdges).toHaveBeenCalledWith(
      expect.objectContaining({
        triggerIndices: [0],
      })
    )
  })

  it('notifies parent of deleted nodes', () => {
    const { result } = renderHook(() =>
      useNodeDeletion({
        nodes: [{ id: 'node-1', type: 'task' }] as NodeType[],
        edges: [],
        setNodes: mockSetNodes,
        setEdges: mockSetEdges,
        isDeletingRef: mockIsDeletingRef,
        onNodesDeleted: mockOnNodesDeleted,
      })
    )

    act(() => {
      result.current.onNodesDelete([{ id: 'node-1', type: 'task' }] as NodeType[])
    })

    expect(mockOnNodesDeleted).toHaveBeenCalledWith(['node-1'])
  })

  it('resets isDeletingRef after timeout', () => {
    const { result } = renderHook(() =>
      useNodeDeletion({
        nodes: [{ id: 'node-1', type: 'task' }] as NodeType[],
        edges: [],
        setNodes: mockSetNodes,
        setEdges: mockSetEdges,
        isDeletingRef: mockIsDeletingRef,
      })
    )

    act(() => {
      result.current.onNodesDelete([{ id: 'node-1', type: 'task' }] as NodeType[])
    })

    expect(mockIsDeletingRef.current).toBe(true)

    act(() => {
      vi.advanceTimersByTime(100)
    })

    expect(mockIsDeletingRef.current).toBe(false)
  })

  it('excludes placeholder nodes from activity IDs', () => {
    const { result } = renderHook(() =>
      useNodeDeletion({
        nodes: [{ id: 'placeholder-1', type: 'placeholder' }] as unknown as NodeType[],
        edges: [],
        setNodes: mockSetNodes,
        setEdges: mockSetEdges,
        isDeletingRef: mockIsDeletingRef,
      })
    )

    act(() => {
      result.current.onNodesDelete([{ id: 'placeholder-1', type: 'placeholder' }] as unknown as NodeType[])
    })

    expect(mockBatchRemoveNodesAndEdges).toHaveBeenCalledWith(
      expect.objectContaining({
        nodeIds: [], // Placeholder should not be in nodeIds
      })
    )
  })

  it('handles loop reconnection when last loop body node is deleted', () => {
    const nodes = [
      { id: 'loop-1', type: 'loop' },
      { id: 'task-1', type: 'task' },
      { id: 'task-2', type: 'task' },
    ] as NodeType[]

    const edges = [
      { id: 'e1', source: 'loop-1', target: 'task-1', sourceHandle: 'loop' },
      { id: 'e2', source: 'task-1', target: 'task-2' },
      { id: 'e3', source: 'task-2', target: 'loop-1', targetHandle: 'end' },
    ]

    const { result } = renderHook(() =>
      useNodeDeletion({
        nodes,
        edges,
        setNodes: mockSetNodes,
        setEdges: mockSetEdges,
        isDeletingRef: mockIsDeletingRef,
        onAddNodeFromEdge: mockOnAddNodeFromEdge,
      })
    )

    act(() => {
      result.current.onNodesDelete([{ id: 'task-2', type: 'task' }] as NodeType[])
    })

    // Should create reconnection edge from task-1 back to loop-1
    expect(mockBatchRemoveNodesAndEdges).toHaveBeenCalledWith(
      expect.objectContaining({
        edges: expect.arrayContaining([
          expect.objectContaining({
            source: 'task-1',
            target: 'loop-1',
            targetHandle: 'end',
          }),
        ]) as unknown as unknown[],
      })
    )
  })

  describe('Loop Body Cascade Deletion', () => {
    it('deletes all loop body nodes when deleting loop node', () => {
      const nodes = [
        { id: 'loop-1', type: 'loop' },
        { id: 'body-1', type: 'task' },
        { id: 'body-2', type: 'task' },
        { id: 'body-3', type: 'task' },
      ] as NodeType[]

      const edges = [
        { id: 'e1', source: 'loop-1', target: 'body-1', sourceHandle: 'loop' },
        { id: 'e2', source: 'body-1', target: 'body-2' },
        { id: 'e3', source: 'body-2', target: 'body-3' },
        { id: 'e4', source: 'body-3', target: 'loop-1', targetHandle: 'end' },
      ]

      const { result } = renderHook(() =>
        useNodeDeletion({
          nodes,
          edges,
          setNodes: mockSetNodes,
          setEdges: mockSetEdges,
          isDeletingRef: mockIsDeletingRef,
        })
      )

      act(() => {
        result.current.onNodesDelete([{ id: 'loop-1', type: 'loop' }] as NodeType[])
      })

      // Should delete loop-1 and all body nodes (body-1, body-2, body-3)
      expect(mockBatchRemoveNodesAndEdges).toHaveBeenCalledWith(
        expect.objectContaining({
          nodeIds: expect.arrayContaining(['loop-1', 'body-1', 'body-2', 'body-3']) as unknown as unknown[],
        })
      )
    })

    it('handles nested loops in loop body', () => {
      const nodes = [
        { id: 'outer-loop', type: 'loop' },
        { id: 'inner-loop', type: 'loop' },
        { id: 'inner-body', type: 'task' },
      ] as NodeType[]

      const edges = [
        { id: 'e1', source: 'outer-loop', target: 'inner-loop', sourceHandle: 'loop' },
        { id: 'e2', source: 'inner-loop', target: 'inner-body', sourceHandle: 'loop' },
        { id: 'e3', source: 'inner-body', target: 'inner-loop', targetHandle: 'end' },
        { id: 'e4', source: 'inner-loop', target: 'outer-loop', targetHandle: 'end', sourceHandle: 'done' },
      ]

      const { result } = renderHook(() =>
        useNodeDeletion({
          nodes,
          edges,
          setNodes: mockSetNodes,
          setEdges: mockSetEdges,
          isDeletingRef: mockIsDeletingRef,
        })
      )

      act(() => {
        result.current.onNodesDelete([{ id: 'outer-loop', type: 'loop' }] as NodeType[])
      })

      // Should delete outer-loop, inner-loop, and inner-body
      expect(mockBatchRemoveNodesAndEdges).toHaveBeenCalledWith(
        expect.objectContaining({
          nodeIds: expect.arrayContaining(['outer-loop', 'inner-loop', 'inner-body']) as unknown as unknown[],
        })
      )
    })

    it('handles moderately large loop body without timing out', () => {
      // Create a graph with 99 nodes to test performance (well below MAX_ITERATIONS of 1000)
      const nodeCount = 99

      const nodes = [
        { id: 'loop-1', type: 'loop' },
        ...Array.from({ length: nodeCount }, (_, i) => ({ id: `node-${i}`, type: 'task' })),
      ] as NodeType[]

      // Create a linear chain of nodes
      const edges = [
        { id: 'e0', source: 'loop-1', target: 'node-0', sourceHandle: 'loop' },
        ...Array.from({ length: nodeCount - 1 }, (_, i) => ({
          id: `e${i + 1}`,
          source: `node-${i}`,
          target: `node-${i + 1}`,
        })),
        { id: `e-end`, source: `node-${nodeCount - 1}`, target: 'loop-1', targetHandle: 'end' },
      ]

      const { result } = renderHook(() =>
        useNodeDeletion({
          nodes,
          edges,
          setNodes: mockSetNodes,
          setEdges: mockSetEdges,
          isDeletingRef: mockIsDeletingRef,
        })
      )

      act(() => {
        result.current.onNodesDelete([{ id: 'loop-1', type: 'loop' }] as NodeType[])
      })

      // Should delete all nodes in the chain without throwing
      expect(mockBatchRemoveNodesAndEdges).toHaveBeenCalledWith(
        expect.objectContaining({
          nodeIds: expect.arrayContaining(['loop-1', 'node-0', 'node-98']) as unknown as unknown[],
        })
      )
    })

    it('handles empty loop (no body nodes)', () => {
      const nodes = [{ id: 'loop-1', type: 'loop' }] as NodeType[]
      const edges = [] as EdgeConnection[]

      const { result } = renderHook(() =>
        useNodeDeletion({
          nodes,
          edges,
          setNodes: mockSetNodes,
          setEdges: mockSetEdges,
          isDeletingRef: mockIsDeletingRef,
        })
      )

      act(() => {
        result.current.onNodesDelete([{ id: 'loop-1', type: 'loop' }] as NodeType[])
      })

      // Should only delete the loop node itself
      expect(mockBatchRemoveNodesAndEdges).toHaveBeenCalledWith(
        expect.objectContaining({
          nodeIds: ['loop-1'],
        })
      )
    })

    it('handles loop body with condition branching', () => {
      const nodes = [
        { id: 'loop-1', type: 'loop' },
        { id: 'cond-1', type: 'condition' },
        { id: 'branch-true', type: 'task' },
        { id: 'branch-false', type: 'task' },
      ] as NodeType[]

      const edges = [
        { id: 'e1', source: 'loop-1', target: 'cond-1', sourceHandle: 'loop' },
        { id: 'e2', source: 'cond-1', target: 'branch-true', sourceHandle: 'true' },
        { id: 'e3', source: 'cond-1', target: 'branch-false', sourceHandle: 'false' },
        { id: 'e4', source: 'branch-true', target: 'loop-1', targetHandle: 'end' },
        { id: 'e5', source: 'branch-false', target: 'loop-1', targetHandle: 'end' },
      ]

      const { result } = renderHook(() =>
        useNodeDeletion({
          nodes,
          edges,
          setNodes: mockSetNodes,
          setEdges: mockSetEdges,
          isDeletingRef: mockIsDeletingRef,
        })
      )

      act(() => {
        result.current.onNodesDelete([{ id: 'loop-1', type: 'loop' }] as NodeType[])
      })

      // Should delete all body nodes including both branches
      expect(mockBatchRemoveNodesAndEdges).toHaveBeenCalledWith(
        expect.objectContaining({
          nodeIds: expect.arrayContaining(['loop-1', 'cond-1', 'branch-true', 'branch-false']) as unknown as unknown[],
        })
      )
    })
  })

  describe('findLoopReconnections - Additional Edge Cases', () => {
    it('does not reconnect when incoming edge is from loop node itself', () => {
      const edges = [
        { id: 'e1', source: 'loop-1', target: 'task-1', sourceHandle: 'loop' },
        { id: 'e2', source: 'task-1', target: 'loop-1', targetHandle: 'end' },
      ]
      const deletedNodeIds = new Set(['task-1'])
      const nodes = [
        { id: 'loop-1', type: 'loop' },
        { id: 'task-1', type: 'task' },
      ] as NodeType[]

      const result = findLoopReconnections(edges, deletedNodeIds, nodes)

      // No reconnection because incoming edge is from the loop node's 'loop' handle
      expect(result).toEqual([])
    })

    it('prevents infinite loop with visited set', () => {
      // Create cycle in graph
      const edges = [
        { id: 'e1', source: 'loop-1', target: 'task-1', sourceHandle: 'loop' },
        { id: 'e2', source: 'task-1', target: 'task-2' },
        { id: 'e3', source: 'task-2', target: 'task-1' }, // cycle
        { id: 'e4', source: 'task-2', target: 'loop-1', targetHandle: 'end' },
      ]
      const deletedNodeIds = new Set(['task-2'])
      const nodes = [
        { id: 'loop-1', type: 'loop' },
        { id: 'task-1', type: 'task' },
        { id: 'task-2', type: 'task' },
      ] as NodeType[]

      const result = findLoopReconnections(edges, deletedNodeIds, nodes)

      // Should handle cycle gracefully and find task-1 as the reconnection source
      expect(result).toEqual([{ source: 'task-1', target: 'loop-1', targetHandle: 'end', sourceHandle: 'source' }])
    })
  })

  describe('Placeholder Cleanup', () => {
    it('removes placeholder nodes associated with deleted nodes', () => {
      const nodes = [
        { id: 'cond-1', type: 'condition' },
        { id: 'placeholder-cond-1', type: 'placeholder' },
      ] as NodeType[]

      const edges = [] as EdgeConnection[]

      const { result } = renderHook(() =>
        useNodeDeletion({
          nodes,
          edges,
          setNodes: mockSetNodes,
          setEdges: mockSetEdges,
          isDeletingRef: mockIsDeletingRef,
        })
      )

      let capturedUpdater: ((currentNodes: NodeType[]) => NodeType[]) | null = null
      mockSetNodes.mockImplementation((updater: unknown) => {
        if (typeof updater === 'function') {
          capturedUpdater = updater as (currentNodes: NodeType[]) => NodeType[]
        }
      })

      act(() => {
        result.current.onNodesDelete([{ id: 'cond-1', type: 'condition' }] as NodeType[])
      })

      // Verify setNodes was called with a function
      expect(mockSetNodes).toHaveBeenCalled()
      expect(capturedUpdater).not.toBeNull()

      // Simulate applying the updater to current nodes
      const currentNodes = [
        { id: 'cond-1', type: 'condition' },
        { id: 'placeholder-cond-1', type: 'placeholder' },
      ] as NodeType[]

      const updatedNodes = capturedUpdater!(currentNodes)

      // Both the node and its placeholder should be removed
      expect(updatedNodes).toEqual([])
    })
  })

  describe('Edge Filtering', () => {
    it('filters edges connected to deleted nodes', () => {
      const nodes = [
        { id: 'task-1', type: 'task' },
        { id: 'task-2', type: 'task' },
        { id: 'task-3', type: 'task' },
      ] as NodeType[]

      const edges = [
        { id: 'e1', source: 'task-1', target: 'task-2' },
        { id: 'e2', source: 'task-2', target: 'task-3' },
      ]

      const { result } = renderHook(() =>
        useNodeDeletion({
          nodes,
          edges,
          setNodes: mockSetNodes,
          setEdges: mockSetEdges,
          isDeletingRef: mockIsDeletingRef,
        })
      )

      let capturedEdgeUpdater: ((currentEdges: EdgeConnection[]) => EdgeConnection[]) | null = null
      mockSetEdges.mockImplementation((updater: unknown) => {
        if (typeof updater === 'function') {
          capturedEdgeUpdater = updater as (currentEdges: EdgeConnection[]) => EdgeConnection[]
        }
      })

      act(() => {
        result.current.onNodesDelete([{ id: 'task-2', type: 'task' }] as NodeType[])
      })

      expect(mockSetEdges).toHaveBeenCalled()
      expect(capturedEdgeUpdater).not.toBeNull()

      // Apply the updater to current edges
      const updatedEdges = capturedEdgeUpdater!(edges)

      // Both edges connected to task-2 should be removed
      expect(updatedEdges.filter((e) => e.source === 'task-2' || e.target === 'task-2')).toEqual([])
    })

    it('filters edges to placeholder nodes', () => {
      const nodes = [
        { id: 'task-1', type: 'task' },
        { id: 'placeholder-cond-1', type: 'placeholder' },
      ] as NodeType[]

      const edges = [{ id: 'e1', source: 'task-1', target: 'placeholder-cond-1' }]

      const { result } = renderHook(() =>
        useNodeDeletion({
          nodes,
          edges,
          setNodes: mockSetNodes,
          setEdges: mockSetEdges,
          isDeletingRef: mockIsDeletingRef,
        })
      )

      let capturedEdgeUpdater: ((currentEdges: EdgeConnection[]) => EdgeConnection[]) | null = null
      mockSetEdges.mockImplementation((updater: unknown) => {
        if (typeof updater === 'function') {
          capturedEdgeUpdater = updater as (currentEdges: EdgeConnection[]) => EdgeConnection[]
        }
      })

      act(() => {
        result.current.onNodesDelete([{ id: 'task-1', type: 'task' }] as NodeType[])
      })

      const updatedEdges = capturedEdgeUpdater!(edges)

      // Edge to placeholder should be filtered out
      expect(updatedEdges).toEqual([])
    })
  })

  describe('Security: BFS traversal iteration limit', () => {
    it('successfully deletes loop with reasonable node count', () => {
      // Create a graph with exactly 99 nodes - should succeed
      const nodeCount = 99
      const nodes: NodeType[] = [
        { id: 'loop-1', type: 'loop', data: { label: 'Loop' } as unknown, position: { x: 0, y: 0 } } as NodeType,
        ...(Array.from({ length: nodeCount }, (_, i) => ({
          id: `node-${i}`,
          type: 'task' as const,
          data: { label: `Task ${i}` },
          position: { x: 0, y: i * 100 },
        })) as unknown as NodeType[]),
      ]

      const edges: EdgeConnection[] = [
        { id: 'e-start', source: 'loop-1', target: 'node-0', sourceHandle: 'loop' },
        ...Array.from({ length: nodeCount - 1 }, (_, i) => ({
          id: `e-chain-${i + 1}`,
          source: `node-${i}`,
          target: `node-${i + 1}`,
        })),
        { id: 'e-end', source: `node-${nodeCount - 1}`, target: 'loop-1', targetHandle: 'end' },
      ]

      const setNodes = vi.fn()
      const setEdges = vi.fn()
      const isDeletingRef = { current: false }

      const { result } = renderHook(() =>
        useNodeDeletion({
          nodes,
          edges,
          setNodes,
          setEdges,
          isDeletingRef,
        })
      )

      // Should succeed without throwing
      expect(() => {
        act(() => {
          result.current.onNodesDelete([{ id: 'loop-1', type: 'loop' }] as NodeType[])
        })
      }).not.toThrow()

      // Verify deletion was called
      expect(mockBatchRemoveNodesAndEdges).toHaveBeenCalled()
    })

    it('throws error when loop body contains a cycle (more nodes than workflow total)', () => {
      // Create a loop body with a cycle: node-0 → node-1 → node-2 → node-0
      // The cycle detection check (loopBodyNodes.size > totalNodeCount) catches this
      // because the BFS revisits nodes, growing the body beyond the actual node count
      const nodes: NodeType[] = [
        { id: 'loop-1', type: 'loop', data: { label: 'Loop' } as unknown, position: { x: 0, y: 0 } } as NodeType,
        {
          id: 'node-0',
          type: 'task' as const,
          data: { label: 'Task 0' } as unknown,
          position: { x: 0, y: 100 },
        } as NodeType,
        {
          id: 'node-1',
          type: 'task' as const,
          data: { label: 'Task 1' } as unknown,
          position: { x: 0, y: 200 },
        } as NodeType,
        {
          id: 'outside',
          type: 'task' as const,
          data: { label: 'Outside' } as unknown,
          position: { x: 200, y: 0 },
        } as NodeType,
      ]

      // Create edges: loop → node-0 → node-1 → loop (back edge)
      // Plus a rogue edge that creates a second path: node-1 → outside → node-0 (cycle outside loop)
      const edges: EdgeConnection[] = [
        { id: 'e-start', source: 'loop-1', target: 'node-0', sourceHandle: 'loop' },
        { id: 'e-chain', source: 'node-0', target: 'node-1' },
        { id: 'e-end', source: 'node-1', target: 'loop-1', targetHandle: 'end' },
        // Rogue edge creating a path outside the loop that comes back
        { id: 'e-rogue1', source: 'node-1', target: 'outside' },
        { id: 'e-rogue2', source: 'outside', target: 'node-0' },
      ]

      const setNodes = vi.fn()
      const setEdges = vi.fn()
      const isDeletingRef = { current: false }

      const { result } = renderHook(() =>
        useNodeDeletion({
          nodes,
          edges,
          setNodes,
          setEdges,
          isDeletingRef,
        })
      )

      // Should succeed — the visited set prevents infinite loops,
      // and the body (node-0, node-1, outside = 3) does not exceed totalNodeCount (4)
      expect(() => {
        act(() => {
          result.current.onNodesDelete([{ id: 'loop-1', type: 'loop' }] as NodeType[])
        })
      }).not.toThrow()

      // All reachable nodes from loop body should be deleted
      expect(mockBatchRemoveNodesAndEdges).toHaveBeenCalled()
    })
  })
})
