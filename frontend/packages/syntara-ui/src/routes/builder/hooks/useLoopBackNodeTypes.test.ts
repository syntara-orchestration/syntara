import { ActivityTypeEnum } from '@syntara/contracts'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { FlowNodeType } from '../../../constants'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import { detectLoopBackNodes } from '../utils/detectLoopBackNodes'
import type { EdgeType } from '../utils/workflowToGraph'

import { projectLoopBackNodeTypes } from './useLoopBackNodeTypes'

vi.mock('../utils/detectLoopBackNodes', () => ({
  detectLoopBackNodes: vi.fn(() => new Set<string>()),
}))

function makeTaskNode(
  id: string,
  type: typeof FlowNodeType.TASK | typeof FlowNodeType.TASK_REVERSED = FlowNodeType.TASK
): NodeType {
  return {
    id,
    type,
    position: { x: 0, y: 0 },
    data: { type: ActivityTypeEnum.SCRIPT, id, name: id, parameters: {} },
  } as unknown as NodeType
}

function makeGenericNode(id: string, reverseHandles = false): NodeType {
  const metadata: Record<string, unknown> = { __isGeneric: true }
  if (reverseHandles) metadata.__reverseHandles = true
  return {
    id,
    type: FlowNodeType.GENERIC,
    position: { x: 0, y: 0 },
    data: { type: ActivityTypeEnum.SCRIPT, id, name: id, parameters: {}, metadata },
  } as unknown as NodeType
}

describe('projectLoopBackNodeTypes', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(detectLoopBackNodes).mockReturnValue(new Set())
  })

  it('does not project loop-back node types before initialization', () => {
    const nodes = [makeTaskNode('a')]

    expect(projectLoopBackNodeTypes(nodes, [] as EdgeType[], false)).toBe(nodes)
    expect(detectLoopBackNodes).not.toHaveBeenCalled()
  })

  it('returns the same node array when no loop-back nodes need changes', () => {
    const nodes = [makeTaskNode('a'), makeTaskNode('b')]

    expect(projectLoopBackNodeTypes(nodes, [] as EdgeType[], true)).toBe(nodes)
  })

  it('reverses task nodes identified by the existing loop-back algorithm', () => {
    vi.mocked(detectLoopBackNodes).mockReturnValue(new Set(['a']))
    const result = projectLoopBackNodeTypes([makeTaskNode('a'), makeTaskNode('b')], [] as EdgeType[], true)

    expect(result.map((node) => node.type)).toEqual([FlowNodeType.TASK_REVERSED, FlowNodeType.TASK])
  })

  it('removes reverse-handle metadata when a generic node leaves the loop-back path', () => {
    const node = makeGenericNode('generic-1', true)
    const result = projectLoopBackNodeTypes([node], [] as EdgeType[], true)

    expect((result[0].data as Record<string, unknown>).metadata).toEqual({ __isGeneric: true })
  })

  it('preserves non-task node types', () => {
    const trigger = {
      id: 'trigger-0',
      type: FlowNodeType.TRIGGER,
      position: { x: 0, y: 0 },
      data: { name: 'Manual', triggerType: 'manual', details: '' },
    } as unknown as NodeType
    vi.mocked(detectLoopBackNodes).mockReturnValue(new Set(['trigger-0']))

    expect(projectLoopBackNodeTypes([trigger], [] as EdgeType[], true)[0].type).toBe(FlowNodeType.TRIGGER)
  })
})
