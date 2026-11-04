import { describe, expect, it } from 'vitest'

import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { EdgeType } from '../utils/workflowToGraph'

import { getNodeUpdatePlan, keepCurrentNodesAndPlaceholders, mergeNodesPreservingPositions } from './nodeUpdates'

function node(id: string, data: Record<string, unknown> = {}, type = 'task'): NodeType {
  return { id, type, data, position: { x: 0, y: 0 } } as unknown as NodeType
}

function edge(id: string, source = 'node-1', target = 'node-2'): EdgeType {
  return { id, source, target }
}

function plan(overrides: Partial<Parameters<typeof getNodeUpdatePlan>[0]> = {}) {
  const initialNodes = [node('node-1', { name: 'before' })]
  const initialEdges = [edge('edge-1')]

  return getNodeUpdatePlan({
    initialNodes,
    initialEdges,
    previousNodeIds: new Set(['node-1']),
    previousInitialNodes: initialNodes,
    previousInitialEdges: initialEdges,
    newlyAddedNodeIds: new Set(),
    isInitialized: true,
    ...overrides,
  })
}

describe('mergeNodesPreservingPositions', () => {
  it('preserves positions, dimensions, and validation errors on existing nodes', () => {
    const previousNodes = [
      {
        ...node('node-1', { __validationError: true, name: 'before' }),
        position: { x: 100, y: 200 },
        measured: { width: 50 },
      },
    ]

    const result = mergeNodesPreservingPositions(previousNodes, [node('node-1', { name: 'after' })])

    expect(result[0]).toMatchObject({
      position: { x: 100, y: 200 },
      measured: { width: 50 },
      data: { __validationError: true, name: 'after' },
    })
  })

  it('keeps non-initial nodes when reconciling updated nodes', () => {
    const previousNodes = [node('node-1'), node('placeholder-1', {}, 'placeholder')]

    const result = mergeNodesPreservingPositions(previousNodes, [node('node-1', { changed: true })])

    expect(result.map((item) => item.id)).toEqual(['node-1', 'placeholder-1'])
  })
})

describe('keepCurrentNodesAndPlaceholders', () => {
  it('filters stale nodes but preserves placeholders', () => {
    const result = keepCurrentNodesAndPlaceholders(
      [node('node-1'), node('placeholder-1', {}, 'placeholder'), node('stale-node')],
      [node('node-1')]
    )

    expect(result.map((item) => item.id)).toEqual(['node-1', 'placeholder-1'])
  })
})

describe('getNodeUpdatePlan', () => {
  it('skips structurally unchanged graph data', () => {
    expect(plan({ initialNodes: [node('node-1', { name: 'before' })] })).toEqual({ type: 'none' })
  })

  it('returns a node-addition plan and includes changed edges', () => {
    const initialNodes = [node('node-1'), node('node-2')]
    const initialEdges = [edge('edge-1'), edge('edge-2', 'node-1', 'node-2')]

    expect(
      plan({
        initialNodes,
        initialEdges,
      })
    ).toMatchObject({ type: 'add-nodes', newNodeIds: ['node-2'], edgesDataChanged: true })
  })

  it('recognizes additions already being positioned', () => {
    const initialNodes = [node('node-1'), node('node-2')]

    expect(
      plan({
        initialNodes,
        newlyAddedNodeIds: new Set(['node-2']),
      })
    ).toMatchObject({ type: 'already-tracked-addition' })
  })

  it('returns a deletion plan when prior nodes disappeared', () => {
    const previousInitialNodes = [node('node-1'), node('node-2')]

    expect(
      plan({
        previousNodeIds: new Set(['node-1', 'node-2']),
        previousInitialNodes,
      })
    ).toMatchObject({ type: 'delete-nodes' })
  })

  it('returns a data-update plan when existing node data changes', () => {
    expect(
      plan({
        initialNodes: [node('node-1', { name: 'after' })],
      })
    ).toEqual({ type: 'update-node-data' })
  })

  it('returns an initialization plan when graph data arrives before initialization', () => {
    const initialNodes = [node('node-1')]

    expect(
      plan({
        initialNodes,
        previousInitialNodes: [],
        isInitialized: false,
      })
    ).toMatchObject({ type: 'initialize-nodes', currentNodeIds: new Set(['node-1']) })
  })

  it('updates comparison snapshots without replacing nodes for edge-only changes', () => {
    expect(
      plan({
        initialEdges: [edge('edge-2')],
      })
    ).toEqual({ type: 'update-snapshots-only' })
  })
})
