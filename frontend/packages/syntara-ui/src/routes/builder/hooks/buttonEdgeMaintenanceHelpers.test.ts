import { describe, expect, it } from 'vitest'

import type { NodeType } from '../../workflows/canvas/nodes/NodeType'

import {
  type ButtonEdgeFilterContext,
  type ProcessMultiHandleNodeOptions,
  createButtonEdgePlaceholderNode,
  getKeptButtonEdge,
  mergeNewPlaceholderNodes,
  processMultiHandleNode,
} from './buttonEdgeMaintenanceHelpers'

function makeNode(id: string, x = 0, y = 0): NodeType {
  return { id, type: 'task', position: { x, y }, data: {} } as NodeType
}

describe('processMultiHandleNode', () => {
  const baseOptions = (): Omit<ProcessMultiHandleNodeOptions, 'node' | 'handles' | 'handlePositions'> => ({
    connectedHandles: new Map(),
    pendingEdge: null,
    nodes: [],
    handlesNeedingButtonEdges: [],
    placeholderNodesToAdd: [],
  })

  it('adds unconnected handles to handlesNeedingButtonEdges', () => {
    const opts: ProcessMultiHandleNodeOptions = {
      ...baseOptions(),
      node: makeNode('cond-1', 100, 200),
      handles: ['true', 'false'],
      handlePositions: { true: { yOffset: -30 }, false: { yOffset: 30 } },
    }

    processMultiHandleNode(opts)

    expect(opts.handlesNeedingButtonEdges).toEqual([
      { nodeId: 'cond-1', handleId: 'true' },
      { nodeId: 'cond-1', handleId: 'false' },
    ])
  })

  it('creates placeholder nodes for unconnected handles', () => {
    const opts: ProcessMultiHandleNodeOptions = {
      ...baseOptions(),
      node: makeNode('cond-1', 100, 200),
      handles: ['true', 'false'],
      handlePositions: { true: { yOffset: -30 }, false: { yOffset: 30 } },
    }

    processMultiHandleNode(opts)

    expect(opts.placeholderNodesToAdd).toHaveLength(2)
    expect(opts.placeholderNodesToAdd[0].id).toBe('placeholder-cond-1-true')
    expect(opts.placeholderNodesToAdd[0].position).toEqual({ x: 300, y: 170 })
    expect(opts.placeholderNodesToAdd[0].style).toEqual({ pointerEvents: 'none' })
    expect(opts.placeholderNodesToAdd[1].id).toBe('placeholder-cond-1-false')
    expect(opts.placeholderNodesToAdd[1].position).toEqual({ x: 300, y: 230 })
  })

  it('skips handles that are already connected', () => {
    const connected = new Map([['cond-1', new Set(['true'])]])
    const opts: ProcessMultiHandleNodeOptions = {
      ...baseOptions(),
      connectedHandles: connected,
      node: makeNode('cond-1'),
      handles: ['true', 'false'],
      handlePositions: { true: { yOffset: -30 }, false: { yOffset: 30 } },
    }

    processMultiHandleNode(opts)

    expect(opts.handlesNeedingButtonEdges).toEqual([{ nodeId: 'cond-1', handleId: 'false' }])
  })

  it('skips handles with pending edge', () => {
    const opts: ProcessMultiHandleNodeOptions = {
      ...baseOptions(),
      pendingEdge: { sourceNodeId: 'cond-1', sourceHandle: 'true' },
      node: makeNode('cond-1'),
      handles: ['true', 'false'],
      handlePositions: { true: { yOffset: -30 }, false: { yOffset: 30 } },
    }

    processMultiHandleNode(opts)

    expect(opts.handlesNeedingButtonEdges).toEqual([{ nodeId: 'cond-1', handleId: 'false' }])
  })

  it('does not add placeholder if one already exists in nodes', () => {
    const existing = makeNode('placeholder-cond-1-true')
    const opts: ProcessMultiHandleNodeOptions = {
      ...baseOptions(),
      nodes: [existing],
      node: makeNode('cond-1'),
      handles: ['true'],
      handlePositions: { true: { yOffset: -30 } },
    }

    processMultiHandleNode(opts)

    expect(opts.handlesNeedingButtonEdges).toHaveLength(1)
    expect(opts.placeholderNodesToAdd).toHaveLength(0)
  })

  it('uses custom xOffset when provided', () => {
    const opts: ProcessMultiHandleNodeOptions = {
      ...baseOptions(),
      node: makeNode('n1', 50, 60),
      handles: ['done'],
      handlePositions: { done: { yOffset: -30, xOffset: 150 } },
    }

    processMultiHandleNode(opts)

    expect(opts.placeholderNodesToAdd[0].position).toEqual({ x: 200, y: 30 })
  })
})

