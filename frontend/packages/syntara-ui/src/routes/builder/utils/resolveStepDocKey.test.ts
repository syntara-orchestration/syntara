import { ExecutorTypeEnum, TriggerTypeEnum } from '@syntara/contracts'
import type { Node } from '@xyflow/react'
import { describe, expect, it } from 'vitest'

import { FlowNodeType, RegistryStepId } from '../../../constants'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'

import { resolveStepDocKey } from './resolveStepDocKey'

function makeNode(type: string, data: Record<string, unknown> = {}): Node<NodeType['data']> {
  return {
    id: 'node-1',
    type,
    position: { x: 0, y: 0 },
    data: data,
  }
}

describe('resolveStepDocKey', () => {
  describe('add mode', () => {
    it.each([
      [RegistryStepId.TRIGGER, RegistryStepId.TRIGGER_MANUAL, 'manualTrigger'],
      [RegistryStepId.TRIGGER, RegistryStepId.TRIGGER_SCHEDULED, 'scheduleTrigger'],
      [RegistryStepId.TRIGGER, RegistryStepId.TRIGGER_WEBHOOK, 'webhookTrigger'],
      [RegistryStepId.TRIGGER, RegistryStepId.TRIGGER_EDA, 'eventDrivenAnsibleTrigger'],
      [RegistryStepId.ACTION, RegistryStepId.ACTION_API, 'restApi'],
      [RegistryStepId.LOGIC, RegistryStepId.LOGIC_CONDITION, 'conditional'],
      [RegistryStepId.LOGIC, RegistryStepId.LOGIC_CONVERGE, 'converge'],
      [RegistryStepId.LOGIC, RegistryStepId.LOGIC_LOOP, 'loop'],
      [RegistryStepId.LOGIC, RegistryStepId.LOGIC_SWITCH, 'switch'],
      [RegistryStepId.LOGIC, RegistryStepId.LOGIC_WAIT, 'wait'],
      [RegistryStepId.AAP_EXECUTION, RegistryStepId.AAP_JOB_TEMPLATE, 'launchAapJobTemplate'],
      [RegistryStepId.AAP_EXECUTION, RegistryStepId.AAP_WORKFLOW_TEMPLATE, 'launchAapWorkflowTemplate'],
    ] as const)('maps %s / %s to %s', (stepTypeId, stepSubtypeId, expectedKey) => {
      expect(
        resolveStepDocKey({
          mode: 'add',
          stepTypeId,
          stepSubtypeId,
          selectedNode: null,
        })
      ).toBe(expectedKey)
    })

    it('returns null for script (no documentation link)', () => {
      expect(
        resolveStepDocKey({
          mode: 'add',
          stepTypeId: RegistryStepId.ACTION,
          stepSubtypeId: RegistryStepId.ACTION_SCRIPT,
          selectedNode: null,
        })
      ).toBeNull()
    })

    it('maps leaf stepTypeId without subtype (agent, approval)', () => {
      expect(
        resolveStepDocKey({
          mode: 'add',
          stepTypeId: RegistryStepId.AGENT,
          stepSubtypeId: null,
          selectedNode: null,
        })
      ).toBe('taskAgent')

      expect(
        resolveStepDocKey({
          mode: 'add',
          stepTypeId: RegistryStepId.APPROVAL,
          stepSubtypeId: null,
          selectedNode: null,
        })
      ).toBe('approval')
    })

    it('falls back to builder for category-only selection', () => {
      expect(
        resolveStepDocKey({
          mode: 'add',
          stepTypeId: RegistryStepId.TRIGGER,
          stepSubtypeId: null,
          selectedNode: null,
        })
      ).toBe('builder')

      expect(
        resolveStepDocKey({
          mode: 'add',
          stepTypeId: RegistryStepId.ACTION,
          stepSubtypeId: null,
          selectedNode: null,
        })
      ).toBe('builder')

      expect(
        resolveStepDocKey({
          mode: 'add',
          stepTypeId: RegistryStepId.LOGIC,
          stepSubtypeId: null,
          selectedNode: null,
        })
      ).toBe('builder')

      expect(
        resolveStepDocKey({
          mode: 'add',
          stepTypeId: RegistryStepId.AAP_EXECUTION,
          stepSubtypeId: null,
          selectedNode: null,
        })
      ).toBe('builder')
    })

    it('falls back to builder when type and subtype are missing', () => {
      expect(
        resolveStepDocKey({
          mode: 'add',
          stepTypeId: null,
          stepSubtypeId: null,
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
          stepTypeId: null,
          stepSubtypeId: null,
          selectedNode: makeNode(FlowNodeType.TRIGGER, { name: 'T', triggerType }),
        })
      ).toBe(expectedKey)
    })

    it('defaults trigger without triggerType to manualTrigger', () => {
      expect(
        resolveStepDocKey({
          mode: 'edit',
          stepTypeId: null,
          stepSubtypeId: null,
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
          stepTypeId: null,
          stepSubtypeId: null,
          selectedNode: makeNode(FlowNodeType.TASK, { type: executor, name: 'Task' }),
        })
      ).toBe(expectedKey)
    })

    it('returns null for script task (no documentation link)', () => {
      expect(
        resolveStepDocKey({
          mode: 'edit',
          stepTypeId: null,
          stepSubtypeId: null,
          selectedNode: makeNode(FlowNodeType.TASK, { type: ExecutorTypeEnum.SCRIPT, name: 'Task' }),
        })
      ).toBeNull()
    })

    it('returns null for script task-reversed nodes', () => {
      expect(
        resolveStepDocKey({
          mode: 'edit',
          stepTypeId: null,
          stepSubtypeId: null,
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
          stepTypeId: null,
          stepSubtypeId: null,
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
          stepTypeId: null,
          stepSubtypeId: null,
          selectedNode: makeNode(flowType, { name: 'Step' }),
        })
      ).toBe(expectedKey)
    })

    it('falls back to builder for unknown task executor', () => {
      expect(
        resolveStepDocKey({
          mode: 'edit',
          stepTypeId: null,
          stepSubtypeId: null,
          selectedNode: makeNode(FlowNodeType.TASK, { type: 'unknown', name: 'Task' }),
        })
      ).toBe('builder')
    })

    it('falls back to builder for generic and placeholder nodes', () => {
      expect(
        resolveStepDocKey({
          mode: 'edit',
          stepTypeId: null,
          stepSubtypeId: null,
          selectedNode: makeNode(FlowNodeType.GENERIC, { name: 'Generic' }),
        })
      ).toBe('builder')

      expect(
        resolveStepDocKey({
          mode: 'edit',
          stepTypeId: null,
          stepSubtypeId: null,
          selectedNode: makeNode(FlowNodeType.PLACEHOLDER, {}),
        })
      ).toBe('builder')
    })

    it('falls back to builder when selectedNode is null', () => {
      expect(
        resolveStepDocKey({
          mode: 'edit',
          stepTypeId: null,
          stepSubtypeId: null,
          selectedNode: null,
        })
      ).toBe('builder')
    })
  })

  it('falls back to builder when mode is null', () => {
    expect(
      resolveStepDocKey({
        mode: null,
        stepTypeId: RegistryStepId.AGENT,
        stepSubtypeId: null,
        selectedNode: null,
      })
    ).toBe('builder')
  })
})
