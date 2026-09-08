import { ExecutorTypeEnum, TriggerTypeEnum } from '@syntara/contracts'
import type { Edge, Node } from '@xyflow/react'
import { describe, expect, it } from 'vitest'

import { RegistryNodeId } from '../../../../constants'

import { getAdjacentNodesFromFlow } from './getAdjacentNodesFromFlow'

const FLOW_NODE_TYPES = new Set(['condition', 'loop', 'converge', 'switch', 'wait', 'approval'])

function makeNode(id: string, name: string, type = 'script'): Node {
  return {
    id,
    type: FLOW_NODE_TYPES.has(type) ? type : 'task',
    position: { x: 0, y: 0 },
    data: { name, type },
  }
}

function makeTriggerNode(index: number, name: string, triggerType: string = TriggerTypeEnum.MANUAL_TRIGGER): Node {
  return {
    id: `trigger-${index}`,
    type: 'trigger',
    position: { x: 0, y: 0 },
    data: { name, triggerType },
  }
}

function makeEdge(source: string, target: string, id?: string): Edge {
  return {
    id: id ?? `${source}->${target}`,
    source,
    target,
    type: 'default',
  }
}

describe('getAdjacentNodesFromFlow', () => {
  it('returns downstream from trigger display id', () => {
    const nodes = [makeTriggerNode(0, 'Manual Trigger'), makeNode('check-value', 'Check Value')]
    const edges = [makeEdge('trigger-0', 'check-value')]

    const result = getAdjacentNodesFromFlow('trigger-0', edges, nodes)

    expect(result.upstream).toEqual([])
    expect(result.downstream).toMatchObject([
      { id: 'check-value', name: 'Check Value', type: 'script', iconId: RegistryNodeId.ACTION_SCRIPT },
    ])
    expect(result.downstream[0]?.icon).toBeDefined()
  })

  it('returns upstream trigger display id for activity node', () => {
    const nodes = [makeTriggerNode(0, 'Manual Trigger'), makeNode('check-value', 'Check Value')]
    const edges = [makeEdge('trigger-0', 'check-value')]

    const result = getAdjacentNodesFromFlow('check-value', edges, nodes)

    expect(result.upstream).toMatchObject([
      {
        id: 'trigger-0',
        name: 'Manual Trigger',
        type: TriggerTypeEnum.MANUAL_TRIGGER,
        iconId: RegistryNodeId.TRIGGER_MANUAL,
      },
    ])
    expect(result.upstream[0]?.icon).toBeDefined()
  })

  it('returns direct downstream neighbors for branching node', () => {
    const nodes = [
      makeNode('cond-1', 'Branch', 'condition'),
      makeNode('task-a', 'Task A'),
      makeNode('task-b', 'Task B'),
    ]
    const edges = [makeEdge('cond-1', 'task-a'), makeEdge('cond-1', 'task-b')]

    const result = getAdjacentNodesFromFlow('cond-1', edges, nodes)

    expect(result.downstream).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ id: 'task-a', name: 'Task A', type: 'script', iconId: RegistryNodeId.ACTION_SCRIPT }),
        expect.objectContaining({ id: 'task-b', name: 'Task B', type: 'script', iconId: RegistryNodeId.ACTION_SCRIPT }),
      ])
    )
    expect(result.downstream).toHaveLength(2)
  })

  it('ignores button and placeholder edges', () => {
    const nodes = [makeTriggerNode(0, 'Manual Trigger'), makeNode('check-value', 'Check Value')]
    const edges = [
      makeEdge('trigger-0', 'check-value', 'real-edge'),
      { id: 'button-trigger-0', source: 'trigger-0', target: 'placeholder-trigger-0', type: 'buttonEdge' },
    ]

    const result = getAdjacentNodesFromFlow('trigger-0', edges, nodes)

    expect(result.downstream).toMatchObject([
      { id: 'check-value', name: 'Check Value', type: 'script', iconId: RegistryNodeId.ACTION_SCRIPT },
    ])
    expect(result.downstream[0]?.icon).toBeDefined()
  })

  it('does not include transitive ancestors as upstream', () => {
    const nodes = [makeNode('node-a', 'A'), makeNode('node-b', 'B'), makeNode('node-c', 'C')]
    const edges = [makeEdge('node-a', 'node-b'), makeEdge('node-b', 'node-c')]

    const result = getAdjacentNodesFromFlow('node-c', edges, nodes)

    expect(result.upstream).toMatchObject([
      { id: 'node-b', name: 'B', type: 'script', iconId: RegistryNodeId.ACTION_SCRIPT },
    ])
    expect(result.upstream[0]?.icon).toBeDefined()
  })
  describe('canvas node type icons', () => {
    it('resolves trigger icons from triggerType', () => {
      const cases = [
        { triggerType: TriggerTypeEnum.MANUAL_TRIGGER, iconId: RegistryNodeId.TRIGGER_MANUAL },
        { triggerType: TriggerTypeEnum.SCHEDULED, iconId: RegistryNodeId.TRIGGER_SCHEDULED },
        { triggerType: TriggerTypeEnum.WEBHOOK_TRIGGER, iconId: RegistryNodeId.TRIGGER_WEBHOOK },
        { triggerType: TriggerTypeEnum.EDA_TRIGGER, iconId: RegistryNodeId.TRIGGER_EDA },
      ]

      for (const { triggerType, iconId } of cases) {
        const nodes = [makeTriggerNode(0, 'Trigger', triggerType), makeNode('next', 'Next')]
        const result = getAdjacentNodesFromFlow('next', [makeEdge('trigger-0', 'next')], nodes)
        expect(result.upstream[0]).toMatchObject({
          id: 'trigger-0',
          name: 'Trigger',
          type: triggerType,
          iconId,
        })
        expect(result.upstream[0]?.icon).toBeDefined()
      }
    })

    it('resolves logic and task activity icons', () => {
      const cases: Array<{ type: string; iconId: string }> = [
        { type: 'condition', iconId: RegistryNodeId.LOGIC_CONDITION },
        { type: 'loop', iconId: RegistryNodeId.LOGIC_LOOP },
        { type: 'converge', iconId: RegistryNodeId.LOGIC_CONVERGE },
        { type: ExecutorTypeEnum.SCRIPT, iconId: RegistryNodeId.ACTION_SCRIPT },
        { type: ExecutorTypeEnum.HTTP_REQUEST, iconId: RegistryNodeId.ACTION_API },
        { type: ExecutorTypeEnum.AGENTIC, iconId: RegistryNodeId.AGENT },
        { type: ExecutorTypeEnum.AAP_JOB_TEMPLATE, iconId: RegistryNodeId.AAP_EXECUTION },
        { type: 'approval', iconId: RegistryNodeId.APPROVAL },
        { type: 'wait', iconId: RegistryNodeId.LOGIC_WAIT },
        { type: 'switch', iconId: RegistryNodeId.LOGIC_SWITCH },
      ]

      for (const { type, iconId } of cases) {
        const nodes = [makeNode('source', 'Source', type), makeNode('next', 'Next')]
        const result = getAdjacentNodesFromFlow('next', [makeEdge('source', 'next')], nodes)
        expect(result.upstream[0]).toMatchObject({ id: 'source', name: 'Source', type, iconId })
        expect(result.upstream[0]?.icon).toBeDefined()
      }
    })

    it('omits icon data for unknown canvas node types', () => {
      const nodes: Node[] = [
        {
          id: 'source',
          type: 'unknown',
          position: { x: 0, y: 0 },
          data: { name: 'Custom', type: 'custom' },
        },
        makeNode('next', 'Next'),
      ]

      const result = getAdjacentNodesFromFlow('next', [makeEdge('source', 'next')], nodes)

      expect(result.upstream[0]).toMatchObject({ id: 'source', name: 'Custom', type: 'custom' })
      expect(result.upstream[0]?.icon).toBeUndefined()
      expect(result.upstream[0]?.iconId).toBeUndefined()
    })

    it('falls back to node type and still resolves icons when activity data is empty', () => {
      const nodes: Node[] = [
        { id: 'source', type: 'loop', position: { x: 0, y: 0 }, data: {} },
        makeNode('next', 'Next'),
      ]

      const result = getAdjacentNodesFromFlow('next', [makeEdge('source', 'next')], nodes)

      expect(result.upstream[0]).toMatchObject({
        id: 'source',
        type: 'loop',
        iconId: RegistryNodeId.LOGIC_LOOP,
      })
      expect(result.upstream[0]?.name).toBeUndefined()
      expect(result.upstream[0]?.icon).toBeDefined()
    })

    it('falls back to unknown and omits icons when type and data type are missing', () => {
      const nodes: Node[] = [
        { id: 'source', position: { x: 0, y: 0 }, data: { name: 'Orphan' } },
        makeNode('next', 'Next'),
      ]

      const result = getAdjacentNodesFromFlow('next', [makeEdge('source', 'next')], nodes)

      expect(result.upstream[0]).toMatchObject({ id: 'source', name: 'Orphan', type: 'unknown' })
      expect(result.upstream[0]?.icon).toBeUndefined()
      expect(result.upstream[0]?.iconId).toBeUndefined()
    })
  })
})