describe('mergeNewPlaceholderNodes', () => {
  it('adds new placeholder nodes', () => {
    const current = [makeNode('a')]
    const placeholders = [createButtonEdgePlaceholderNode({ id: 'placeholder-b', position: { x: 0, y: 0 } })]

    const result = mergeNewPlaceholderNodes(placeholders, current)

    expect(result).toHaveLength(2)
    expect(result.map((n) => n.id)).toEqual(['a', 'placeholder-b'])
  })

  it('skips placeholders that already exist', () => {
    const existing = createButtonEdgePlaceholderNode({ id: 'placeholder-b', position: { x: 1, y: 1 } })
    const current: NodeType[] = [makeNode('a'), existing]
    const placeholders = [createButtonEdgePlaceholderNode({ id: 'placeholder-b', position: { x: 0, y: 0 } })]

    const result = mergeNewPlaceholderNodes(placeholders, current)

    expect(result).toBe(current)
  })

  it('returns same array reference when nothing to add', () => {
    const current = [makeNode('a')]
    const result = mergeNewPlaceholderNodes([], current)
    expect(result).toBe(current)
  })
})

describe('getKeptButtonEdge', () => {
  const emptyCtx: ButtonEdgeFilterContext = {
    conditionHandles: [],
    loopHandles: [],
    approvalHandles: [],
    switchHandles: [],
    regularNodeIds: [],
    activeNodeId: null,
    activeHandle: null,
  }

  it('returns null for unrecognized handle', () => {
    const edge = { source: 'n1', sourceHandle: 'unknown', data: {} }
    expect(getKeptButtonEdge(edge, emptyCtx)).toBeNull()
  })

  it('keeps condition true handle when needed', () => {
    const ctx: ButtonEdgeFilterContext = {
      ...emptyCtx,
      conditionHandles: [{ nodeId: 'c1', handleId: 'true' }],
    }
    const edge = { source: 'c1', sourceHandle: 'true', data: {} }
    const result = getKeptButtonEdge(edge, ctx)
    expect(result).not.toBeNull()
    expect(result!.data.isActive).toBe(false)
  })

  it('removes condition handle when not needed', () => {
    const edge = { source: 'c1', sourceHandle: 'false', data: {} }
    expect(getKeptButtonEdge(edge, emptyCtx)).toBeNull()
  })

  it('sets isActive for condition handle', () => {
    const ctx: ButtonEdgeFilterContext = {
      ...emptyCtx,
      conditionHandles: [{ nodeId: 'c1', handleId: 'true' }],
      activeNodeId: 'c1',
      activeHandle: 'true',
    }
    const edge = { source: 'c1', sourceHandle: 'true', data: {} }
    const result = getKeptButtonEdge(edge, ctx)
    expect(result!.data.isActive).toBe(true)
  })

  it('keeps loop done handle when needed', () => {
    const ctx: ButtonEdgeFilterContext = {
      ...emptyCtx,
      loopHandles: [{ nodeId: 'l1', handleId: 'done' }],
    }
    const edge = { source: 'l1', sourceHandle: 'done', data: {} }
    expect(getKeptButtonEdge(edge, ctx)).not.toBeNull()
  })

  it('keeps loop handle when needed', () => {
    const ctx: ButtonEdgeFilterContext = {
      ...emptyCtx,
      loopHandles: [{ nodeId: 'l1', handleId: 'loop' }],
    }
    const edge = { source: 'l1', sourceHandle: 'loop', data: {} }
    expect(getKeptButtonEdge(edge, ctx)).not.toBeNull()
  })

  it('removes loop handle when not needed', () => {
    const edge = { source: 'l1', sourceHandle: 'done', data: {} }
    expect(getKeptButtonEdge(edge, emptyCtx)).toBeNull()
  })

  it('keeps approval approved handle when needed', () => {
    const ctx: ButtonEdgeFilterContext = {
      ...emptyCtx,
      approvalHandles: [{ nodeId: 'a1', handleId: 'approved' }],
    }
    const edge = { source: 'a1', sourceHandle: 'approved', data: {} }
    expect(getKeptButtonEdge(edge, ctx)).not.toBeNull()
  })

  it('keeps approval rejected handle when needed', () => {
    const ctx: ButtonEdgeFilterContext = {
      ...emptyCtx,
      approvalHandles: [{ nodeId: 'a1', handleId: 'rejected' }],
    }
    const edge = { source: 'a1', sourceHandle: 'rejected', data: {} }
    expect(getKeptButtonEdge(edge, ctx)).not.toBeNull()
  })

  it('removes approval handle when not needed', () => {
    const edge = { source: 'a1', sourceHandle: 'approved', data: {} }
    expect(getKeptButtonEdge(edge, emptyCtx)).toBeNull()
  })

  it('keeps regular source handle for known nodes', () => {
    const ctx: ButtonEdgeFilterContext = {
      ...emptyCtx,
      regularNodeIds: ['n1'],
    }
    const edge = { source: 'n1', sourceHandle: 'source', data: {} }
    expect(getKeptButtonEdge(edge, ctx)).not.toBeNull()
  })

  it('keeps edge with null sourceHandle for known regular nodes', () => {
    const ctx: ButtonEdgeFilterContext = {
      ...emptyCtx,
      regularNodeIds: ['n1'],
    }
    const edge = { source: 'n1', sourceHandle: null, data: {} }
    expect(getKeptButtonEdge(edge, ctx)).not.toBeNull()
  })

  it('sets isActive for regular source handle', () => {
    const ctx: ButtonEdgeFilterContext = {
      ...emptyCtx,
      regularNodeIds: ['n1'],
      activeNodeId: 'n1',
      activeHandle: 'source',
    }
    const edge = { source: 'n1', sourceHandle: 'source', data: {} }
    const result = getKeptButtonEdge(edge, ctx)
    expect(result!.data.isActive).toBe(true)
  })

  it('sets isActive for regular node with null activeHandle', () => {
    const ctx: ButtonEdgeFilterContext = {
      ...emptyCtx,
      regularNodeIds: ['n1'],
      activeNodeId: 'n1',
      activeHandle: null,
    }
    const edge = { source: 'n1', sourceHandle: 'source', data: {} }
    const result = getKeptButtonEdge(edge, ctx)
    expect(result!.data.isActive).toBe(true)
  })

  it('removes regular source handle for unknown nodes', () => {
    const edge = { source: 'unknown', sourceHandle: 'source', data: {} }
    expect(getKeptButtonEdge(edge, emptyCtx)).toBeNull()
  })

  it('sets isActive on loop handle', () => {
    const ctx: ButtonEdgeFilterContext = {
      ...emptyCtx,
      loopHandles: [{ nodeId: 'l1', handleId: 'done' }],
      activeNodeId: 'l1',
      activeHandle: 'done',
    }
    const edge = { source: 'l1', sourceHandle: 'done', data: {} }
    const result = getKeptButtonEdge(edge, ctx)
    expect(result!.data.isActive).toBe(true)
  })

  it('sets isActive on approval handle', () => {
    const ctx: ButtonEdgeFilterContext = {
      ...emptyCtx,
      approvalHandles: [{ nodeId: 'a1', handleId: 'approved' }],
      activeNodeId: 'a1',
      activeHandle: 'approved',
    }
    const edge = { source: 'a1', sourceHandle: 'approved', data: {} }
    const result = getKeptButtonEdge(edge, ctx)
    expect(result!.data.isActive).toBe(true)
  })
})
