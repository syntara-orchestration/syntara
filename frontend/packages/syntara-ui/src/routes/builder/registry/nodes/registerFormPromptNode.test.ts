import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RegistryNodeId } from '../../../../constants'
import { useWorkflowStore } from '../../../../stores/useWorkflowStore'
import { NodeRegistry } from '../NodeRegistry'

import registerFormPromptNode from './registerFormPromptNode'

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

describe('registerFormPromptNode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    NodeRegistry.unregister(RegistryNodeId.FORM_PROMPT)
  })

  it('registers the Form step type (disabled; add panel uses Human tasks parent)', () => {
    registerFormPromptNode()

    const registration = NodeRegistry.get(RegistryNodeId.FORM_PROMPT)
    expect(registration).toBeDefined()
    expect(registration?.id).toBe(RegistryNodeId.FORM_PROMPT)
    expect(registration?.label).toBe('Form')
    expect(registration?.category).toBe('human_tasks')
    expect(registration?.enabled).toBe(false)
  })

  it('adds a form prompt activity on submit', () => {
    const addActivity = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({ addActivity } as never)

    registerFormPromptNode()
    const registration = NodeRegistry.get(RegistryNodeId.FORM_PROMPT)
    expect(registration?.onSubmit).toBeDefined()

    const onSuccess = vi.fn()
    const onError = vi.fn()
    registration?.onSubmit(
      {
        name: 'Collect details',
        form_definition: { fields: [] },
        fallback_decision: 'fallback',
      },
      onSuccess,
      onError
    )

    expect(addActivity).toHaveBeenCalledOnce()
    expect(onSuccess).toHaveBeenCalled()
    expect(onError).not.toHaveBeenCalled()
  })
})
