import { ExecutorTypeEnum } from '@syntara/contracts'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RegistryNodeId } from '../../../../constants'
import { useWorkflowStore } from '../../../../stores/useWorkflowStore'
import { NodeRegistry } from '../NodeRegistry'

import registerActionNode from './registerActionNode'

vi.mock('../../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: {
    getState: vi.fn(() => ({
      addActivity: vi.fn(),
    })),
  },
  createScriptActivity: vi.fn((id: string, name: string) => ({
    id,
    name,
    type: 'script' as const,
  })),
  createApiActivity: vi.fn((opts: Record<string, unknown>) => ({
    id: opts.id,
    name: opts.name,
    type: 'http_request' as const,
  })),
}))

describe('registerActionNode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    NodeRegistry.unregister(RegistryNodeId.ACTION)
  })

  it('registers the Action step type in the NodeRegistry', () => {
    registerActionNode()

    const registration = NodeRegistry.get(RegistryNodeId.ACTION)
    expect(registration).toBeDefined()
    expect(registration?.id).toBe(RegistryNodeId.ACTION)
    expect(registration?.label).toBe('Action')
    expect(registration?.category).toBe('action')
    expect(registration?.description).toBe('Execute scripts or make API calls')
  })

  it('registers with correct order', () => {
    registerActionNode()

    const registration = NodeRegistry.get(RegistryNodeId.ACTION)
    expect(registration?.order).toBe(30)
  })

  it('registers with searchable keywords', () => {
    registerActionNode()

    const registration = NodeRegistry.get(RegistryNodeId.ACTION)
    expect(registration?.keywords).toEqual(expect.arrayContaining(['script', 'api', 'http', 'python', 'rest']))
  })

  it('includes two subtypes: script and REST API', () => {
    registerActionNode()

    const registration = NodeRegistry.get(RegistryNodeId.ACTION)
    expect(registration?.subtypes).toHaveLength(2)

    const scriptSubtype = registration?.subtypes?.find((s) => s.id === RegistryNodeId.ACTION_SCRIPT)
    expect(scriptSubtype).toBeDefined()
    expect(scriptSubtype?.label).toBe('Script')
    expect(scriptSubtype?.initialData).toEqual({ executor: ExecutorTypeEnum.SCRIPT })

    const apiSubtype = registration?.subtypes?.find((s) => s.id === RegistryNodeId.ACTION_API)
    expect(apiSubtype).toBeDefined()
    expect(apiSubtype?.label).toBe('REST API')
    expect(apiSubtype?.initialData).toEqual({ executor: ExecutorTypeEnum.HTTP_REQUEST })
  })

  it('onSubmit creates a script activity and calls onSuccess', () => {
    const mockAddActivity = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addActivity: mockAddActivity,
    } as never)

    registerActionNode()
    const registration = NodeRegistry.get(RegistryNodeId.ACTION)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit(
      {
        name: 'My Script',
        executor: ExecutorTypeEnum.SCRIPT,
        language: 'python',
        code: 'print("hello")',
        credential_id: undefined,
      },
      onSuccess,
      onError
    )

    expect(mockAddActivity).toHaveBeenCalled()
    expect(onSuccess).toHaveBeenCalledWith(expect.any(String))
    expect(onError).not.toHaveBeenCalled()
  })

  it('onSubmit creates an API activity and calls onSuccess', () => {
    const mockAddActivity = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addActivity: mockAddActivity,
    } as never)

    registerActionNode()
    const registration = NodeRegistry.get(RegistryNodeId.ACTION)
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

  it('creates activity even when script is missing required fields', () => {
    const mockAddActivity = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addActivity: mockAddActivity,
    } as never)

    registerActionNode()
    const registration = NodeRegistry.get(RegistryNodeId.ACTION)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit(
      {
        name: 'Bad Script',
        executor: ExecutorTypeEnum.SCRIPT,
        language: undefined,
        code: undefined,
      },
      onSuccess,
      onError
    )

    expect(mockAddActivity).toHaveBeenCalled()
    expect(onSuccess).toHaveBeenCalledWith(expect.any(String))
    expect(onError).not.toHaveBeenCalled()
  })

  it('creates activity even when API is missing required fields', () => {
    const mockAddActivity = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addActivity: mockAddActivity,
    } as never)

    registerActionNode()
    const registration = NodeRegistry.get(RegistryNodeId.ACTION)
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

    registerActionNode()
    const registration = NodeRegistry.get(RegistryNodeId.ACTION)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit(
      { name: 'Crash', executor: ExecutorTypeEnum.SCRIPT, language: 'python', code: 'x' },
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

    registerActionNode()
    const registration = NodeRegistry.get(RegistryNodeId.ACTION)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit(
      { name: 'Crash', executor: ExecutorTypeEnum.SCRIPT, language: 'python', code: 'x' },
      onSuccess,
      onError
    )

    expect(onError).toHaveBeenCalledWith('Failed to add action')
    expect(onSuccess).not.toHaveBeenCalled()
  })
})
