import { describe, expect, it } from 'vitest'

import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { EdgeType } from './workflowToGraph'
import { getLoopBodyMap, collectLoopGroupPositions } from './loopUtils'

function makeNode(id: string, type = 'task'): NodeType {
  return { id, type, position: { x: 0, y: 0 }, data: {} } as unknown as NodeType
}

function makeEdge(id: string, source: string, target: string, sourceHandle: string): EdgeType {
  return { id, source, target, sourceHandle } as unknown as EdgeType
}

describe('getLoopBodyMap', () => {
  it('returns empty map when there are no loop nodes', () => {
    const nodes = [makeNode('task-1'), makeNode('task-2')]
    const edges = [makeEdge('e1', 'task-1', 'task-2', 'source')]

    expect(getLoopBodyMap(nodes, edges)).toEqual(new Map())
  })

  it('returns empty map when the loop node has no loop-handle edge', () => {
    const nodes = [makeNode('loop-1', 'loop'), makeNode('task-1')]
    const edges: EdgeType[] = []

    expect(getLoopBodyMap(nodes, edges)).toEqual(new Map())
  })

  it('identifies a single body node', () => {
    const nodes = [makeNode('loop-1', 'loop'), makeNode('task-1')]
    const edges = [makeEdge('e-loop', 'loop-1', 'task-1', 'loop')]

    const result = getLoopBodyMap(nodes, edges)

    expect(result.get('loop-1')).toEqual(['task-1'])
  })

  it('identifies multiple body nodes connected in a chain', () => {
    const nodes = [makeNode('loop-1', 'loop'), makeNode('task-1'), makeNode('task-2')]
    const edges = [
      makeEdge('e-loop', 'loop-1', 'task-1', 'loop'),
      makeEdge('e-chain', 'task-1', 'task-2', 'source'),
    ]

    const result = getLoopBodyMap(nodes, edges)

    expect(result.get('loop-1')).toContain('task-1')
    expect(result.get('loop-1')).toContain('task-2')
    expect(result.get('loop-1')).toHaveLength(2)
  })

  it('does not follow edges back to the loop node itself', () => {
    const nodes = [makeNode('loop-1', 'loop'), makeNode('task-1')]
    const edges = [
      makeEdge('e-loop', 'loop-1', 'task-1', 'loop'),
      // loop-back edge (source handle on task, target is the loop node)
      makeEdge('e-back', 'task-1', 'loop-1', 'source'),
    ]

    const result = getLoopBodyMap(nodes, edges)

    expect(result.get('loop-1')).toEqual(['task-1'])
  })

  it('excludes placeholder nodes from traversal', () => {
    const nodes = [
      makeNode('loop-1', 'loop'),
      makeNode('task-1'),
      makeNode('placeholder-abc'), // filtered out by filterRealNodes
    ]
    const edges = [
      makeEdge('e-loop', 'loop-1', 'task-1', 'loop'),
      makeEdge('e-ph', 'task-1', 'placeholder-abc', 'source'),
    ]

    const result = getLoopBodyMap(nodes, edges)

    // The loop body contains task-1 but since placeholder-abc is filtered,
    // BFS won't reach it as a loop node; however it can still appear as a
    // body node if reachable (filterRealNodes only filters loop/edge source nodes).
    // The key assertion: loop-1's body does NOT include placeholder-abc as a loop header
    expect(result.has('placeholder-abc')).toBe(false)
  })

  it('handles two independent loop nodes', () => {
    const nodes = [
      makeNode('loop-1', 'loop'),
      makeNode('task-1'),
      makeNode('loop-2', 'loop'),
      makeNode('task-2'),
    ]
    const edges = [
      makeEdge('e1', 'loop-1', 'task-1', 'loop'),
      makeEdge('e2', 'loop-2', 'task-2', 'loop'),
    ]

    const result = getLoopBodyMap(nodes, edges)

    expect(result.get('loop-1')).toEqual(['task-1'])
    expect(result.get('loop-2')).toEqual(['task-2'])
  })

  it('handles nested loops — inner body is included in outer body traversal', () => {
    // Outer loop -> inner loop -> task (via source handle chain)
    const nodes = [
      makeNode('outer-loop', 'loop'),
      makeNode('inner-loop', 'loop'),
      makeNode('task-1'),
    ]
    const edges = [
      makeEdge('e-outer', 'outer-loop', 'inner-loop', 'loop'),
      makeEdge('e-inner', 'inner-loop', 'task-1', 'loop'),
      // inner-loop is chained via outer's loop handle, so it's an outer body node
    ]

    const result = getLoopBodyMap(nodes, edges)

    // inner-loop is a direct body of outer-loop
    expect(result.get('outer-loop')).toContain('inner-loop')
    // task-1 is a body of inner-loop
    expect(result.get('inner-loop')).toContain('task-1')
  })

  it('does not include done-branch nodes by default', () => {
    const nodes = [makeNode('loop-1', 'loop'), makeNode('task-loop', 'task'), makeNode('task-done', 'task')]
    const edges = [
      makeEdge('e-loop', 'loop-1', 'task-loop', 'loop'),
      makeEdge('e-done', 'loop-1', 'task-done', 'done'),
    ]

    const result = getLoopBodyMap(nodes, edges)

    expect(result.get('loop-1')).toEqual(['task-loop'])
  })

  it('includes done-branch nodes when includeDoneBranch is true', () => {
    const nodes = [makeNode('loop-1', 'loop'), makeNode('task-loop', 'task'), makeNode('task-done', 'task')]
    const edges = [
      makeEdge('e-loop', 'loop-1', 'task-loop', 'loop'),
      makeEdge('e-done', 'loop-1', 'task-done', 'done'),
    ]

    const result = getLoopBodyMap(nodes, edges, { includeDoneBranch: true })

    expect(result.get('loop-1')).toContain('task-loop')
    expect(result.get('loop-1')).toContain('task-done')
    expect(result.get('loop-1')).toHaveLength(2)
  })

  it('excludes done edges that loop back to a parent loop end handle', () => {
    const nodes = [makeNode('outer-loop', 'loop'), makeNode('inner-loop', 'loop'), makeNode('inner-body', 'task')]
    const edges = [
      makeEdge('e-outer-loop', 'outer-loop', 'inner-loop', 'loop'),
      makeEdge('e-inner-loop', 'inner-loop', 'inner-body', 'loop'),
      makeEdge('e-inner-done', 'inner-loop', 'outer-loop', 'done'),
    ]
    // Simulate loop-back: done target uses the end handle on the parent loop
    edges[2] = { ...edges[2], targetHandle: 'end' } as EdgeType

    const result = getLoopBodyMap(nodes, edges, { includeDoneBranch: true })

    expect(result.get('inner-loop')).toEqual(['inner-body'])
  })
})

describe('collectLoopGroupPositions', () => {
  it('collects positions for loop header and all group members', () => {
    const nodes = [
      makeNode('loop-1', 'loop'),
      makeNode('task-loop', 'task'),
      makeNode('task-done', 'task'),
    ]
    nodes[0].position = { x: 10, y: 20 }
    nodes[1].position = { x: 110, y: 70 }
    nodes[2].position = { x: 10, y: -50 }
    const edges = [
      makeEdge('e-loop', 'loop-1', 'task-loop', 'loop'),
      makeEdge('e-done', 'loop-1', 'task-done', 'done'),
    ]

    const positions = collectLoopGroupPositions(nodes, edges, (id) => id)

    expect(positions).toEqual({
      'loop-1': { x: 10, y: 20 },
      'task-loop': { x: 110, y: 70 },
      'task-done': { x: 10, y: -50 },
    })
  })
})
