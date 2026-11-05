import { EdgeHandleEnum } from '@syntara/contracts'
import { describe, expect, it, vi } from 'vitest'

import { FlowNodeType } from '../../../constants'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { PendingEdge } from '../types'
import { getButtonEdgeId, getPlaceholderNodeId } from '../utils/edgeHelpers'
import type { EdgeType } from '../utils/workflowToGraph'

import { projectPendingEdgeGraph } from './usePendingEdgeManagement'

vi.mock('../utils/workflowToGraph', () => ({
  markerEnd: 'url(#arrow)',
}))

const node = (id: string, type: string = FlowNodeType.TASK): NodeType =>
  ({ id, type, position: { x: 10, y: 20 }, data: {} }) as unknown as NodeType

const buttonEdge = (id: string, source: string, handle: string): EdgeType => ({
  id,
  source,
  sourceHandle: handle,
  target: 'placeholder',
  type: 'buttonEdge',
})

describe('projectPendingEdgeGraph', () => {
  it('does not add temporary graph items before initialization', () => {
    const nodes = [node('task-1')]
    const edges = [{ id: 'edge-1', source: 'task-1', target: 'task-2' }] as EdgeType[]
    const pendingEdge: PendingEdge = { sourceNodeId: 'task-1', x: 100, y: 50 }

    expect(projectPendingEdgeGraph(nodes, edges, pendingEdge, false)).toEqual({ nodes, edges })
  })

  it('projects a pending target and edge at the dragged position', () => {
    const pendingEdge: PendingEdge = { sourceNodeId: 'task-1', x: 100, y: 50 }
    const result = projectPendingEdgeGraph([node('task-1')], [], pendingEdge, true)

    expect(result.nodes).toContainEqual({
      id: 'pending-target-task-1',
      type: FlowNodeType.PLACEHOLDER,
      position: { x: 95, y: 45 },
      data: {},
      draggable: false,
      selectable: false,
    })
    expect(result.edges).toContainEqual({
      id: 'pending-task-1',
      source: 'task-1',
      sourceHandle: EdgeHandleEnum.SOURCE,
      target: 'pending-target-task-1',
      targetHandle: EdgeHandleEnum.TARGET,
      type: 'default',
      selectable: false,
      markerEnd: 'url(#arrow)',
      data: { isPending: true, isActive: true },
    })
  })

  it('removes the matching per-handle button edge and placeholder', () => {
    const pendingEdge: PendingEdge = {
      sourceNodeId: 'condition-1',
      sourceHandle: EdgeHandleEnum.TRUE,
      x: 100,
      y: 50,
    }
    const selectedButtonEdgeId = getButtonEdgeId('condition-1', EdgeHandleEnum.TRUE)
    const otherButtonEdgeId = getButtonEdgeId('condition-1', EdgeHandleEnum.FALSE)
    const selectedPlaceholderId = getPlaceholderNodeId('condition-1', EdgeHandleEnum.TRUE)
    const result = projectPendingEdgeGraph(
      [node('condition-1', FlowNodeType.CONDITION), node(selectedPlaceholderId), node('placeholder-other')],
      [
        buttonEdge(selectedButtonEdgeId, 'condition-1', EdgeHandleEnum.TRUE),
        buttonEdge(otherButtonEdgeId, 'condition-1', EdgeHandleEnum.FALSE),
      ],
      pendingEdge,
      true
    )

    expect(result.nodes.some((item) => item.id === selectedPlaceholderId)).toBe(false)
    expect(result.nodes.some((item) => item.id === 'placeholder-other')).toBe(true)
    expect(result.edges.some((item) => item.id === selectedButtonEdgeId)).toBe(false)
    expect(result.edges.some((item) => item.id === otherButtonEdgeId)).toBe(true)
  })

  it('cleans temporary items when the pending edge is cancelled', () => {
    const nodes = [node('task-1'), node('pending-target-task-1', FlowNodeType.PLACEHOLDER), node('placeholder-task-1')]
    const edges = [
      { id: 'real-edge', source: 'task-1', target: 'task-2' },
      { id: 'pending-task-1', source: 'task-1', target: 'pending-target-task-1' },
    ] as EdgeType[]
    const result = projectPendingEdgeGraph(nodes, edges, null, true)

    expect(result.nodes.map((item) => item.id)).toEqual(['task-1', 'placeholder-task-1'])
    expect(result.edges.map((item) => item.id)).toEqual(['real-edge'])
  })

  it('updates pending target position when the drag moves', () => {
    const first = projectPendingEdgeGraph([node('task-1')], [], { sourceNodeId: 'task-1', x: 10, y: 20 }, true)
    const second = projectPendingEdgeGraph([node('task-1')], [], { sourceNodeId: 'task-1', x: 30, y: 45 }, true)

    expect(first.nodes[1].position).toEqual({ x: 5, y: 15 })
    expect(second.nodes[1].position).toEqual({ x: 25, y: 40 })
  })
})
