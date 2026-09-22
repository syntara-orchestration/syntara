import { ExecutorTypeEnum, TriggerTypeEnum, type TaskActivity } from '@syntara/contracts'
import { describe, expect, it, vi } from 'vitest'

import { RegistryNodeId } from '../../../../constants'

import { DetectedExecutorType } from './common/detectTaskNodeType'
import { getCanvasNodeIconDescriptor, getTaskIconDescriptor } from './nodeIconResolver'

vi.mock('../../../../utils/triggerNodeIds', () => ({
  parseTriggerIndex: vi.fn((id: string) => {
    const match = /trigger-(\d+)/.exec(id)
    return match ? Number(match[1]) : null
  }),
}))

vi.mock('./common/detectTaskNodeType', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./common/detectTaskNodeType')>()
  return {
    ...actual,
    detectTaskNodeType: vi.fn((data: TaskActivity) => ({
      detectedExecutorType: data.type,
      actualExecutor: data.type,
    })),
  }
})

vi.mock('./nodeMetadata', () => ({
  nodeMetadata: {
    trigger: { icon: () => null },
    scheduledTrigger: { icon: () => null },
    webhookTrigger: { icon: () => null },
    condition: { icon: () => null },
    loop: { icon: () => null },
    converge: { icon: () => null },
    switch: { icon: () => null },
    wait: { icon: () => null },
  },
  executorMetadata: {
    [ExecutorTypeEnum.SCRIPT]: { icon: () => null },
    [ExecutorTypeEnum.HTTP_REQUEST]: { icon: () => null },
    [ExecutorTypeEnum.AGENTIC]: { icon: () => null },
    [ExecutorTypeEnum.AAP_JOB_TEMPLATE]: { icon: () => null },
    [ExecutorTypeEnum.APPROVAL]: { icon: () => null },
  },
}))

