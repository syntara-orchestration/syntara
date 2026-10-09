import { ExecutorTypeEnum, TriggerTypeEnum, type TaskActivity } from '@syntara/contracts'
import { describe, expect, it, vi } from 'vitest'

import { RegistryStepId } from '../../../../constants'

import { DetectedExecutorType } from './common/detectTaskExecutorType'
import { getCanvasStepIconDescriptor, getTaskIconDescriptor } from './stepIconResolver'

vi.mock('../../../../utils/triggerNodeIds', () => ({
  parseTriggerIndex: vi.fn((id: string) => {
    const match = /trigger-(\d+)/.exec(id)
    return match ? Number(match[1]) : null
  }),
}))

vi.mock('./common/detectTaskExecutorType', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./common/detectTaskExecutorType')>()
  return {
    ...actual,
    detectTaskExecutorType: vi.fn((data: TaskActivity) => ({
      detectedExecutorType: data.type,
      actualExecutor: data.type,
    })),
  }
})

vi.mock('./stepMetadata', () => ({
  stepMetadata: {
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

describe('stepIconResolver', () => {
  describe('getTaskIconDescriptor', () => {
    it('returns script icon by default', () => {
      const result = getTaskIconDescriptor({ type: ExecutorTypeEnum.SCRIPT, id: 't1', name: 'Script' } as TaskActivity)
      expect(result.id).toBe(RegistryStepId.ACTION_SCRIPT)
    })

    it('returns API icon for http_request', () => {
      const result = getTaskIconDescriptor({
        type: ExecutorTypeEnum.HTTP_REQUEST,
        id: 't2',
        name: 'API',
      } as TaskActivity)
      expect(result.id).toBe(RegistryStepId.ACTION_API)
    })

    it('returns agent icon for agentic', () => {
      const result = getTaskIconDescriptor({
        type: ExecutorTypeEnum.AGENTIC,
        id: 't3',
        name: 'Agent',
      } as TaskActivity)
      expect(result.id).toBe(RegistryStepId.AGENT)
    })

    it('returns approval icon for approval', () => {
      const result = getTaskIconDescriptor({
        type: ExecutorTypeEnum.APPROVAL,
        id: 't4',
        name: 'Approve',
      } as unknown as TaskActivity)
      expect(result.id).toBe(RegistryStepId.APPROVAL)
    })

    it('returns AAP icon for aap_job_template', () => {
      const result = getTaskIconDescriptor({
        type: ExecutorTypeEnum.AAP_JOB_TEMPLATE,
        id: 't5',
        name: 'AAP',
      } as TaskActivity)
      expect(result.id).toBe(RegistryStepId.AAP_EXECUTION)
    })

    it('returns AAP icon for detected AAP connector type', async () => {
      const mod = await import('./common/detectTaskExecutorType')
      const { detectTaskExecutorType } = vi.mocked(mod)
      detectTaskExecutorType.mockReturnValueOnce({
        detectedExecutorType: DetectedExecutorType.AAP,
        actualExecutor: 'some-connector',
        connectorData: null,
      })
      const result = getTaskIconDescriptor({ type: 'task', id: 't6', name: 'AAP Conn' } as unknown as TaskActivity)
      expect(result.id).toBe(RegistryStepId.AAP_EXECUTION)
    })
  })

  describe('getCanvasStepIconDescriptor', () => {
    it('returns switch icon for switch node', () => {
      const result = getCanvasStepIconDescriptor(
        { id: 'switch-1', type: 'switch', data: { id: 'switch-1', type: 'switch' } },
        null
      )
      expect(result.id).toBe(RegistryStepId.LOGIC_SWITCH)
    })

    it('returns wait icon for wait node', () => {
      const result = getCanvasStepIconDescriptor(
        { id: 'wait-1', type: 'wait', data: { id: 'wait-1', type: 'wait' } },
        null
      )
      expect(result.id).toBe(RegistryStepId.LOGIC_WAIT)
    })

    it('returns condition icon for condition node', () => {
      const result = getCanvasStepIconDescriptor(
        { id: 'cond-1', type: 'condition', data: { id: 'cond-1', type: 'condition' } },
        null
      )
      expect(result.id).toBe(RegistryStepId.LOGIC_CONDITION)
    })

    it('returns loop icon for loop node', () => {
      const result = getCanvasStepIconDescriptor(
        { id: 'loop-1', type: 'loop', data: { id: 'loop-1', type: 'loop' } },
        null
      )
      expect(result.id).toBe(RegistryStepId.LOGIC_LOOP)
    })

    it('returns converge icon for converge node', () => {
      const result = getCanvasStepIconDescriptor(
        { id: 'conv-1', type: 'converge', data: { id: 'conv-1', type: 'converge' } },
        null
      )
      expect(result.id).toBe(RegistryStepId.LOGIC_CONVERGE)
    })

    it('returns approval icon for approval node', () => {
      const result = getCanvasStepIconDescriptor(
        { id: 'apr-1', type: 'approval', data: { id: 'apr-1', type: 'approval' } },
        null
      )
      expect(result.id).toBe(RegistryStepId.APPROVAL)
    })

    it('returns manual trigger icon by default for trigger node', () => {
      const result = getCanvasStepIconDescriptor(
        { id: 'trigger-0', type: 'trigger', data: { id: 'trigger-0', type: TriggerTypeEnum.MANUAL_TRIGGER } },
        { triggers: [{ type: TriggerTypeEnum.MANUAL_TRIGGER }] }
      )
      expect(result.id).toBe(RegistryStepId.TRIGGER_MANUAL)
    })

    it('returns scheduled trigger icon', () => {
      const result = getCanvasStepIconDescriptor(
        { id: 'trigger-0', type: 'trigger', data: { id: 'trigger-0', type: TriggerTypeEnum.SCHEDULED } },
        { triggers: [{ type: TriggerTypeEnum.SCHEDULED }] }
      )
      expect(result.id).toBe(RegistryStepId.TRIGGER_SCHEDULED)
    })

    it('returns webhook trigger icon', () => {
      const result = getCanvasStepIconDescriptor(
        { id: 'trigger-0', type: 'trigger', data: { id: 'trigger-0', type: TriggerTypeEnum.WEBHOOK_TRIGGER } },
        { triggers: [{ type: TriggerTypeEnum.WEBHOOK_TRIGGER }] }
      )
      expect(result.id).toBe(RegistryStepId.TRIGGER_WEBHOOK)
    })

    it('falls back to data.triggerType when workflow triggers are missing', () => {
      const result = getCanvasStepIconDescriptor(
        { id: 'trigger-0', type: 'trigger', data: { triggerType: TriggerTypeEnum.SCHEDULED } },
        null
      )
      expect(result.id).toBe(RegistryStepId.TRIGGER_SCHEDULED)
    })

    it('returns undefined icon for unknown step type', () => {
      const result = getCanvasStepIconDescriptor({ id: 'unk-1', type: 'unknown', data: { id: 'unk-1' } }, null)
      expect(result.icon).toBeUndefined()
      expect(result.id).toBeUndefined()
    })

    it('delegates to getTaskIconDescriptor for task nodes', () => {
      const result = getCanvasStepIconDescriptor(
        {
          id: 'task-1',
          type: 'task',
          data: { type: ExecutorTypeEnum.SCRIPT, id: 'task-1', name: 'Script' },
        },
        null
      )
      expect(result.id).toBe(RegistryStepId.ACTION_SCRIPT)
    })
  })
})
