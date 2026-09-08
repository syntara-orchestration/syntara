import { renderHook } from '@testing-library/react'
import type { Edge, Node } from '@xyflow/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAdjacentNodes } from './useAdjacentNodes'

const flowGraph = vi.hoisted(() => ({
  edges: [] as Edge[],
  nodes: [] as Node[],
}))

vi.mock('@xyflow/react', () => ({
  useStore: (selector: (state: { edges: Edge[]; nodes: Node[] }) => unknown) =>
    selector({ edges: flowGraph.edges, nodes: flowGraph.nodes }),
}))

describe('useAdjacentNodes', () => {
  beforeEach(() => {
    flowGraph.edges = []
    flowGraph.nodes = []
  })

  it('returns empty arrays when nodeId is undefined', () => {
    const { result } = renderHook(() => useAdjacentNodes(undefined))
    expect(result.current).toEqual({ upstream: [], downstream: [] })
  })

  it('reads neighbors from the React Flow graph', () => {
    flowGraph.nodes = [
      {
        id: 'trigger-0',
        type: 'trigger',
        position: { x: 0, y: 0 },
        data: { name: 'Manual Trigger', triggerType: 'manual_trigger' },
      },
      {
        id: 'check-value',
        type: 'task',
        position: { x: 0, y: 0 },
        data: { name: 'Check Value', type: 'script' },
      },
    ]
    flowGraph.edges = [{ id: 'e1', source: 'trigger-0', target: 'check-value', type: 'default' }]

    const { result } = renderHook(() => useAdjacentNodes('trigger-0'))

    expect(result.current.downstream).toMatchObject([
      { id: 'check-value', name: 'Check Value', type: 'script', iconId: 'action-script' },
    ])
  })

  it('memoizes result when edges and nodes do not change', () => {
    flowGraph.nodes = [
      { id: 'node-a', position: { x: 0, y: 0 }, data: { name: 'A' } },
      { id: 'node-b', position: { x: 0, y: 0 }, data: { name: 'B' } },
    ]
    flowGraph.edges = [{ id: 'e1', source: 'node-a', target: 'node-b', type: 'default' }]

    const { result, rerender } = renderHook(() => useAdjacentNodes('node-b'))
    const firstResult = result.current

    rerender()

    expect(result.current).toBe(firstResult)
  })

  it('recomputes when edges or nodes change', () => {
    flowGraph.nodes = [
      { id: 'node-a', position: { x: 0, y: 0 }, data: { name: 'A' } },
      { id: 'node-b', position: { x: 0, y: 0 }, data: { name: 'B' } },
    ]
    flowGraph.edges = [{ id: 'e1', source: 'node-a', target: 'node-b', type: 'default' }]

    const { result, rerender } = renderHook(() => useAdjacentNodes('node-a'))
    const firstResult = result.current

    expect(firstResult.downstream).toMatchObject([{ id: 'node-b', name: 'B', type: 'unknown' }])

    flowGraph.nodes = [...flowGraph.nodes, { id: 'node-c', position: { x: 0, y: 0 }, data: { name: 'C' } }]
    flowGraph.edges = [...flowGraph.edges, { id: 'e2', source: 'node-a', target: 'node-c', type: 'default' }]
    rerender()

    expect(result.current).not.toBe(firstResult)
    expect(result.current.downstream).toMatchObject([
      { id: 'node-b', name: 'B', type: 'unknown' },
      { id: 'node-c', name: 'C', type: 'unknown' },
    ])
  })
})
