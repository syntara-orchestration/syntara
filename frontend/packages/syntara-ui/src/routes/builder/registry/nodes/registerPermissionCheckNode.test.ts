import { beforeEach, describe, expect, it, vi } from 'vitest'

const { mockAddActivity, mockCreatePermissionCheckActivity, mockRegister } = vi.hoisted(() => ({
  mockAddActivity: vi.fn(),
  mockCreatePermissionCheckActivity: vi.fn((id: string, name: string) => ({
    id,
    name,
    type: 'permission_check',
    parameters: {},
  })),
  mockRegister: vi.fn(),
}))

vi.mock('../../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: { getState: vi.fn(() => ({ addActivity: mockAddActivity })) },
}))

vi.mock('../../../../stores/workflowFactories', () => ({
  createPermissionCheckActivity: mockCreatePermissionCheckActivity,
}))

vi.mock('../../utils/nodeCreationHelpers', () => ({
  buildNamedActivity: vi.fn(
    (baseName: string, requestedName: string | undefined, build: (id: string, name: string) => unknown) => {
      const activityId = 'activity_permission_check_1'
      const name = requestedName ?? baseName
      return { activityId, name, activity: build(activityId, name) }
    }
  ),
}))

vi.mock('../helpers/nodeTemplates', () => ({
  createCustomNode: vi.fn((config: Record<string, unknown>, handler: (...args: unknown[]) => void) => ({
    ...config,
    onSubmit: handler,
  })),
}))

vi.mock('../NodeRegistry', () => ({
  NodeRegistry: { register: mockRegister },
}))

import registerPermissionCheckNode from './registerPermissionCheckNode'

type RegisteredDefinition = {
  id: string
  label: string
  category: string
  description: string
  keywords: string[]
  formComponent: unknown
  subtypes?: unknown
  onSubmit: (data: Record<string, unknown>, onSuccess: (id?: string) => void, onError: (error: string) => void) => void
}

function getDefinition(): RegisteredDefinition {
  return mockRegister.mock.calls[0][0] as RegisteredDefinition
}

describe('registerPermissionCheckNode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    registerPermissionCheckNode()
  })

  it('registers exactly one node type', () => {
    expect(mockRegister).toHaveBeenCalledTimes(1)
  })

  it('registers under the flow-control (logic) category with the expected label and description', () => {
    const definition = getDefinition()

    expect(definition.id).toBe('logic-permission-check')
    expect(definition.label).toBe('Permission check')
    expect(definition.category).toBe('logic')
    expect(definition.description).toBe('Routes on whether the previous node was allowed to run for this execution')
  })

  it('exposes search keywords and an icon', () => {
    const definition = getDefinition()

    expect(definition.keywords).toContain('permission')
    expect(definition.keywords).toContain('denied')
    expect(definition.formComponent).toBeDefined()
  })

  it('has no subtypes', () => {
    expect(getDefinition().subtypes).toBeUndefined()
  })

  it('creates and adds a permission check activity on submit', () => {
    const onSuccess = vi.fn()
    const onError = vi.fn()

    getDefinition().onSubmit({ name: 'Was it allowed' }, onSuccess, onError)

    expect(mockCreatePermissionCheckActivity).toHaveBeenCalledWith('activity_permission_check_1', 'Was it allowed')
    expect(mockAddActivity).toHaveBeenCalledWith(expect.objectContaining({ type: 'permission_check', parameters: {} }))
    expect(onSuccess).toHaveBeenCalledWith('activity_permission_check_1')
    expect(onError).not.toHaveBeenCalled()
  })

  it('reports an error when the factory throws', () => {
    mockCreatePermissionCheckActivity.mockImplementationOnce(() => {
      throw new Error('boom')
    })
    const onSuccess = vi.fn()
    const onError = vi.fn()

    getDefinition().onSubmit({ name: 'Broken' }, onSuccess, onError)

    expect(onError).toHaveBeenCalledWith('boom')
    expect(onSuccess).not.toHaveBeenCalled()
  })
})
