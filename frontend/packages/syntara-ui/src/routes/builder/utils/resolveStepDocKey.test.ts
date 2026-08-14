import { ExecutorTypeEnum, TriggerTypeEnum } from '@syntara/contracts'
import type { Node } from '@xyflow/react'
import { describe, expect, it } from 'vitest'

import { FlowNodeType, RegistryNodeId } from '../../../constants'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'

import { resolveStepDocKey } from './resolveStepDocKey'

function makeNode(type: string, data: Record<string, unknown> = {}): Node<NodeType['data']> {
  return {
    id: 'node-1',
    type,
    position: { x: 0, y: 0 },
    data: data as NodeType['data'],
  }
}

describe('resolveStepDocKey', () => {
  describe('add mode', () => {
    it.each([
      [RegistryNodeId.TRIGGER, RegistryNodeId.TRIGGER_MANUAL, 'manualTrigger'],
      [RegistryNodeId.TRIGGER, RegistryNodeId.TRIGGER_SCHEDULED, 'scheduleTrigger'],
      [RegistryNodeId.TRIGGER, RegistryNodeId.TRIGGER_WEBHOOK, 'webhookTrigger'],
      [RegistryNodeId.TRIGGER, RegistryNodeId.TRIGGER_EDA, 'eventDrivenAnsibleTrigger'],
      [RegistryNodeId.ACTION, RegistryNodeId.ACTION_API, 'restApi'],
      [RegistryNodeId.LOGIC, RegistryNodeId.LOGIC_CONDITION, 'conditional'],
      [RegistryNodeId.LOGIC, RegistryNodeId.LOGIC_CONVERGE, 'converge'],
      [RegistryNodeId.LOGIC, RegistryNodeId.LOGIC_LOOP, 'loop'],
      [RegistryNodeId.LOGIC, RegistryNodeId.LOGIC_SWITCH, 'switch'],
      [RegistryNodeId.LOGIC, RegistryNodeId.LOGIC_WAIT, 'wait'],
      [RegistryNodeId.AAP_EXECUTION, RegistryNodeId.AAP_JOB_TEMPLATE, 'launchAapJobTemplate'],
      [RegistryNodeId.AAP_EXECUTION, RegistryNodeId.AAP_WORKFLOW_TEMPLATE, 'launchAapWorkflowTemplate'],
    ] as const)('maps %s / %s to %s', (nodeTypeId, nodeSubtypeId, expectedKey) => {
      expect(
        resolveStepDocKey({
          mode: 'add',
          nodeTypeId,
          nodeSubtypeId,
          selectedNode: null,
        })
      ).toBe(expectedKey)
    })

    it('returns null for script (no documentation link)', () => {
      expect(
        resolveStepDocKey({
          mode: 'add',
          nodeTypeId: RegistryNodeId.ACTION,
          nodeSubtypeId: RegistryNodeId.ACTION_SCRIPT,
          selectedNode: null,
        })
      ).toBeNull()
    })

    it('maps leaf nodeTypeId without subtype (agent, approval)', () => {
      expect(
        resolveStepDocKey({
          mode: 'add',
          nodeTypeId: RegistryNodeId.AGENT,
          nodeSubtypeId: null,
          selectedNode: null,
        })
      ).toBe('taskAgent')

      expect(
        resolveStepDocKey({
          mode: 'add',
          nodeTypeId: RegistryNodeId.APPROVAL,
          nodeSubtypeId: null,
          selectedNode: null,
        })
      ).toBe('approval')
    })

    it('falls back to builder for category-only selection', () => {
      expect(
        resolveStepDocKey({
          mode: 'add',
          nodeTypeId: RegistryNodeId.TRIGGER,
          nodeSubtypeId: null,
          selectedNode: null,
        })
      ).toBe('builder')

      expect(
        resolveStepDocKey({
          mode: 'add',
          nodeTypeId: RegistryNodeId.ACTION,
          nodeSubtypeId: null,
          selectedNode: null,
        })
      ).toBe('builder')

      expect(
        resolveStepDocKey({
          mode: 'add',
          nodeTypeId: RegistryNodeId.LOGIC,
          nodeSubtypeId: null,
          selectedNode: null,
        })
      ).toBe('builder')

      expect(
        resolveStepDocKey({
          mode: 'add',
          nodeTypeId: RegistryNodeId.AAP_EXECUTION,
          nodeSubtypeId: null,
          selectedNode: null,
        })
      ).toBe('builder')
    })

    it('falls back to builder when type and subtype are missing', () => {
      expect(
        resolveStepDocKey({
          mode: 'add',
          nodeTypeId: null,
          nodeSubtypeId: null,
          selectedNode: null,
        })
      ).toBe('builder')
    })
  })

  describe('edit mode', () => {
    it.each([
      [TriggerTypeEnum.MANUAL_TRIGGER, 'manualTrigger'],
      [TriggerTypeEnum.SCHEDULED, 'scheduleTrigger'],
      [TriggerTypeEnum.WEBHOOK_TRIGGER, 'webhookTrigger'],
      [TriggerTypeEnum.EDA_TRIGGER, 'eventDrivenAnsibleTrigger'],
    ] as const)('maps trigger type %s to %s', (triggerType, expectedKey) => {
      expect(
        resolveStepDocKey({
          mode: 'edit',
          nodeTypeId: null,
          nodeSubtypeId: null,
          selectedNode: makeNode(FlowNodeType.TRIGGER, { name: 'T', triggerType }),
        })
      ).toBe(expectedKey)
    })

    it('defaults trigger without triggerType to manualTrigger', () => {
      expect(
        resolveStepDocKey({
          mode: 'edit',
          nodeTypeId: null,
          nodeSubtypeId: null,
          selectedNode: makeNode(FlowNodeType.TRIGGER, { name: 'T' }),
        })
      ).toBe('manualTrigger')
    })

    it.each([
      [ExecutorTypeEnum.HTTP_REQUEST, 'restApi'],
      [ExecutorTypeEnum.AGENTIC, 'taskAgent'],
      [ExecutorTypeEnum.AAP_JOB_TEMPLATE, 'launchAapJobTemplate'],
      [ExecutorTypeEnum.AAP_WORKFLOW_JOB_TEMPLATE, 'launchAapWorkflowTemplate'],
    ] as const)('maps task executor %s to %s', (executor, expectedKey) => {
      expect(
        resolveStepDocKey({
          mode: 'edit',
          nodeTypeId: null,
          nodeSubtypeId: null,
          selectedNode: makeNode(FlowNodeType.TASK, { type: executor, name: 'Task' }),
        })
      ).toBe(expectedKey)
    })

    it('returns null for script task (no documentation link)', () => {
      expect(
        resolveStepDocKey({
          mode: 'edit',
          nodeTypeId: null,
          nodeSubtypeId: null,
          selectedNode: makeNode(FlowNodeType.TASK, { type: ExecutorTypeEnum.SCRIPT, name: 'Task' }),
        })
      ).toBeNull()
    })

    it('returns null for script task-reversed nodes', () => {
      expect(
        resolveStepDocKey({
          mode: 'edit',
          nodeTypeId: null,
          nodeSubtypeId: null,
          selectedNode: makeNode(FlowNodeType.TASK_REVERSED, {
            type: ExecutorTypeEnum.SCRIPT,
            name: 'Task',
          }),
        })
      ).toBeNull()
    })

    it('maps non-script task-reversed nodes using executor type', () => {
      expect(
        resolveStepDocKey({
          mode: 'edit',
          nodeTypeId: null,
          nodeSubtypeId: null,
          selectedNode: makeNode(FlowNodeType.TASK_REVERSED, {
            type: ExecutorTypeEnum.HTTP_REQUEST,
            name: 'Task',
          }),
        })
      ).toBe('restApi')
    })

    it.each([
      [FlowNodeType.APPROVAL, 'approval'],
      [FlowNodeType.CONDITION, 'conditional'],
      [FlowNodeType.CONVERGE, 'converge'],
      [FlowNodeType.LOOP, 'loop'],
      [FlowNodeType.SWITCH, 'switch'],
      [FlowNodeType.WAIT, 'wait'],
    ] as const)('maps flow type %s to %s', (flowType, expectedKey) => {
      expect(
        resolveStepDocKey({
          mode: 'edit',
          nodeTypeId: null,
          nodeSubtypeId: null,
          selectedNode: makeNode(flowType, { name: 'Step' }),
        })
      ).toBe(expectedKey)
    })

    it('falls back to builder for unknown task executor', () => {
      expect(
        resolveStepDocKey({
          mode: 'edit',
          nodeTypeId: null,
          nodeSubtypeId: null,
          selectedNode: makeNode(FlowNodeType.TASK, { type: 'unknown', name: 'Task' }),
        })
      ).toBe('builder')
    })

    it('falls back to builder for generic and placeholder nodes', () => {
      expect(
        resolveStepDocKey({
          mode: 'edit',
          nodeTypeId: null,
          nodeSubtypeId: null,
          selectedNode: makeNode(FlowNodeType.GENERIC, { name: 'Generic' }),
        })
      ).toBe('builder')

      expect(
        resolveStepDocKey({
          mode: 'edit',
          nodeTypeId: null,
          nodeSubtypeId: null,
          selectedNode: makeNode(FlowNodeType.PLACEHOLDER, {}),
        })
      ).toBe('builder')
    })

    it('falls back to builder when selectedNode is null', () => {
      expect(
        resolveStepDocKey({
          mode: 'edit',
          nodeTypeId: null,
          nodeSubtypeId: null,
          selectedNode: null,
        })
      ).toBe('builder')
    })
  })

  it('falls back to builder when mode is null', () => {
    expect(
      resolveStepDocKey({
        mode: null,
        nodeTypeId: RegistryNodeId.AGENT,
        nodeSubtypeId: null,
        selectedNode: null,
      })
    ).toBe('builder')
  })
})
