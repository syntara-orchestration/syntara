import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RegistryStepId } from '../../../../constants'
import { useWorkflowStore } from '../../../../stores/useWorkflowStore'
import { StepRegistry } from '../StepRegistry'

import registerGenericStep from './registerGenericStep'

vi.mock('../../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: {
    getState: vi.fn(() => ({
      addActivity: vi.fn(),
    })),
  },
  createGenericActivity: vi.fn((id: string, name: string) => ({
    id,
    name,
    type: 'task' as const,
  })),
}))

describe('registerGenericStep', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    StepRegistry.unregister(RegistryStepId.GENERIC)
  })

  it('registers the Generic step type in the StepRegistry', () => {
    registerGenericStep()

    const registration = StepRegistry.get(RegistryStepId.GENERIC)
    expect(registration).toBeDefined()
    expect(registration?.id).toBe(RegistryStepId.GENERIC)
    expect(registration?.label).toBe('Generic Step')
    expect(registration?.category).toBe('other')
    expect(registration?.description).toBe('Placeholder step — click to configure')
  })

  it('registers with enabled=false so it is hidden from AddStepPanel', () => {
    registerGenericStep()

    const registration = StepRegistry.get(RegistryStepId.GENERIC)
    expect(registration?.enabled).toBe(false)
  })

  it('registers with high order so it appears last', () => {
    registerGenericStep()

    const registration = StepRegistry.get(RegistryStepId.GENERIC)
    expect(registration?.order).toBe(1000)
  })

  it('registers with searchable keywords', () => {
    registerGenericStep()

    const registration = StepRegistry.get(RegistryStepId.GENERIC)
    expect(registration?.keywords).toEqual(expect.arrayContaining(['placeholder', 'generic', 'new', 'configure']))
  })

  it('onSubmit creates a generic activity and calls onSuccess', () => {
    const mockAddActivity = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addActivity: mockAddActivity,
    } as never)

    registerGenericStep()
    const registration = StepRegistry.get(RegistryStepId.GENERIC)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit({}, onSuccess, onError)

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

    registerGenericStep()
    const registration = StepRegistry.get(RegistryStepId.GENERIC)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit({}, onSuccess, onError)

    expect(onError).toHaveBeenCalledWith('Store error')
    expect(onSuccess).not.toHaveBeenCalled()
  })

  it('onSubmit handles non-Error throws with generic message', () => {
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addActivity: vi.fn(() => {
        throw Object.create(null) as Error
      }),
    } as never)

    registerGenericStep()
    const registration = StepRegistry.get(RegistryStepId.GENERIC)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit({}, onSuccess, onError)

    expect(onError).toHaveBeenCalledWith('Failed to add generic step')
    expect(onSuccess).not.toHaveBeenCalled()
  })
})
