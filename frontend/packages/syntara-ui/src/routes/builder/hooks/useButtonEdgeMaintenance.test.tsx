import { EdgeHandleEnum } from '@syntara/contracts'
import { describe, expect, it, vi } from 'vitest'

import { FlowNodeType } from '../../../constants'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { PendingEdge } from '../types'
import type { EdgeType } from '../utils/workflowToGraph'

import { projectButtonEdgeMaintenance } from './useButtonEdgeMaintenance'

function node(
  id: string,
  type: string = FlowNodeType.TASK,
  position = { x: 20, y: 40 },
  data: Record<string, unknown> = {}
): NodeType {
  return { id, type, position, data } as unknown as NodeType
}

function edge(id: string, source: string, target: string, sourceHandle?: string): EdgeType {
  return { id, source, target, sourceHandle, type: 'default' }
}

function project(
  nodes: NodeType[],
  edges: EdgeType[] = [],
  options: Partial<Parameters<typeof projectButtonEdgeMaintenance>[0]> = {}
) {
  return projectButtonEdgeMaintenance({
    nodes,
    edges,
    isInitialized: true,
    activeEdgeButtonNodeId: null,
    activeEdgeButtonHandle: null,
    pendingEdge: null,
    executionStatus: null,
    ...options,
  })
}

describe('projectButtonEdgeMaintenance', () => {
  it('leaves controlled graph state unchanged before initialization', () => {
    const nodes = [node('task-1')]
    const edges = [edge('edge-1', 'task-1', 'task-2')]

    expect(project(nodes, edges, { isInitialized: false })).toEqual({ nodes, edges })
  })

  it('projects a button edge and placeholder for a node without an outgoing connection', () => {
    const onAddNodeFromEdge = vi.fn()
    const result = project([node('task-1')], [], { onAddNodeFromEdge })
    const buttonEdge = result.edges.find((item) => item.id === 'button-task-1')
    const placeholder = result.nodes.find((item) => item.id === 'placeholder-task-1')

    expect(buttonEdge).toMatchObject({
      source: 'task-1',
      sourceHandle: EdgeHandleEnum.SOURCE,
      target: 'placeholder-task-1',
      type: 'buttonEdge',
      data: { isActive: false },
    })
    expect(buttonEdge?.data?.onButtonClick).toBeDefined()
    expect(placeholder?.position).toEqual({ x: 220, y: 40 })
    expect(result.nodes[0].className).toContain('has-button-edge')
  })

  it('does not add a source button when a real outgoing edge exists', () => {
    const result = project([node('task-1'), node('task-2')], [edge('edge-1', 'task-1', 'task-2')])

    expect(result.edges.some((item) => item.id === 'button-task-1')).toBe(false)
    expect(result.edges.some((item) => item.id === 'button-task-2')).toBe(true)
    expect(result.nodes.some((item) => item.id === 'placeholder-task-1')).toBe(false)
  })

  it('projects one button per unconnected condition handle', () => {
    const condition = node('condition-1', FlowNodeType.CONDITION)
    const result = project([condition])

    expect(result.edges.map((item) => item.id).sort()).toEqual(['button-condition-1-false', 'button-condition-1-true'])
    expect(result.nodes.find((item) => item.id === 'placeholder-condition-1-true')?.position).toEqual({
      x: 220,
      y: 10,
    })
    expect(result.nodes.find((item) => item.id === 'placeholder-condition-1-false')?.position).toEqual({
      x: 220,
      y: 70,
    })
  })

  it('omits only the connected condition handle', () => {
    const condition = node('condition-1', FlowNodeType.CONDITION)
    const result = project(
      [condition, node('task-2')],
      [edge('true-edge', 'condition-1', 'task-2', EdgeHandleEnum.TRUE)]
    )

    expect(result.edges.some((item) => item.id === 'button-condition-1-true')).toBe(false)
    expect(result.edges.some((item) => item.id === 'button-condition-1-false')).toBe(true)
    expect(result.nodes.some((item) => item.id === 'placeholder-condition-1-true')).toBe(false)
  })

  it('projects loop and approval handles with distinct active state and placeholders', () => {
    const loop = node('loop-1', FlowNodeType.LOOP)
    const approval = node('approval-1', FlowNodeType.APPROVAL)
    const result = project([loop, approval], [], {
      activeEdgeButtonNodeId: 'loop-1',
      activeEdgeButtonHandle: EdgeHandleEnum.LOOP,
    })

    expect(result.edges.find((item) => item.id === 'button-loop-1-loop')?.data?.isActive).toBe(true)
    expect(result.edges.find((item) => item.id === 'button-loop-1-done')?.data?.isActive).toBe(false)
    expect(result.edges.some((item) => item.id === 'button-approval-1-approved')).toBe(true)
    expect(result.edges.some((item) => item.id === 'button-approval-1-rejected')).toBe(true)
    expect(result.nodes.some((item) => item.id === 'placeholder-loop-1-loop')).toBe(true)
  })

  it('projects switch case and default handles from node configuration', () => {
    const switchNode = node('switch-1', FlowNodeType.SWITCH, undefined, {
      parameters: { cases: [{ port: 'case_0' }, { port: 'case_1' }] },
    })
    const result = project([switchNode])

    expect(
      result.edges.map((item) => item.sourceHandle).sort((left, right) => (left ?? '').localeCompare(right ?? ''))
    ).toEqual(['case_0', 'case_1', 'default'])
    expect(result.nodes.some((item) => item.id === 'placeholder-switch-1-default')).toBe(true)
  })

  it('omits the pending handle while keeping buttons on other handles', () => {
    const condition = node('condition-1', FlowNodeType.CONDITION)
    const pendingEdge: PendingEdge = { sourceNodeId: 'condition-1', sourceHandle: EdgeHandleEnum.TRUE, x: 500, y: 300 }
    const result = project([condition], [], { pendingEdge })

    expect(result.edges.some((item) => item.id === 'button-condition-1-true')).toBe(false)
    expect(result.edges.some((item) => item.id === 'button-condition-1-false')).toBe(true)
    expect(result.nodes.some((item) => item.id === 'placeholder-condition-1-true')).toBe(false)
  })

  it('removes button edges, placeholders, and button classes in execution or read-only views', () => {
    const task = node('task-1', FlowNodeType.TASK, undefined, {})
    const result = project(
      [
        { ...task, className: 'custom has-button-edge handle-source-connected' },
        node('placeholder-task-1', FlowNodeType.PLACEHOLDER),
      ],
      [
        edge('real-edge', 'task-1', 'task-2'),
        { ...edge('button-task-1', 'task-1', 'placeholder-task-1'), type: 'buttonEdge' },
      ],
      { executionStatus: 'running' }
    )

    expect(result.edges.map((item) => item.id)).toEqual(['real-edge'])
    expect(result.nodes.map((item) => item.id)).toEqual(['task-1'])
    expect(result.nodes[0].className).toBe('custom')

    const readOnly = project([task], [], { isReadOnly: true })
    expect(readOnly.edges).toEqual([])
  })
})
