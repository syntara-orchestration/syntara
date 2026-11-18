import { ExecutorTypeEnum, type Activity } from '@syntara/contracts'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RegistryStepId } from '../../../../constants'
import { useWorkflowStore } from '../../../../stores/useWorkflowStore'
import { StepRegistry } from '../StepRegistry'

import registerActionStep from './registerActionStep'

vi.mock('../../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: {
    getState: vi.fn(() => ({
      addActivity: vi.fn(),
    })),
  },
  createPythonScriptActivity: vi.fn((opts: Record<string, unknown>) => ({
    id: opts.id,
    name: opts.name,
    type: 'script_python' as const,
    parameters: { code: opts.code },
  })),
  createBashScriptActivity: vi.fn((opts: Record<string, unknown>) => ({
    id: opts.id,
    name: opts.name,
    type: 'script_bash' as const,
    parameters: { code: opts.code },
  })),
  createApiActivity: vi.fn((opts: Record<string, unknown>) => ({
    id: opts.id,
    name: opts.name,
    type: 'http_request' as const,
  })),
}))

describe('registerActionStep', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    StepRegistry.unregister(RegistryStepId.ACTION)
  })

  it('registers the Action step type in the StepRegistry', () => {
    registerActionStep()

    const registration = StepRegistry.get(RegistryStepId.ACTION)
    expect(registration).toBeDefined()
    expect(registration?.id).toBe(RegistryStepId.ACTION)
    expect(registration?.label).toBe('Action')
    expect(registration?.category).toBe('action')
    expect(registration?.description).toBe('Execute scripts or make API calls')
  })

  it('registers with correct order', () => {
    registerActionStep()

    const registration = StepRegistry.get(RegistryStepId.ACTION)
    expect(registration?.order).toBe(30)
  })

  it('registers with searchable keywords', () => {
    registerActionStep()

    const registration = StepRegistry.get(RegistryStepId.ACTION)
    expect(registration?.keywords).toEqual(expect.arrayContaining(['script', 'api', 'http', 'python', 'rest']))
  })

  it('includes Python Script, Bash Script, and REST API subtypes', () => {
    registerActionStep()

    const registration = StepRegistry.get(RegistryStepId.ACTION)
    expect(registration?.subtypes).toHaveLength(3)

    const pythonSubtype = registration?.subtypes?.find((s) => s.id === RegistryStepId.ACTION_SCRIPT_PYTHON)
    expect(pythonSubtype).toBeDefined()
    expect(pythonSubtype?.label).toBe('Python Script')
    expect(pythonSubtype?.initialData).toEqual({ executor: ExecutorTypeEnum.SCRIPT_PYTHON })

    const bashSubtype = registration?.subtypes?.find((s) => s.id === RegistryStepId.ACTION_SCRIPT_BASH)
    expect(bashSubtype).toBeDefined()
    expect(bashSubtype?.label).toBe('Bash Script')
    expect(bashSubtype?.initialData).toEqual({ executor: ExecutorTypeEnum.SCRIPT_BASH })

    const apiSubtype = registration?.subtypes?.find((s) => s.id === RegistryStepId.ACTION_API)
    expect(apiSubtype).toBeDefined()
    expect(apiSubtype?.label).toBe('REST API')
    expect(apiSubtype?.initialData).toEqual({ executor: ExecutorTypeEnum.HTTP_REQUEST })
  })

  it('onSubmit creates a script activity and calls onSuccess', () => {
    const mockAddActivity = vi.fn<(activity: Activity) => void>()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addActivity: mockAddActivity,
    } as never)

    registerActionStep()
    const registration = StepRegistry.get(RegistryStepId.ACTION)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit(
      {
        name: 'My Script',
        executor: ExecutorTypeEnum.SCRIPT_PYTHON,
        code: 'print("hello")',
        credential_id: undefined,
      },
      onSuccess,
      onError
    )

    expect(mockAddActivity).toHaveBeenCalled()
    expect(mockAddActivity).toHaveBeenCalledWith(
      expect.objectContaining({
        type: ExecutorTypeEnum.SCRIPT_PYTHON,
        parameters: { code: 'print("hello")' },
      })
    )
    expect(mockAddActivity.mock.calls[0]?.[0].parameters).not.toHaveProperty('language')
    expect(onSuccess).toHaveBeenCalledWith(expect.any(String))
    expect(onError).not.toHaveBeenCalled()
  })

  it('onSubmit creates an API activity and calls onSuccess', () => {
    const mockAddActivity = vi.fn<(activity: Activity) => void>()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addActivity: mockAddActivity,
    } as never)

    registerActionStep()
    const registration = StepRegistry.get(RegistryStepId.ACTION)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit(
      {
        name: 'My API Call',
        executor: ExecutorTypeEnum.HTTP_REQUEST,
        method: 'GET',
        url: 'https://api.example.com',
        headers: {},
        body: '',
        parameters: undefined,
        credential_id: undefined,
      },
      onSuccess,
      onError
    )

    expect(mockAddActivity).toHaveBeenCalled()
    expect(onSuccess).toHaveBeenCalledWith(expect.any(String))
    expect(onError).not.toHaveBeenCalled()
  })

  it('onSubmit creates a Bash activity and calls onSuccess', () => {
    const mockAddActivity = vi.fn<(activity: Activity) => void>()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addActivity: mockAddActivity,
    } as never)

    registerActionStep()
    const registration = StepRegistry.get(RegistryStepId.ACTION)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit(
      {
        name: 'Bash Script',
        executor: ExecutorTypeEnum.SCRIPT_BASH,
        code: 'echo hello',
      },
      onSuccess,
      onError
    )

    expect(mockAddActivity).toHaveBeenCalled()
    expect(mockAddActivity).toHaveBeenCalledWith(
      expect.objectContaining({
        type: ExecutorTypeEnum.SCRIPT_BASH,
        parameters: { code: 'echo hello' },
      })
    )
    expect(onSuccess).toHaveBeenCalledWith(expect.any(String))
    expect(onError).not.toHaveBeenCalled()
  })

  it('creates activity even when API is missing required fields', () => {
    const mockAddActivity = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addActivity: mockAddActivity,
    } as never)

    registerActionStep()
    const registration = StepRegistry.get(RegistryStepId.ACTION)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit(
      {
        name: 'Bad API',
        executor: ExecutorTypeEnum.HTTP_REQUEST,
        method: undefined,
        url: undefined,
      },
      onSuccess,
      onError
    )

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

    registerActionStep()
    const registration = StepRegistry.get(RegistryStepId.ACTION)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit({ name: 'Crash', executor: ExecutorTypeEnum.SCRIPT_PYTHON, code: 'x' }, onSuccess, onError)

    expect(onError).toHaveBeenCalledWith('Store error')
    expect(onSuccess).not.toHaveBeenCalled()
  })

  it('onSubmit handles non-Error throws with generic message', () => {
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addActivity: vi.fn(() => {
        throw Object.create(null) as Error
      }),
    } as never)

    registerActionStep()
    const registration = StepRegistry.get(RegistryStepId.ACTION)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit({ name: 'Crash', executor: ExecutorTypeEnum.SCRIPT_PYTHON, code: 'x' }, onSuccess, onError)

    expect(onError).toHaveBeenCalledWith('Failed to add action')
    expect(onSuccess).not.toHaveBeenCalled()
  })
})
