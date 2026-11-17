import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RegistryStepId } from '../../../../constants'
import { useWorkflowStore } from '../../../../stores/useWorkflowStore'
import { StepRegistry } from '../StepRegistry'

import registerHumanTasksStep from './registerHumanTasksStep'

vi.mock('../../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: {
    getState: vi.fn(() => ({
      addActivity: vi.fn(),
    })),
  },
  createApprovalActivity: vi.fn((opts: Record<string, unknown>) => ({
    id: opts.id,
    name: opts.name,
    type: 'approval' as const,
  })),
  createFormPromptActivity: vi.fn((opts: Record<string, unknown>) => ({
    id: opts.id,
    name: opts.name,
    type: 'form_prompt' as const,
  })),
}))

describe('registerHumanTasksStep', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    StepRegistry.unregister(RegistryStepId.HUMAN_TASKS)
  })

  it('registers Human tasks with Approval and Form subtypes', () => {
    registerHumanTasksStep()

    const registration = StepRegistry.get(RegistryStepId.HUMAN_TASKS)
    expect(registration?.label).toBe('Human tasks')
    expect(registration?.category).toBe('human_tasks')
    expect(registration?.subtypes?.map((s) => s.id)).toEqual([RegistryStepId.APPROVAL, RegistryStepId.FORM_PROMPT])
    expect(registration?.description).toBe('Pause the workflow for human approval or structured input')
  })

  it('onSubmit adds approval activity when subtype is Approval', () => {
    const addActivity = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({ addActivity } as never)

    registerHumanTasksStep()
    const registration = StepRegistry.get(RegistryStepId.HUMAN_TASKS)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit(
      { name: 'Gate', prompt: '', fallback_decision: 'reject' as const },
      onSuccess,
      onError,
      RegistryStepId.APPROVAL
    )

    expect(addActivity).toHaveBeenCalledOnce()
    expect(onSuccess).toHaveBeenCalled()
    expect(onError).not.toHaveBeenCalled()
  })

  it('onSubmit adds form prompt activity when subtype is Form', () => {
    const addActivity = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({ addActivity } as never)

    registerHumanTasksStep()
    const registration = StepRegistry.get(RegistryStepId.HUMAN_TASKS)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit(
      {
        name: 'Survey',
        form_definition: { fields: [] },
        fallback_decision: 'fallback',
      },
      onSuccess,
      onError,
      RegistryStepId.FORM_PROMPT
    )

    expect(addActivity).toHaveBeenCalledOnce()
    expect(onSuccess).toHaveBeenCalled()
    expect(onError).not.toHaveBeenCalled()
  })

  it('onSubmit calls onError when subtype is missing', () => {
    registerHumanTasksStep()
    const registration = StepRegistry.get(RegistryStepId.HUMAN_TASKS)
    const onError = vi.fn()

    registration?.onSubmit({ name: 'X', form_definition: { fields: [] } }, vi.fn(), onError)

    expect(onError).toHaveBeenCalledWith('Select Approval or Form')
  })
})
