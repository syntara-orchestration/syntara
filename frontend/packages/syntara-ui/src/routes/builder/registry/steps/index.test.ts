import { TriggerTypeEnum } from '@syntara/contracts'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { StepRegistry } from '../StepRegistry'

vi.mock('../../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: {
    getState: vi.fn(() => ({
      addActivity: vi.fn(),
      addTrigger: vi.fn(),
      edges: [],
      batchAddActivitiesAndEdges: vi.fn(),
    })),
  },
  createManualTrigger: vi.fn(() => ({ type: TriggerTypeEnum.MANUAL_TRIGGER })),
  createScheduledTrigger: vi.fn(() => ({ type: TriggerTypeEnum.SCHEDULED })),
  createWebhookTrigger: vi.fn(() => ({ type: TriggerTypeEnum.WEBHOOK_TRIGGER })),
  createScriptActivity: vi.fn(() => ({ type: 'script' })),
  createApiActivity: vi.fn(() => ({ type: 'http_request' })),
  createAgenticActivity: vi.fn(() => ({ type: 'agentic' })),
  createApprovalActivity: vi.fn(() => ({ type: 'approval' })),
  createGenericActivity: vi.fn(() => ({ type: 'task' })),
  createConditionActivity: vi.fn(() => ({ type: 'condition' })),
  createConvergeActivity: vi.fn(() => ({ type: 'converge' })),
  createLoopActivity: vi.fn(() => ({ type: 'loop' })),
  createWaitActivity: vi.fn(() => ({ type: 'wait' })),
  createAAPJobTemplateActivity: vi.fn(() => ({ type: 'aap_job_template' })),
  createAAPWorkflowTemplateActivity: vi.fn(() => ({ type: 'aap_workflow_job_template' })),
}))

vi.mock('../../../../utils/jsonSafeParse', () => ({
  parseJsonSchema: vi.fn(),
}))

vi.mock('../../../../utils/webhookPath', () => ({
  normalizeWebhookPath: vi.fn((p: string) => p),
}))

describe('registerAllSteps (index)', () => {
  beforeEach(() => {
    StepRegistry.clear()
  })

  // 15s: the dynamic import of ./index pulls in every node module; under full-suite
  // parallelism the worker startup + import resolution can exceed the default 5s.
  it('registers all workflow step types when called', async () => {
    const { registerAllSteps } = await import('./index')
    registerAllSteps()

    const allNodes = StepRegistry.getAll()
    expect(allNodes.length).toBeGreaterThan(0)
  }, 15000)

  it('registers expected step type ids', async () => {
    const { registerAllSteps } = await import('./index')
    registerAllSteps()

    expect(StepRegistry.get('trigger')).toBeDefined()
    expect(StepRegistry.get('action')).toBeDefined()
    expect(StepRegistry.get('agent')).toBeDefined()
    expect(StepRegistry.get('approval')).toBeDefined()
  })
})