describe('nodeIconResolver', () => {
  describe('getTaskIconDescriptor', () => {
    it('returns script icon by default', () => {
      const result = getTaskIconDescriptor({ type: ExecutorTypeEnum.SCRIPT, id: 't1', name: 'Script' } as TaskActivity)
      expect(result.id).toBe(RegistryNodeId.ACTION_SCRIPT)
    })

    it('returns API icon for http_request', () => {
      const result = getTaskIconDescriptor({
        type: ExecutorTypeEnum.HTTP_REQUEST,
        id: 't2',
        name: 'API',
      } as TaskActivity)
      expect(result.id).toBe(RegistryNodeId.ACTION_API)
    })

    it('returns agent icon for agentic', () => {
      const result = getTaskIconDescriptor({
        type: ExecutorTypeEnum.AGENTIC,
        id: 't3',
        name: 'Agent',
      } as TaskActivity)
      expect(result.id).toBe(RegistryNodeId.AGENT)
    })

    it('returns approval icon for approval', () => {
      const result = getTaskIconDescriptor({
        type: ExecutorTypeEnum.APPROVAL,
        id: 't4',
        name: 'Approve',
      } as unknown as TaskActivity)
      expect(result.id).toBe(RegistryNodeId.APPROVAL)
    })

    it('returns AAP icon for aap_job_template', () => {
      const result = getTaskIconDescriptor({
        type: ExecutorTypeEnum.AAP_JOB_TEMPLATE,
        id: 't5',
        name: 'AAP',
      } as TaskActivity)
      expect(result.id).toBe(RegistryNodeId.AAP_EXECUTION)
    })

    it('returns AAP icon for detected AAP connector type', async () => {
      const mod = await import('./common/detectTaskNodeType')
      const { detectTaskNodeType } = vi.mocked(mod)
      detectTaskNodeType.mockReturnValueOnce({
        detectedExecutorType: DetectedExecutorType.AAP,
        actualExecutor: 'some-connector',
        connectorData: null,
      })
      const result = getTaskIconDescriptor({ type: 'task', id: 't6', name: 'AAP Conn' } as unknown as TaskActivity)
      expect(result.id).toBe(RegistryNodeId.AAP_EXECUTION)
    })
  })

  describe('getCanvasNodeIconDescriptor', () => {
    it('returns switch icon for switch node', () => {
      const result = getCanvasNodeIconDescriptor(
        { id: 'switch-1', type: 'switch', data: { id: 'switch-1', type: 'switch' } },
        null
      )
      expect(result.id).toBe(RegistryNodeId.LOGIC_SWITCH)
    })

    it('returns wait icon for wait node', () => {
      const result = getCanvasNodeIconDescriptor(
        { id: 'wait-1', type: 'wait', data: { id: 'wait-1', type: 'wait' } },
        null
      )
      expect(result.id).toBe(RegistryNodeId.LOGIC_WAIT)
    })

    it('returns condition icon for condition node', () => {
      const result = getCanvasNodeIconDescriptor(
        { id: 'cond-1', type: 'condition', data: { id: 'cond-1', type: 'condition' } },
        null
      )
      expect(result.id).toBe(RegistryNodeId.LOGIC_CONDITION)
    })

    it('returns loop icon for loop node', () => {
      const result = getCanvasNodeIconDescriptor(
        { id: 'loop-1', type: 'loop', data: { id: 'loop-1', type: 'loop' } },
        null
      )
      expect(result.id).toBe(RegistryNodeId.LOGIC_LOOP)
    })

    it('returns converge icon for converge node', () => {
      const result = getCanvasNodeIconDescriptor(
        { id: 'conv-1', type: 'converge', data: { id: 'conv-1', type: 'converge' } },
        null
      )
      expect(result.id).toBe(RegistryNodeId.LOGIC_CONVERGE)
    })

    it('returns approval icon for approval node', () => {
      const result = getCanvasNodeIconDescriptor(
        { id: 'apr-1', type: 'approval', data: { id: 'apr-1', type: 'approval' } },
        null
      )
      expect(result.id).toBe(RegistryNodeId.APPROVAL)
    })

    it('returns manual trigger icon by default for trigger node', () => {
      const result = getCanvasNodeIconDescriptor(
        { id: 'trigger-0', type: 'trigger', data: { id: 'trigger-0', type: TriggerTypeEnum.MANUAL_TRIGGER } },
        { triggers: [{ type: TriggerTypeEnum.MANUAL_TRIGGER }] }
      )
      expect(result.id).toBe(RegistryNodeId.TRIGGER_MANUAL)
    })

    it('returns scheduled trigger icon', () => {
      const result = getCanvasNodeIconDescriptor(
        { id: 'trigger-0', type: 'trigger', data: { id: 'trigger-0', type: TriggerTypeEnum.SCHEDULED } },
        { triggers: [{ type: TriggerTypeEnum.SCHEDULED }] }
      )
      expect(result.id).toBe(RegistryNodeId.TRIGGER_SCHEDULED)
    })

    it('returns webhook trigger icon', () => {
      const result = getCanvasNodeIconDescriptor(
        { id: 'trigger-0', type: 'trigger', data: { id: 'trigger-0', type: TriggerTypeEnum.WEBHOOK_TRIGGER } },
        { triggers: [{ type: TriggerTypeEnum.WEBHOOK_TRIGGER }] }
      )
      expect(result.id).toBe(RegistryNodeId.TRIGGER_WEBHOOK)
    })

    it('falls back to data.triggerType when workflow triggers are missing', () => {
      const result = getCanvasNodeIconDescriptor(
        { id: 'trigger-0', type: 'trigger', data: { triggerType: TriggerTypeEnum.SCHEDULED } },
        null
      )
      expect(result.id).toBe(RegistryNodeId.TRIGGER_SCHEDULED)
    })

    it('returns undefined icon for unknown node type', () => {
      const result = getCanvasNodeIconDescriptor({ id: 'unk-1', type: 'unknown', data: { id: 'unk-1' } }, null)
      expect(result.icon).toBeUndefined()
      expect(result.id).toBeUndefined()
    })

    it('delegates to getTaskIconDescriptor for task nodes', () => {
      const result = getCanvasNodeIconDescriptor(
        {
          id: 'task-1',
          type: 'task',
          data: { type: ExecutorTypeEnum.SCRIPT, id: 'task-1', name: 'Script' },
        },
        null
      )
      expect(result.id).toBe(RegistryNodeId.ACTION_SCRIPT)
    })
  })
})
