import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RegistryStepId } from '../../../../constants'
import { useWorkflowStore } from '../../../../stores/useWorkflowStore'
import { StepRegistry } from '../StepRegistry'

import registerFormPromptStep from './registerFormPromptStep'

vi.mock('../../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: {
    getState: vi.fn(() => ({
      addActivity: vi.fn(),
    })),
  },
  createFormPromptActivity: vi.fn((opts: Record<string, unknown>) => ({
    id: opts.id,
    name: opts.name,
    type: 'form_prompt' as const,
  })),
}))

describe('registerFormPromptStep', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    StepRegistry.unregister(RegistryStepId.FORM_PROMPT)
  })

  it('registers the Form step type as disabled for the Human tasks parent', () => {
    registerFormPromptStep()

    const registration = StepRegistry.get(RegistryStepId.FORM_PROMPT)
    expect(registration?.label).toBe('Form')
    expect(registration?.enabled).toBe(false)
    expect(registration?.order).toBe(51)
  })

  it('onSubmit creates a form prompt activity and calls onSuccess', () => {
    const addActivity = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({ addActivity } as never)

    registerFormPromptStep()
    const registration = StepRegistry.get(RegistryStepId.FORM_PROMPT)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit(
      {
        name: 'Survey',
        form_definition: { fields: [] },
        fallback_decision: 'submit',
      },
      onSuccess,
      onError
    )

    expect(addActivity).toHaveBeenCalledOnce()
    expect(onSuccess).toHaveBeenCalled()
    expect(onError).not.toHaveBeenCalled()
  })

  it('onSubmit calls onError when addActivity throws', () => {
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addActivity: () => {
        throw new Error('store failed')
      },
    } as never)

    registerFormPromptStep()
    const registration = StepRegistry.get(RegistryStepId.FORM_PROMPT)
    const onError = vi.fn()

    registration?.onSubmit(
      { name: 'Survey', form_definition: { fields: [] }, fallback_decision: 'submit' },
      vi.fn(),
      onError
    )

    expect(onError).toHaveBeenCalledWith('store failed')
  })
})
