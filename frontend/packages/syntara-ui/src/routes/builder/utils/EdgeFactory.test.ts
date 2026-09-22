import { describe, expect, it, vi } from 'vitest'

import { EdgeFactory } from './EdgeFactory'
import type { EdgeType } from './workflowToGraph'

// Mock @xyflow/react addEdge with importOriginal to preserve MarkerType
vi.mock('@xyflow/react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@xyflow/react')>()
  return {
    ...actual,
    addEdge: vi.fn((edge: unknown, edges: unknown[]) => [...edges, edge]),
  }
})

describe('EdgeFactory', () => {
  describe('createEdge', () => {
    it('creates a basic edge with default type', () => {
      const edge = EdgeFactory.createEdge({
        source: 'node-1',
        target: 'node-2',
      })

      expect(edge).toMatchObject({
        id: 'node-1-node-2',
        source: 'node-1',
        target: 'node-2',
        targetHandle: 'target',
        type: 'default',
      })
      expect(edge.markerEnd).toBeDefined()
    })

    it('creates edge with source and target handles', () => {
      const edge = EdgeFactory.createEdge({
        source: 'node-1',
        target: 'node-2',
        sourceHandle: 'source',
        targetHandle: 'custom-target',
      })

      expect(edge.sourceHandle).toBe('source')
      expect(edge.targetHandle).toBe('custom-target')
    })

    it('creates condition edge with true handle', () => {
      const edge = EdgeFactory.createEdge({
        source: 'condition-1',
        target: 'task-1',
        sourceHandle: 'true',
      })

      expect(edge.id).toBe('condition-1-true-task-1')
      expect(edge.type).toBe('default')
    })

    it('creates condition edge with false handle', () => {
      const edge = EdgeFactory.createEdge({
        source: 'condition-1',
        target: 'task-2',
        sourceHandle: 'false',
      })

      expect(edge.id).toBe('condition-1-false-task-2')
      expect(edge.type).toBe('default')
    })

    it('creates approval edge with approved handle', () => {
      const edge = EdgeFactory.createEdge({
        source: 'approval-1',
        target: 'task-1',
        sourceHandle: 'approved',
      })

      expect(edge.id).toBe('approval-1-approved-task-1')
      expect(edge.sourceHandle).toBe('approved')
      expect(edge.type).toBe('default')
    })

    it('creates approval edge with rejected handle', () => {
      const edge = EdgeFactory.createEdge({
        source: 'approval-1',
        target: 'task-2',
        sourceHandle: 'rejected',
      })

      expect(edge.id).toBe('approval-1-rejected-task-2')
      expect(edge.sourceHandle).toBe('rejected')
      expect(edge.type).toBe('default')
    })

    it('creates loopBack edge when targeting end handle', () => {
      const edge = EdgeFactory.createEdge({
        source: 'task-in-loop',
        target: 'loop-1',
        targetHandle: 'end',
      })

      expect(edge.type).toBe('loopBack')
    })

    it('creates loopOutgoing edge from loop handle', () => {
      const edge = EdgeFactory.createEdge({
        source: 'loop-1',
        target: 'first-task-in-loop',
        sourceHandle: 'loop',
      })

      expect(edge.type).toBe('loopOutgoing')
    })

    it('creates loopDone edge from done handle', () => {
      const edge = EdgeFactory.createEdge({
        source: 'loop-1',
        target: 'task-after-loop',
        sourceHandle: 'done',
      })

      expect(edge.type).toBe('loopDone')
    })

    it('includes onAddNode callback in data', () => {
      const onAddNode = vi.fn()
      const edge = EdgeFactory.createEdge({
        source: 'node-1',
        target: 'node-2',
        onAddNode,
      })

      expect(edge.data?.onAddNode).toBe(onAddNode)
    })

    it('does not include data when onAddNode is not provided', () => {
      const edge = EdgeFactory.createEdge({
        source: 'node-1',
        target: 'node-2',
      })

      expect(edge.data).toBeUndefined()
    })
  })

  describe('addEdge', () => {
    it('adds edge to existing edges array', () => {
      const existingEdges: EdgeType[] = [{ id: 'edge-1', source: 'node-1', target: 'node-2', type: 'default' }]
      const newEdge = EdgeFactory.createEdge({
        source: 'node-2',
        target: 'node-3',
      })

      const result = EdgeFactory.addEdge(newEdge, existingEdges)

      expect(result).toHaveLength(2)
      expect(result[1]).toEqual(newEdge)
    })

    it('adds edge to empty array', () => {
      const newEdge = EdgeFactory.createEdge({
        source: 'node-1',
        target: 'node-2',
      })

      const result = EdgeFactory.addEdge(newEdge, [])

      expect(result).toHaveLength(1)
      expect(result[0]).toEqual(newEdge)
    })
  })

  describe('createAndAdd', () => {
    it('creates and adds edge in one operation', () => {
      const existingEdges: EdgeType[] = [{ id: 'edge-1', source: 'node-1', target: 'node-2', type: 'default' }]

      const result = EdgeFactory.createAndAdd(
        {
          source: 'node-2',
          target: 'node-3',
        },
        existingEdges
      )

      expect(result).toHaveLength(2)
      expect(result[1].source).toBe('node-2')
      expect(result[1].target).toBe('node-3')
    })
  })

  describe('replaceEdge', () => {
    it('replaces an existing edge', () => {
      const existingEdges: EdgeType[] = [
        { id: 'edge-1', source: 'node-1', target: 'node-2', type: 'default' },
        { id: 'edge-2', source: 'node-2', target: 'node-3', type: 'default' },
      ]

      const result = EdgeFactory.replaceEdge(
        'edge-1',
        {
          source: 'node-1',
          target: 'node-4',
        },
        existingEdges
      )

      expect(result).toHaveLength(2)
      expect(result.find((e) => e.id === 'edge-1')).toBeUndefined()
      expect(result.find((e) => e.target === 'node-4')).toBeDefined()
    })

    it('handles replacing non-existent edge', () => {
      const existingEdges: EdgeType[] = [{ id: 'edge-1', source: 'node-1', target: 'node-2', type: 'default' }]

      const result = EdgeFactory.replaceEdge(
        'non-existent',
        {
          source: 'node-2',
          target: 'node-3',
        },
        existingEdges
      )

      expect(result).toHaveLength(2)
    })
  })

  describe('removeButtonEdge', () => {
    it('removes button edge for regular node', () => {
      const edges: EdgeType[] = [
        { id: 'button-node-1', source: 'node-1', target: 'placeholder-node-1', type: 'buttonEdge' },
        { id: 'edge-1', source: 'node-1', target: 'node-2', type: 'default' },
      ]

      const result = EdgeFactory.removeButtonEdge('node-1', edges)

      expect(result).toHaveLength(1)
      expect(result[0].id).toBe('edge-1')
    })

    it('removes all button edge variants for a node without specific handle', () => {
      const edges: EdgeType[] = [
        { id: 'button-condition-1', source: 'condition-1', target: 'placeholder', type: 'buttonEdge' },
        { id: 'button-condition-1-true', source: 'condition-1', target: 'placeholder', type: 'buttonEdge' },
        {
          id: 'button-condition-1-false',
          source: 'condition-1',
          target: 'placeholder',
          type: 'buttonEdge',
        },
        { id: 'edge-1', source: 'condition-1', target: 'task-1', type: 'default' },
      ]

      const result = EdgeFactory.removeButtonEdge('condition-1', edges)

      expect(result).toHaveLength(1)
      expect(result[0].id).toBe('edge-1')
    })

    it('removes specific true handle button edge', () => {
      const edges: EdgeType[] = [
        { id: 'button-condition-1-true', source: 'condition-1', target: 'placeholder', type: 'buttonEdge' },
        {
          id: 'button-condition-1-false',
          source: 'condition-1',
          target: 'placeholder',
          type: 'buttonEdge',
        },
      ]

      const result = EdgeFactory.removeButtonEdge('condition-1', edges, 'true')

      expect(result).toHaveLength(1)
      expect(result[0].id).toBe('button-condition-1-false')
    })

    it('removes specific false handle button edge', () => {
      const edges: EdgeType[] = [
        { id: 'button-condition-1-true', source: 'condition-1', target: 'placeholder', type: 'buttonEdge' },
        {
          id: 'button-condition-1-false',
          source: 'condition-1',
          target: 'placeholder',
          type: 'buttonEdge',
        },
      ]

      const result = EdgeFactory.removeButtonEdge('condition-1', edges, 'false')

      expect(result).toHaveLength(1)
      expect(result[0].id).toBe('button-condition-1-true')
    })

    it('removes specific done handle button edge for loop', () => {
      const edges: EdgeType[] = [
        { id: 'button-loop-1-done', source: 'loop-1', target: 'placeholder', type: 'buttonEdge' },
        { id: 'button-loop-1-loop', source: 'loop-1', target: 'placeholder', type: 'buttonEdge' },
      ]

      const result = EdgeFactory.removeButtonEdge('loop-1', edges, 'done')

      expect(result).toHaveLength(1)
      expect(result[0].id).toBe('button-loop-1-loop')
    })

    it('removes specific loop handle button edge for loop', () => {
      const edges: EdgeType[] = [
        { id: 'button-loop-1-done', source: 'loop-1', target: 'placeholder', type: 'buttonEdge' },
        { id: 'button-loop-1-loop', source: 'loop-1', target: 'placeholder', type: 'buttonEdge' },
      ]

      const result = EdgeFactory.removeButtonEdge('loop-1', edges, 'loop')

      expect(result).toHaveLength(1)
      expect(result[0].id).toBe('button-loop-1-done')
    })

    it('removes all loop button edges when no handle specified', () => {
      const edges: EdgeType[] = [
        { id: 'button-loop-1', source: 'loop-1', target: 'placeholder', type: 'buttonEdge' },
        { id: 'button-loop-1-done', source: 'loop-1', target: 'placeholder', type: 'buttonEdge' },
        { id: 'button-loop-1-loop', source: 'loop-1', target: 'placeholder', type: 'buttonEdge' },
        { id: 'edge-1', source: 'loop-1', target: 'task-1', type: 'default' },
      ]

      const result = EdgeFactory.removeButtonEdge('loop-1', edges)

      expect(result).toHaveLength(1)
      expect(result[0].id).toBe('edge-1')
    })

    it('removes specific approved handle button edge for approval node', () => {
      const edges: EdgeType[] = [
        {
          id: 'button-approval-1-approved',
          source: 'approval-1',
          target: 'placeholder',
          type: 'buttonEdge',
        },
        {
          id: 'button-approval-1-rejected',
          source: 'approval-1',
          target: 'placeholder',
          type: 'buttonEdge',
        },
      ]

      const result = EdgeFactory.removeButtonEdge('approval-1', edges, 'approved')

      expect(result).toHaveLength(1)
      expect(result[0].id).toBe('button-approval-1-rejected')
    })

    it('removes specific rejected handle button edge for approval node', () => {
      const edges: EdgeType[] = [
        {
          id: 'button-approval-1-approved',
          source: 'approval-1',
          target: 'placeholder',
          type: 'buttonEdge',
        },
        {
          id: 'button-approval-1-rejected',
          source: 'approval-1',
          target: 'placeholder',
          type: 'buttonEdge',
        },
      ]

      const result = EdgeFactory.removeButtonEdge('approval-1', edges, 'rejected')

      expect(result).toHaveLength(1)
      expect(result[0].id).toBe('button-approval-1-approved')
    })
  })

  describe('toEdgeConnection', () => {
    it('converts EdgeType to EdgeConnection', () => {
      const edge = {
        id: 'edge-1',
        source: 'node-1',
        target: 'node-2',
        sourceHandle: 'source',
        targetHandle: 'target',
        type: 'default',
        markerEnd: { type: 'arrowclosed' },
        data: { onAddNode: vi.fn() },
      } as unknown as EdgeType

      const result = EdgeFactory.toEdgeConnection(edge)

      expect(result).toEqual({
        id: 'edge-1',
        source: 'node-1',
        target: 'node-2',
        sourceHandle: 'source',
        targetHandle: 'target',
      })
      // Should not include markerEnd or data
      expect(result).not.toHaveProperty('markerEnd')
      expect(result).not.toHaveProperty('data')
    })

    it('handles edge without optional handles', () => {
      const edge: EdgeType = {
        id: 'edge-1',
        source: 'node-1',
        target: 'node-2',
        type: 'default',
      }

      const result = EdgeFactory.toEdgeConnection(edge)

      expect(result).toEqual({
        id: 'edge-1',
        source: 'node-1',
        target: 'node-2',
        sourceHandle: undefined,
        targetHandle: undefined,
      })
    })
  })

  describe('toEdgeConnections', () => {
    it('converts multiple EdgeTypes to EdgeConnections', () => {
      const edges: EdgeType[] = [
        {
          id: 'edge-1',
          source: 'node-1',
          target: 'node-2',
          sourceHandle: 'source',
          targetHandle: 'target',
          type: 'default',
        },
        {
          id: 'edge-2',
          source: 'node-2',
          target: 'node-3',
          sourceHandle: 'source',
          targetHandle: 'target',
          type: 'default',
        },
      ]

      const result = EdgeFactory.toEdgeConnections(edges)

      expect(result).toHaveLength(2)
      expect(result[0]).toEqual({
        id: 'edge-1',
        source: 'node-1',
        target: 'node-2',
        sourceHandle: 'source',
        targetHandle: 'target',
      })
      expect(result[1]).toEqual({
        id: 'edge-2',
        source: 'node-2',
        target: 'node-3',
        sourceHandle: 'source',
        targetHandle: 'target',
      })
    })

    it('handles empty array', () => {
      const result = EdgeFactory.toEdgeConnections([])
      expect(result).toEqual([])
    })
  })
})
