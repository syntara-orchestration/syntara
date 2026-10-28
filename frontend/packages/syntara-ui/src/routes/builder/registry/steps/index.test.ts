import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { RegistryStepId, TriggerTypeEnum } from '@syntara/contracts'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { StepRegistry, type StepSubtypeDefinition } from '../StepRegistry'

const nodeTypeCatalog = JSON.parse(
  readFileSync(
    resolve(
      dirname(fileURLToPath(import.meta.url)),
      '../../../../../../../../backend/src/syntara/schemas/workflows/v2/catalog/node_type_catalog.json'
    ),
    'utf-8'
  )
) as { node_types: { type: string }[] }
// Internal activities have no user-facing palette entry.
const BACKEND_ONLY_STEP_TYPES = new Set(['internal_activity'])

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

    expect(StepRegistry.get(RegistryStepId.TRIGGER)).toBeDefined()
    expect(StepRegistry.get(RegistryStepId.ACTION)).toBeDefined()
    expect(StepRegistry.get(RegistryStepId.AGENT)).toBeDefined()
    expect(StepRegistry.get(RegistryStepId.APPROVAL)).toBeDefined()
  })

  it('registers every backend step type exactly once except explicitly backend-only types', async () => {
    const { registerAllSteps } = await import('./index')
    registerAllSteps()

    const concreteSteps = StepRegistry.getAll().flatMap<StepSubtypeDefinition>((step) => step.subtypes ?? [step])
    const stepIds = concreteSteps.map(({ id }) => id)
    expect(new Set(stepIds).size).toBe(stepIds.length)
    expect(stepIds.sort()).toEqual(
      nodeTypeCatalog.node_types
        .map(({ type }) => type)
        .filter((type) => !BACKEND_ONLY_STEP_TYPES.has(type))
        .sort()
    )
    expect(nodeTypeCatalog.node_types.map(({ type }) => type)).toEqual(
      expect.arrayContaining([...BACKEND_ONLY_STEP_TYPES])
    )
  })
})
