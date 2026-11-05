import { describe, expect, it, vi } from 'vitest'

import type { EdgeType } from '../utils/workflowToGraph'

import { projectEdgeActiveState } from './useEdgeActiveState'

vi.mock('../utils/workflowToGraph', () => ({
  markerEnd: 'url(#arrow)',
}))

function project(edges: EdgeType[], options: Partial<Parameters<typeof projectEdgeActiveState>[1]> = {}) {
  return projectEdgeActiveState(edges, {
    activeEdgeId: null,
    activeEdgeButtonNodeId: null,
    activeEdgeButtonHandle: null,
    isInitialized: true,
    ...options,
  })
}

describe('projectEdgeActiveState', () => {
  it('adds markers and the add-node callback to default and loop edges', () => {
    const onAddNodeFromEdge = vi.fn()
    const edges = [
      { id: 'default', type: 'default', source: 'a', target: 'b' },
      { id: 'back', type: 'loopBack', source: 'b', target: 'a' },
      { id: 'out', type: 'loopOutgoing', source: 'a', target: 'b' },
      { id: 'done', type: 'loopDone', source: 'a', target: 'b' },
    ] as EdgeType[]

    const result = project(edges, { onAddNodeFromEdge })

    expect(result).toHaveLength(4)
    result.forEach((edge) => {
      expect(edge.markerEnd).toBe('url(#arrow)')
      expect(edge.data?.onAddNode).toBe(onAddNodeFromEdge)
      expect(edge.data?.isActive).toBeUndefined()
    })
  })

  it('uses activeEdgeId and preserves a pending edge active state', () => {
    const result = project(
      [
        { id: 'edge-1', type: 'default', source: 'a', target: 'b' },
        { id: 'edge-2', type: 'default', source: 'b', target: 'c', data: { isPending: true } },
      ] as EdgeType[],
      { activeEdgeId: 'edge-1' }
    )

    expect(result.map((edge) => edge.data?.isActive)).toEqual([true, true])
  })

  it('activates button edges for their source handle', () => {
    const result = project(
      [
        { id: 'button-node-1', type: 'buttonEdge', source: 'node-1', sourceHandle: 'source' },
        { id: 'button-node-1-true', type: 'buttonEdge', source: 'node-1', sourceHandle: 'true' },
      ] as EdgeType[],
      { activeEdgeButtonNodeId: 'node-1', activeEdgeButtonHandle: 'true' }
    )

    expect(result.map((edge) => edge.data?.isActive)).toEqual([false, true])
  })

  it('does not project button edge state before initialization', () => {
    const edges = [{ id: 'button-node-1', type: 'buttonEdge', source: 'node-1', sourceHandle: 'source' }] as EdgeType[]

    expect(project(edges, { activeEdgeButtonNodeId: 'node-1', isInitialized: false })).toBe(edges)
  })

  it('preserves edge references when all projected fields already match', () => {
    const callback = vi.fn()
    const edges = [
      {
        id: 'edge-1',
        type: 'default',
        source: 'a',
        target: 'b',
        markerEnd: 'url(#arrow)',
        data: { onAddNode: callback, isActive: true },
      },
    ] as unknown as EdgeType[]

    expect(project(edges, { activeEdgeId: 'edge-1', onAddNodeFromEdge: callback })).toBe(edges)
  })
})
