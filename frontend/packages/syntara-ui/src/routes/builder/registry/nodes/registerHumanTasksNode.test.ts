import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RegistryNodeId } from '../../../../constants'
import { useWorkflowStore } from '../../../../stores/useWorkflowStore'
import { NodeRegistry } from '../NodeRegistry'

import registerHumanTasksNode from './registerHumanTasksNode'

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

describe('registerHumanTasksNode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    NodeRegistry.unregister(RegistryNodeId.HUMAN_TASKS)
  })

  it('registers Human tasks with Approval and Form subtypes', () => {
    registerHumanTasksNode()

    const registration = NodeRegistry.get(RegistryNodeId.HUMAN_TASKS)
    expect(registration?.label).toBe('Human tasks')
    expect(registration?.category).toBe('human_tasks')
    expect(registration?.subtypes?.map((s) => s.id)).toEqual([RegistryNodeId.APPROVAL, RegistryNodeId.FORM_PROMPT])
    expect(registration?.description).toBe('Pause the workflow for human approval or structured input')
  })

  it('onSubmit adds approval activity when subtype is Approval', () => {
    const addActivity = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({ addActivity } as never)

    registerHumanTasksNode()
    const registration = NodeRegistry.get(RegistryNodeId.HUMAN_TASKS)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit(
      { name: 'Gate', prompt: '', fallback_decision: 'reject' as const },
      onSuccess,
      onError,
      RegistryNodeId.APPROVAL
    )

    expect(addActivity).toHaveBeenCalledOnce()
    expect(onSuccess).toHaveBeenCalled()
    expect(onError).not.toHaveBeenCalled()
  })

  it('onSubmit adds form prompt activity when subtype is Form', () => {
    const addActivity = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({ addActivity } as never)

    registerHumanTasksNode()
    const registration = NodeRegistry.get(RegistryNodeId.HUMAN_TASKS)
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
      RegistryNodeId.FORM_PROMPT
    )

    expect(addActivity).toHaveBeenCalledOnce()
    expect(onSuccess).toHaveBeenCalled()
    expect(onError).not.toHaveBeenCalled()
  })

  it('onSubmit calls onError when subtype is missing', () => {
    registerHumanTasksNode()
    const registration = NodeRegistry.get(RegistryNodeId.HUMAN_TASKS)
    const onError = vi.fn()

    registration?.onSubmit({ name: 'X', form_definition: { fields: [] } }, vi.fn(), onError)

    expect(onError).toHaveBeenCalledWith('Select Approval or Form')
  })
})
