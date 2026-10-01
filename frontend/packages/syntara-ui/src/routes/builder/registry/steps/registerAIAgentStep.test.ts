import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RegistryStepId } from '../../../../constants'
import { useWorkflowStore } from '../../../../stores/useWorkflowStore'
import { StepRegistry } from '../StepRegistry'

import registerAIAgentStep from './registerAIAgentStep'

vi.mock('../../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: {
    getState: vi.fn(() => ({
      addActivity: vi.fn(),
    })),
  },
  createAgenticActivity: vi.fn((opts: Record<string, unknown>) => ({
    id: opts.id,
    name: opts.name,
    type: 'agentic' as const,
  })),
}))

describe('registerAIAgentStep', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    StepRegistry.unregister(RegistryStepId.AGENT)
  })

  it('registers the Task Agent step type in the StepRegistry', () => {
    registerAIAgentStep()

    const registration = StepRegistry.get(RegistryStepId.AGENT)
    expect(registration).toBeDefined()
    expect(registration?.id).toBe(RegistryStepId.AGENT)
    expect(registration?.label).toBe('Task Agent')
    expect(registration?.category).toBe('action')
    expect(registration?.description).toBe('Execute tasks using task agents')
  })

  it('registers with correct order', () => {
    registerAIAgentStep()

    const registration = StepRegistry.get(RegistryStepId.AGENT)
    expect(registration?.order).toBe(20)
  })

  it('registers with searchable keywords', () => {
    registerAIAgentStep()

    const registration = StepRegistry.get(RegistryStepId.AGENT)
    expect(registration?.keywords).toEqual(expect.arrayContaining(['ai', 'agent', 'llm', 'mcp', 'claude']))
  })

  it('onSubmit creates an agentic activity and calls onSuccess', () => {
    const mockAddActivity = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addActivity: mockAddActivity,
    } as never)

    registerAIAgentStep()
    const registration = StepRegistry.get(RegistryStepId.AGENT)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    const formData = {
      name: 'My Agent',
      tools: 'tool1, tool2',
      prompt: 'Do something',
      model: 'claude-3',
      fileIds: ['file-1'],
      credential_id: 'cred-1',
      parsedResponseSchema: undefined,
    }

    registration?.onSubmit(formData, onSuccess, onError)

    expect(mockAddActivity).toHaveBeenCalled()
    expect(onSuccess).toHaveBeenCalledWith(expect.any(String))
    expect(onError).not.toHaveBeenCalled()
  })

  it('onSubmit handles empty fileIds', () => {
    const mockAddActivity = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addActivity: mockAddActivity,
    } as never)

    registerAIAgentStep()
    const registration = StepRegistry.get(RegistryStepId.AGENT)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    const formData = {
      name: 'Agent',
      tools: '',
      prompt: '',
      model: '',
      fileIds: [] as string[],
      credential_id: null,
      parsedResponseSchema: undefined,
    }

    registration?.onSubmit(formData, onSuccess, onError)

    expect(mockAddActivity).toHaveBeenCalled()
    expect(onSuccess).toHaveBeenCalledWith(expect.any(String))
    expect(onError).not.toHaveBeenCalled()
  })

  it('onSubmit handles thrown errors and calls onError', () => {
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addActivity: vi.fn(() => {
        throw new Error('Store error')
      }),
    } as never)

    registerAIAgentStep()
    const registration = StepRegistry.get(RegistryStepId.AGENT)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit(
      {
        name: 'Agent',
        tools: 'tool1',
        prompt: '',
        model: '',
        fileIds: [],
        credential_id: null,
        parsedResponseSchema: undefined,
      },
      onSuccess,
      onError
    )

    expect(onError).toHaveBeenCalledWith('Store error')
    expect(onSuccess).not.toHaveBeenCalled()
  })

  it('onSubmit handles non-Error throws with generic message', () => {
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addActivity: vi.fn(() => {
        throw Object.create(null) as Error
      }),
    } as never)

    registerAIAgentStep()
    const registration = StepRegistry.get(RegistryStepId.AGENT)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit(
      {
        name: 'Agent',
        tools: 'tool1',
        prompt: '',
        model: '',
        fileIds: [],
        credential_id: null,
        parsedResponseSchema: undefined,
      },
      onSuccess,
      onError
    )

    expect(onError).toHaveBeenCalledWith('Failed to add task agent')
    expect(onSuccess).not.toHaveBeenCalled()
  })
})
